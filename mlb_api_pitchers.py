"""
mlb_api_pitchers.py
MLB Stats API Integration for Real-Time Pitcher Data
Replaces pybaseball (FanGraphs 403 blocked) with official MLB API
"""

import requests
import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

# ─── Configuration ──────────────────────────────────────────────────────────
MLB_API_BASE = "https://statsapi.mlb.com/api/v1"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
CACHE_DURATION_HOURS = 6  # Cache pitcher data for 6 hours
FIP_CONSTANT = 3.15  # Approximate league FIP constant for 2026

# Dome stadiums (no weather impact)
DOME_STADIUMS = {
    "Tropicana Field", "Rogers Centre", "Minute Maid Park",
    "T-Mobile Park", "Globe Life Field", "loanDepot park",
    "American Family Field", "Chase Field"
}

# Team ID mapping (abbreviation -> MLB team ID)
TEAM_ID_MAP = {
    "ARI": 109, "ATL": 144, "BAL": 110, "BOS": 111, "CHC": 112,
    "CIN": 113, "CLE": 114, "COL": 115, "CWS": 145, "DET": 116,
    "HOU": 117, "KC": 118, "LAA": 108, "LAD": 119, "MIA": 146,
    "MIL": 158, "MIN": 142, "NYM": 121, "NYY": 147, "OAK": 133,
    "PHI": 143, "PIT": 134, "SD": 135, "SEA": 136, "SF": 137,
    "STL": 138, "TB": 139, "TEX": 140, "TOR": 141, "WSH": 120
}

# Reverse mapping
TEAM_ABBREV_MAP = {v: k for k, v in TEAM_ID_MAP.items()}


# ─── Data Classes ───────────────────────────────────────────────────────────
@dataclass
class PitcherStats:
    """Comprehensive pitcher statistics from MLB API"""
    player_id: int
    name: str
    team: str
    team_id: int
    era: float
    whip: float
    k_per_9: float
    bb_per_9: float
    hr_per_9: float
    fip: float
    ip: float
    games: int
    games_started: int
    wins: int
    losses: int
    strikeouts: int
    walks: int
    home_runs: int
    hits: int
    batters_faced: int
    # Recent form (last 5 starts)
    recent_era: Optional[float] = None
    recent_k_per_9: Optional[float] = None
    recent_bb_per_9: Optional[float] = None
    # Career context
    career_era: Optional[float] = None
    # Derived metrics
    k_bb_ratio: Optional[float] = None
    groundout_airout: Optional[float] = None

    def to_dict(self) -> Dict:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "team": self.team,
            "team_id": self.team_id,
            "era": self.era,
            "whip": self.whip,
            "k_per_9": self.k_per_9,
            "bb_per_9": self.bb_per_9,
            "hr_per_9": self.hr_per_9,
            "fip": self.fip,
            "ip": self.ip,
            "games": self.games,
            "games_started": self.games_started,
            "wins": self.wins,
            "losses": self.losses,
            "strikeouts": self.strikeouts,
            "walks": self.walks,
            "home_runs": self.home_runs,
            "hits": self.hits,
            "batters_faced": self.batters_faced,
            "recent_era": self.recent_era,
            "recent_k_per_9": self.recent_k_per_9,
            "recent_bb_per_9": self.recent_bb_per_9,
            "career_era": self.career_era,
            "k_bb_ratio": self.k_bb_ratio,
            "groundout_airout": self.groundout_airout,
        }


@dataclass
class GameMatchup:
    """Represents a single game with both pitchers"""
    game_pk: int
    game_date: str
    game_time: str
    away_team: str
    away_team_id: int
    home_team: str
    home_team_id: int
    away_pitcher: Optional[PitcherStats]
    home_pitcher: Optional[PitcherStats]
    venue: str
    venue_id: int
    is_dome: bool
    status: str


# ─── Cache Management ────────────────────────────────────────────────────────
def _ensure_cache_dir():
    """Create cache directory if it doesn't exist"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)


def _get_cache_path(key: str) -> str:
    """Get cache file path for a given key"""
    _ensure_cache_dir()
    safe_key = key.replace("/", "_").replace("?", "_").replace("&", "_")
    return os.path.join(CACHE_DIR, f"{safe_key}.json")


def _is_cache_valid(cache_path: str) -> bool:
    """Check if cache file exists and is within duration"""
    if not os.path.exists(cache_path):
        return False
    mtime = datetime.fromtimestamp(os.path.getmtime(cache_path))
    return datetime.now() - mtime < timedelta(hours=CACHE_DURATION_HOURS)


def _cache_get(key: str) -> Optional[Dict]:
    """Get data from cache if valid"""
    cache_path = _get_cache_path(key)
    if _is_cache_valid(cache_path):
        with open(cache_path, "r") as f:
            return json.load(f)
    return None


def _cache_set(key: str, data: Dict):
    """Save data to cache"""
    cache_path = _get_cache_path(key)
    with open(cache_path, "w") as f:
        json.dump(data, f, indent=2)


# ─── API Helpers ────────────────────────────────────────────────────────────
def _api_get(endpoint: str, params: Optional[Dict] = None, use_cache: bool = True) -> Optional[Dict]:
    """
    Make GET request to MLB Stats API with caching support.
    Returns parsed JSON or None on failure.
    """
    url = f"{MLB_API_BASE}{endpoint}"
    cache_key = f"{endpoint}_{json.dumps(params or {}, sort_keys=True)}"

    # Try cache first
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        if use_cache:
            _cache_set(cache_key, data)
        return data
    except requests.exceptions.RequestException as e:
        print(f"[MLB API Error] {url}: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"[MLB API JSON Error] {url}: {e}")
        return None


# ─── Core Functions ─────────────────────────────────────────────────────────
def get_today_schedule(date_str: Optional[str] = None) -> List[Dict]:
    """
    Fetch MLB schedule for a specific date.

    Args:
        date_str: Date in MM/DD/YYYY format. Defaults to today.

    Returns:
        List of game dictionaries with probable pitchers.
    """
    if date_str is None:
        date_str = datetime.now().strftime("%m/%d/%Y")

    params = {
        "sportId": 1,
        "date": date_str,
        "hydrate": "probablePitcher,venue,team"
    }

    data = _api_get("/schedule/games/", params)
    if not data or not data.get("dates"):
        return []

    games = []
    for date_info in data["dates"]:
        for game in date_info.get("games", []):
            games.append(game)

    return games


def get_pitcher_stats(player_id: int, include_recent: bool = True, 
                      include_career: bool = False) -> Optional[PitcherStats]:
    """
    Fetch comprehensive stats for a single pitcher.

    Args:
        player_id: MLB player ID
        include_recent: Whether to fetch last 5 game logs
        include_career: Whether to fetch career stats

    Returns:
        PitcherStats object or None if not found / not a pitcher.
    """
    # Fetch season stats
    season_data = _api_get(f"/people/{player_id}/stats", {
        "stats": "season",
        "group": "pitching"
    })

    if not season_data or not season_data.get("stats"):
        return None

    splits = season_data["stats"][0].get("splits", [])
    if not splits:
        return None

    stat = splits[0]["stat"]
    player_info = splits[0].get("player", {})
    team_info = splits[0].get("team", {})

    # Calculate FIP
    hr = int(stat.get("homeRuns", 0))
    bb = int(stat.get("baseOnBalls", 0))
    hbp = int(stat.get("hitByPitch", 0))
    k = int(stat.get("strikeOuts", 0))
    ip = float(stat.get("inningsPitched", "0"))

    fip = FIP_CONSTANT
    if ip > 0:
        fip = ((13 * hr) + (3 * (bb + hbp)) - (2 * k)) / ip + FIP_CONSTANT

    # K/BB ratio
    k_bb_ratio = None
    if bb > 0:
        k_bb_ratio = k / bb

    # Groundout/Airout ratio
    go = int(stat.get("groundOuts", 0))
    ao = int(stat.get("airOuts", 0))
    go_ao = None
    if ao > 0:
        go_ao = go / ao

    pitcher = PitcherStats(
        player_id=player_id,
        name=player_info.get("fullName", f"Player {player_id}"),
        team=team_info.get("name", "Unknown"),
        team_id=team_info.get("id", 0),
        era=float(stat.get("era", "0")),
        whip=float(stat.get("whip", "0")),
        k_per_9=float(stat.get("strikeoutsPer9Inn", "0")),
        bb_per_9=float(stat.get("walksPer9Inn", "0")),
        hr_per_9=float(stat.get("homeRunsPer9", "0")),
        fip=round(fip, 2),
        ip=ip,
        games=int(stat.get("gamesPlayed", 0)),
        games_started=int(stat.get("gamesStarted", 0)),
        wins=int(stat.get("wins", 0)),
        losses=int(stat.get("losses", 0)),
        strikeouts=k,
        walks=bb,
        home_runs=hr,
        hits=int(stat.get("hits", 0)),
        batters_faced=int(stat.get("battersFaced", 0)),
        k_bb_ratio=round(k_bb_ratio, 2) if k_bb_ratio else None,
        groundout_airout=round(go_ao, 2) if go_ao else None,
    )

    # Fetch recent form (last 5 games)
    if include_recent:
        recent = _get_recent_form(player_id)
        if recent:
            pitcher.recent_era = recent.get("era")
            pitcher.recent_k_per_9 = recent.get("k_per_9")
            pitcher.recent_bb_per_9 = recent.get("bb_per_9")

    # Fetch career stats
    if include_career:
        career = _get_career_stats(player_id)
        if career:
            pitcher.career_era = career.get("era")

    return pitcher


def _get_recent_form(player_id: int, num_games: int = 5) -> Optional[Dict]:
    """Calculate stats from last N games"""
    gamelog_data = _api_get(f"/people/{player_id}/stats", {
        "stats": "gameLog",
        "group": "pitching",
        "limit": num_games
    })

    if not gamelog_data or not gamelog_data.get("stats"):
        return None

    splits = gamelog_data["stats"][0].get("splits", [])
    if len(splits) < 2:  # Need at least 2 games for meaningful data
        return None

    total_ip = 0.0
    total_er = 0
    total_k = 0
    total_bb = 0

    for game in splits[:num_games]:
        stat = game.get("stat", {})
        ip_str = stat.get("inningsPitched", "0")
        # Convert IP string (e.g., "5.1") to decimal
        if "." in str(ip_str):
            parts = str(ip_str).split(".")
            whole = int(parts[0])
            frac = int(parts[1])
            ip_decimal = whole + frac / 3.0
        else:
            ip_decimal = float(ip_str)

        total_ip += ip_decimal
        total_er += int(stat.get("earnedRuns", 0))
        total_k += int(stat.get("strikeOuts", 0))
        total_bb += int(stat.get("baseOnBalls", 0))

    if total_ip <= 0:
        return None

    return {
        "era": round((total_er / total_ip) * 9, 2),
        "k_per_9": round((total_k / total_ip) * 9, 2),
        "bb_per_9": round((total_bb / total_ip) * 9, 2),
        "games": len(splits[:num_games])
    }


def _get_career_stats(player_id: int) -> Optional[Dict]:
    """Fetch career pitching stats"""
    career_data = _api_get(f"/people/{player_id}/stats", {
        "stats": "career",
        "group": "pitching"
    })

    if not career_data or not career_data.get("stats"):
        return None

    splits = career_data["stats"][0].get("splits", [])
    if not splits:
        return None

    stat = splits[0]["stat"]
    return {
        "era": float(stat.get("era", "0")),
        "whip": float(stat.get("whip", "0")),
        "ip": float(stat.get("inningsPitched", "0")),
        "games": int(stat.get("gamesPlayed", 0))
    }


def get_today_matchups(date_str: Optional[str] = None) -> List[GameMatchup]:
    """
    Get all today's games with full pitcher data.

    Returns:
        List of GameMatchup objects with populated pitcher stats.
    """
    games = get_today_schedule(date_str)
    matchups = []

    for game in games:
        game_pk = game.get("gamePk")
        game_date = game.get("gameDate", "")[:10]
        game_time = game.get("gameDate", "")[11:16] if game.get("gameDate") else "TBD"

        teams = game.get("teams", {})
        away_team_info = teams.get("away", {}).get("team", {})
        home_team_info = teams.get("home", {}).get("team", {})

        away_team = away_team_info.get("name", "Unknown")
        away_team_id = away_team_info.get("id", 0)
        home_team = home_team_info.get("name", "Unknown")
        home_team_id = home_team_info.get("id", 0)

        venue_info = game.get("venue", {})
        venue = venue_info.get("name", "Unknown")
        venue_id = venue_info.get("id", 0)
        is_dome = venue in DOME_STADIUMS

        # Get probable pitchers
        away_pitcher_info = teams.get("away", {}).get("probablePitcher")
        home_pitcher_info = teams.get("home", {}).get("probablePitcher")

        away_pitcher = None
        home_pitcher = None

        if away_pitcher_info and away_pitcher_info.get("id"):
            away_pitcher = get_pitcher_stats(away_pitcher_info["id"])

        if home_pitcher_info and home_pitcher_info.get("id"):
            home_pitcher = get_pitcher_stats(home_pitcher_info["id"])

        matchup = GameMatchup(
            game_pk=game_pk,
            game_date=game_date,
            game_time=game_time,
            away_team=away_team,
            away_team_id=away_team_id,
            home_team=home_team,
            home_team_id=home_team_id,
            away_pitcher=away_pitcher,
            home_pitcher=home_pitcher,
            venue=venue,
            venue_id=venue_id,
            is_dome=is_dome,
            status=game.get("status", {}).get("detailedState", "Unknown")
        )
        matchups.append(matchup)

    return matchups


def get_team_pitchers(team_id: int, active_only: bool = True) -> List[PitcherStats]:
    """
    Get all pitchers for a specific team.

    Args:
        team_id: MLB team ID
        active_only: Only return pitchers on active roster

    Returns:
        List of PitcherStats objects.
    """
    roster_data = _api_get(f"/teams/{team_id}/roster", {"season": 2026})

    if not roster_data or not roster_data.get("roster"):
        return []

    pitchers = []
    for entry in roster_data["roster"]:
        position = entry.get("position", {}).get("abbreviation", "")
        if position != "P":
            continue

        if active_only and entry.get("status", {}).get("code") != "A":
            continue

        person = entry.get("person", {})
        player_id = person.get("id")
        if player_id:
            stats = get_pitcher_stats(player_id, include_recent=False, include_career=False)
            if stats:
                pitchers.append(stats)

    return pitchers


def get_pitcher_by_name(name: str) -> Optional[PitcherStats]:
    """
    Search for a pitcher by name and return their stats.
    Uses the people search endpoint.

    Args:
        name: Full or partial player name

    Returns:
        PitcherStats or None if not found.
    """
    # MLB API doesn't have a direct search, so we use the sports_players endpoint
    # or try to find via team rosters
    # For now, this is a simplified version - in production you'd want
    # a more robust search mechanism

    # Try each team's roster
    for team_id in TEAM_ID_MAP.values():
        pitchers = get_team_pitchers(team_id, active_only=True)
        for p in pitchers:
            if name.lower() in p.name.lower():
                return p

    return None


# ─── Comparison & Analysis ──────────────────────────────────────────────────
def compare_pitchers(p1: PitcherStats, p2: PitcherStats) -> Dict:
    """
    Compare two pitchers and return advantage metrics.

    Returns:
        Dict with advantage scores (-1 to 1) for each stat.
        Positive = p1 (away) advantage, Negative = p2 (home) advantage.
    """
    def _normalize(val1, val2, lower_is_better=True):
        """Normalize difference to -1 to 1 scale"""
        if val1 is None or val2 is None:
            return 0.0
        diff = val2 - val1 if lower_is_better else val1 - val2
        avg = (abs(val1) + abs(val2)) / 2.0 if (val1 + val2) != 0 else 1.0
        return max(-1.0, min(1.0, diff / avg))

    return {
        "era": _normalize(p1.era, p2.era, lower_is_better=True),
        "whip": _normalize(p1.whip, p2.whip, lower_is_better=True),
        "k_per_9": _normalize(p1.k_per_9, p2.k_per_9, lower_is_better=False),
        "bb_per_9": _normalize(p1.bb_per_9, p2.bb_per_9, lower_is_better=True),
        "hr_per_9": _normalize(p1.hr_per_9, p2.hr_per_9, lower_is_better=True),
        "fip": _normalize(p1.fip, p2.fip, lower_is_better=True),
        "ip": _normalize(p1.ip, p2.ip, lower_is_better=False),
    }


def get_pitcher_advantage_score(p1: PitcherStats, p2: PitcherStats, 
                                weights: Optional[Dict] = None) -> float:
    """
    Calculate overall pitcher advantage score.

    Args:
        p1: Away pitcher
        p2: Home pitcher
        weights: Custom weights for each stat. Defaults to balanced.

    Returns:
        Score from -1 (strong home advantage) to 1 (strong away advantage).
    """
    if weights is None:
        weights = {
            "era": 0.25,
            "whip": 0.20,
            "k_per_9": 0.15,
            "bb_per_9": 0.15,
            "hr_per_9": 0.10,
            "fip": 0.15,
        }

    comparison = compare_pitchers(p1, p2)
    score = 0.0
    total_weight = 0.0

    for stat, weight in weights.items():
        score += comparison.get(stat, 0) * weight
        total_weight += weight

    if total_weight > 0:
        score /= total_weight

    return round(score, 3)


# ─── Integration with Existing System ───────────────────────────────────────
def get_pitcher_data_for_prediction(game_date: Optional[str] = None) -> List[Dict]:
    """
    Main entry point for the prediction system.
    Returns structured data compatible with the existing v6.0 pipeline.

    Returns:
        List of game dicts with pitcher data ready for model input.
    """
    matchups = get_today_matchups(game_date)
    results = []

    for m in matchups:
        game_data = {
            "game_pk": m.game_pk,
            "date": m.game_date,
            "time": m.game_time,
            "away_team": m.away_team,
            "away_team_id": m.away_team_id,
            "home_team": m.home_team,
            "home_team_id": m.home_team_id,
            "venue": m.venue,
            "is_dome": m.is_dome,
            "status": m.status,
            "away_pitcher": m.away_pitcher.to_dict() if m.away_pitcher else None,
            "home_pitcher": m.home_pitcher.to_dict() if m.home_pitcher else None,
        }

        # Add derived comparison metrics
        if m.away_pitcher and m.home_pitcher:
            game_data["pitcher_comparison"] = compare_pitchers(m.away_pitcher, m.home_pitcher)
            game_data["pitcher_advantage"] = get_pitcher_advantage_score(
                m.away_pitcher, m.home_pitcher
            )
        else:
            game_data["pitcher_comparison"] = None
            game_data["pitcher_advantage"] = None

        results.append(game_data)

    return results


def clear_cache():
    """Clear all cached API responses"""
    _ensure_cache_dir()
    for f in os.listdir(CACHE_DIR):
        if f.endswith(".json"):
            os.remove(os.path.join(CACHE_DIR, f))
    print("[MLB API] Cache cleared.")


# ─── CLI / Testing ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("MLB API Pitchers Module - Test Run")
    print("=" * 60)

    # Test 1: Get today's matchups
    print("\n--- Today's Matchups ---")
    matchups = get_today_matchups()
    print(f"Found {len(matchups)} games")

    for m in matchups[:3]:
        print(f"\n{m.away_team} @ {m.home_team} ({m.game_time})")
        print(f"  Venue: {m.venue} {'(Dome)' if m.is_dome else ''}")
        if m.away_pitcher:
            print(f"  Away SP: {m.away_pitcher.name} - ERA: {m.away_pitcher.era}, FIP: {m.away_pitcher.fip}")
        else:
            print(f"  Away SP: TBD")
        if m.home_pitcher:
            print(f"  Home SP: {m.home_pitcher.name} - ERA: {m.home_pitcher.era}, FIP: {m.home_pitcher.fip}")
        else:
            print(f"  Home SP: TBD")

    # Test 2: Get prediction-ready data
    print("\n--- Prediction Data Sample ---")
    pred_data = get_pitcher_data_for_prediction()
    if pred_data:
        sample = pred_data[0]
        print(f"Game: {sample['away_team']} @ {sample['home_team']}")
        print(f"Pitcher Advantage: {sample.get('pitcher_advantage')}")
        if sample.get('pitcher_comparison'):
            print("Comparison:")
            for stat, val in sample['pitcher_comparison'].items():
                direction = "Away" if val > 0 else "Home" if val < 0 else "Even"
                print(f"  {stat}: {val:+.3f} ({direction})")
