"""
data_fetchers.py - Data Fetching Module v6.0
Integrates: MLB Stats API, OpenWeatherMap Forecast, ESPN Injury Scraper
Replaces: pybaseball (FanGraphs blocked) with official MLB API
"""

import requests
import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from config import (
    MLB_API_BASE, OPENWEATHER_API_KEY, DOME_STADIUMS, VENUE_COORDINATES,
    TEAM_ID_MAP, TEAM_ABBREV_MAP, TEAM_NAMES, CACHE_DIR,
    CACHE_DURATION_HOURS, FIP_CONSTANT, get_today_date,
    load_json, save_json
)

# ─── Data Classes ─────────────────────────────────────────────────────────────
@dataclass
class PitcherStats:
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
    recent_era: Optional[float] = None
    recent_k_per_9: Optional[float] = None
    recent_bb_per_9: Optional[float] = None
    career_era: Optional[float] = None
    k_bb_ratio: Optional[float] = None
    groundout_airout: Optional[float] = None

    def to_dict(self) -> Dict:
        return {
            "player_id": self.player_id, "name": self.name, "team": self.team,
            "team_id": self.team_id, "era": self.era, "whip": self.whip,
            "k_per_9": self.k_per_9, "bb_per_9": self.bb_per_9,
            "hr_per_9": self.hr_per_9, "fip": self.fip, "ip": self.ip,
            "games": self.games, "games_started": self.games_started,
            "wins": self.wins, "losses": self.losses,
            "strikeouts": self.strikeouts, "walks": self.walks,
            "home_runs": self.home_runs, "hits": self.hits,
            "batters_faced": self.batters_faced,
            "recent_era": self.recent_era, "recent_k_per_9": self.recent_k_per_9,
            "recent_bb_per_9": self.recent_bb_per_9, "career_era": self.career_era,
            "k_bb_ratio": self.k_bb_ratio, "groundout_airout": self.groundout_airout,
        }


@dataclass
class WeatherData:
    venue: str
    is_dome: bool
    temperature: Optional[float] = None
    humidity: Optional[int] = None
    wind_speed: Optional[float] = None
    wind_direction: Optional[str] = None
    condition: Optional[str] = None
    precipitation_chance: Optional[float] = None
    forecast_time: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "venue": self.venue, "is_dome": self.is_dome,
            "temperature": self.temperature, "humidity": self.humidity,
            "wind_speed": self.wind_speed, "wind_direction": self.wind_direction,
            "condition": self.condition, "precipitation_chance": self.precipitation_chance,
            "forecast_time": self.forecast_time
        }


@dataclass
class InjuryInfo:
    player_name: str
    team: str
    injury_type: str
    severity: str  # low, medium, high
    status: str
    return_estimate: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "player_name": self.player_name, "team": self.team,
            "injury_type": self.injury_type, "severity": self.severity,
            "status": self.status, "return_estimate": self.return_estimate
        }


@dataclass
class GameData:
    game_pk: int
    game_date: str
    game_time: str
    away_team: str
    away_team_id: int
    home_team: str
    home_team_id: int
    away_pitcher: Optional[PitcherStats] = None
    home_pitcher: Optional[PitcherStats] = None
    weather: Optional[WeatherData] = None
    away_injuries: List[InjuryInfo] = field(default_factory=list)
    home_injuries: List[InjuryInfo] = field(default_factory=list)
    venue: str = ""
    venue_id: int = 0
    is_dome: bool = False
    status: str = "Scheduled"

    def to_dict(self) -> Dict:
        return {
            "game_pk": self.game_pk, "game_date": self.game_date,
            "game_time": self.game_time, "away_team": self.away_team,
            "away_team_id": self.away_team_id, "home_team": self.home_team,
            "home_team_id": self.home_team_id,
            "away_pitcher": self.away_pitcher.to_dict() if self.away_pitcher else None,
            "home_pitcher": self.home_pitcher.to_dict() if self.home_pitcher else None,
            "weather": self.weather.to_dict() if self.weather else None,
            "away_injuries": [i.to_dict() for i in self.away_injuries],
            "home_injuries": [i.to_dict() for i in self.home_injuries],
            "venue": self.venue, "venue_id": self.venue_id,
            "is_dome": self.is_dome, "status": self.status
        }


# ─── Cache Helpers ────────────────────────────────────────────────────────────
def _cache_path(key: str) -> str:
    """Create Windows-safe cache filename using hash"""
    import hashlib
    # Hash the key to avoid illegal characters in filename
    key_hash = hashlib.md5(key.encode()).hexdigest()[:16]
    # Add a short prefix for readability
    prefix = key.split("/")[-1].split("?")[0] if "/" in key else "cache"
    safe_prefix = "".join(c for c in prefix if c.isalnum() or c in "_-").rstrip()[:20]
    return os.path.join(CACHE_DIR, f"{safe_prefix}_{key_hash}.json")

def _is_cache_valid(path: str) -> bool:
    if not os.path.exists(path):
        return False
    mtime = datetime.fromtimestamp(os.path.getmtime(path))
    return datetime.now() - mtime < timedelta(hours=CACHE_DURATION_HOURS)

def _cache_get(key: str) -> Optional[Dict]:
    path = _cache_path(key)
    if _is_cache_valid(path):
        return load_json(path)
    return None

def _cache_set(key: str, data: Dict):
    path = _cache_path(key)
    save_json(path, data)

# ─── MLB API Core ─────────────────────────────────────────────────────────────
def mlb_api_get(endpoint: str, params: Optional[Dict] = None, use_cache: bool = True) -> Optional[Dict]:
    url = f"{MLB_API_BASE}{endpoint}"
    cache_key = f"{endpoint}_{json.dumps(params or {}, sort_keys=True)}"

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
    except Exception as e:
        print(f"[MLB API Error] {url}: {e}")
        return None

# ─── Pitcher Data (MLB Stats API) ─────────────────────────────────────────────
def get_pitcher_stats(player_id: int, include_recent: bool = True) -> Optional[PitcherStats]:
    """Fetch comprehensive pitcher stats from MLB Stats API"""
    season_data = mlb_api_get(f"/people/{player_id}/stats", {"stats": "season", "group": "pitching"})
    if not season_data or not season_data.get("stats"):
        return None

    splits = season_data["stats"][0].get("splits", [])
    if not splits:
        return None

    stat = splits[0]["stat"]
    player_info = splits[0].get("player", {})
    team_info = splits[0].get("team", {})

    hr = int(stat.get("homeRuns", 0))
    bb = int(stat.get("baseOnBalls", 0))
    hbp = int(stat.get("hitByPitch", 0))
    k = int(stat.get("strikeOuts", 0))
    ip = float(stat.get("inningsPitched", "0"))

    fip = FIP_CONSTANT
    if ip > 0:
        fip = ((13 * hr) + (3 * (bb + hbp)) - (2 * k)) / ip + FIP_CONSTANT

    k_bb_ratio = k / bb if bb > 0 else None
    go = int(stat.get("groundOuts", 0))
    ao = int(stat.get("airOuts", 0))
    go_ao = go / ao if ao > 0 else None

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

    if include_recent:
        recent = _get_recent_form(player_id)
        if recent:
            pitcher.recent_era = recent.get("era")
            pitcher.recent_k_per_9 = recent.get("k_per_9")
            pitcher.recent_bb_per_9 = recent.get("bb_per_9")

    return pitcher

def _get_recent_form(player_id: int, num_games: int = 5) -> Optional[Dict]:
    """Calculate stats from last N games"""
    gamelog_data = mlb_api_get(f"/people/{player_id}/stats", {"stats": "gameLog", "group": "pitching", "limit": num_games})
    if not gamelog_data or not gamelog_data.get("stats"):
        return None

    splits = gamelog_data["stats"][0].get("splits", [])
    if len(splits) < 2:
        return None

    total_ip = 0.0
    total_er = 0
    total_k = 0
    total_bb = 0

    for game in splits[:num_games]:
        stat = game.get("stat", {})
        ip_str = stat.get("inningsPitched", "0")
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

# ─── Schedule & Games ─────────────────────────────────────────────────────────
def get_schedule(date_str: Optional[str] = None) -> List[Dict]:
    """Fetch MLB schedule with probable pitchers"""
    if date_str is None:
        date_str = get_today_date()

    params = {"sportId": 1, "date": date_str, "hydrate": "probablePitcher,venue,team"}
    data = mlb_api_get("/schedule/games/", params)
    if not data or not data.get("dates"):
        return []

    games = []
    for date_info in data["dates"]:
        for game in date_info.get("games", []):
            games.append(game)
    return games

def get_all_games(date_str: Optional[str] = None) -> List[GameData]:
    """Fetch all games with full pitcher and weather data"""
    games = get_schedule(date_str)
    result = []

    for game in games:
        game_pk = game.get("gamePk")
        game_date = game.get("gameDate", "")[:10]
        game_time = game.get("gameDate", "")[11:16] if game.get("gameDate") else "TBD"

        teams = game.get("teams", {})
        away_info = teams.get("away", {}).get("team", {})
        home_info = teams.get("home", {}).get("team", {})

        venue_info = game.get("venue", {})
        venue = venue_info.get("name", "Unknown")
        venue_id = venue_info.get("id", 0)
        is_dome = venue in DOME_STADIUMS

        game_data = GameData(
            game_pk=game_pk,
            game_date=game_date,
            game_time=game_time,
            away_team=away_info.get("name", "Unknown"),
            away_team_id=away_info.get("id", 0),
            home_team=home_info.get("name", "Unknown"),
            home_team_id=home_info.get("id", 0),
            venue=venue,
            venue_id=venue_id,
            is_dome=is_dome,
            status=game.get("status", {}).get("detailedState", "Unknown")
        )

        # Fetch pitchers
        away_pitcher_info = teams.get("away", {}).get("probablePitcher")
        home_pitcher_info = teams.get("home", {}).get("probablePitcher")

        if away_pitcher_info and away_pitcher_info.get("id"):
            game_data.away_pitcher = get_pitcher_stats(away_pitcher_info["id"])

        if home_pitcher_info and home_pitcher_info.get("id"):
            game_data.home_pitcher = get_pitcher_stats(home_pitcher_info["id"])

        # Fetch injuries
        try:
            game_data.away_injuries = get_injuries_for_team(game_data.away_team)
            game_data.home_injuries = get_injuries_for_team(game_data.home_team)
        except Exception as e:
            print(f"[Injuries Fetch Error] {e}")

        # Fetch weather
        if not is_dome:
            game_data.weather = get_weather_for_venue(venue, game_date, game_time)
        else:
            game_data.weather = WeatherData(venue=venue, is_dome=True)

        result.append(game_data)

    return result

# ─── Weather (OpenWeatherMap Forecast API) ────────────────────────────────────
def get_weather_for_venue(venue: str, game_date: str, game_time: str) -> Optional[WeatherData]:
    """Fetch weather forecast for game time using OpenWeatherMap Forecast API"""
    if not OPENWEATHER_API_KEY:
        return _simulated_weather(venue)

    coords = VENUE_COORDINATES.get(venue)
    if not coords:
        return _simulated_weather(venue)

    try:
        url = "https://api.openweathermap.org/data/2.5/forecast"
        params = {
            "lat": coords[0],
            "lon": coords[1],
            "appid": OPENWEATHER_API_KEY,
            "units": "imperial"
        }
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        # Find forecast closest to game time
        game_dt = datetime.strptime(f"{game_date} {game_time}", "%Y-%m-%d %H:%M")
        closest = None
        min_diff = float('inf')

        for item in data.get("list", []):
            forecast_dt = datetime.fromtimestamp(item.get("dt", 0))
            diff = abs((forecast_dt - game_dt).total_seconds())
            if diff < min_diff:
                min_diff = diff
                closest = item

        if closest:
            main = closest.get("main", {})
            wind = closest.get("wind", {})
            weather_list = closest.get("weather", [{}])

            return WeatherData(
                venue=venue,
                is_dome=False,
                temperature=main.get("temp"),
                humidity=main.get("humidity"),
                wind_speed=wind.get("speed"),
                wind_direction=_degrees_to_direction(wind.get("deg", 0)),
                condition=weather_list[0].get("main"),
                precipitation_chance=closest.get("pop", 0) * 100,
                forecast_time=datetime.fromtimestamp(closest.get("dt", 0)).strftime("%Y-%m-%d %H:%M")
            )
    except Exception as e:
        print(f"[Weather API Error] {venue}: {e}")

    return _simulated_weather(venue)

def _simulated_weather(venue: str) -> WeatherData:
    """Fallback simulated weather data"""
    import random
    random.seed(hash(venue) % 10000)
    return WeatherData(
        venue=venue,
        is_dome=False,
        temperature=round(random.uniform(65, 85), 1),
        humidity=random.randint(40, 80),
        wind_speed=round(random.uniform(3, 15), 1),
        wind_direction=random.choice(["N", "NE", "E", "SE", "S", "SW", "W", "NW"]),
        condition=random.choice(["Clear", "Clouds", "Partly Cloudy"]),
        precipitation_chance=round(random.uniform(0, 30), 1),
        forecast_time="simulated"
    )

def _degrees_to_direction(deg: int) -> str:
    """Convert wind degrees to cardinal direction"""
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    idx = round(deg / 22.5) % 16
    return dirs[idx]

# ─── Injury Data (ESPN Scraper) ───────────────────────────────────────────────
_espn_injuries_cache = None

def get_all_espn_injuries() -> Dict:
    global _espn_injuries_cache
    if _espn_injuries_cache is not None:
        return _espn_injuries_cache
    cached = _cache_get("espn_injuries_all")
    if cached:
        _espn_injuries_cache = cached
        return cached
    try:
        url = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/injuries"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        _cache_set("espn_injuries_all", data)
        _espn_injuries_cache = data
        return data
    except Exception as e:
        print(f"[Injury API Error]: {e}")
        return {}

def get_injuries_for_team(team_name: str) -> List[InjuryInfo]:
    """Scrape injury data from ESPN with global caching"""
    data = get_all_espn_injuries()
    if not data:
        return []
    injuries = []
    for team_data in data.get("injuries", []):
        if team_name.lower() in team_data.get("team", {}).get("name", "").lower():
            for injury in team_data.get("injuries", []):
                injuries.append(InjuryInfo(
                    player_name=injury.get("athlete", {}).get("displayName", "Unknown"),
                    team=team_name,
                    injury_type=injury.get("injury", "Unknown"),
                    severity=_classify_severity(injury.get("status", ""), injury.get("injury", "")),
                    status=injury.get("status", "Unknown"),
                    return_estimate=injury.get("returnDate")
                ))
    return injuries

def _classify_severity(status: str, injury_type: str) -> str:
    """Classify injury severity"""
    status_lower = status.lower()
    injury_lower = injury_type.lower()

    high_keywords = ["out", "surgery", "fracture", "tear", "rupture", "concussion", "il"]
    medium_keywords = ["day-to-day", "dtd", "sprain", "strain", "inflammation"]

    for kw in high_keywords:
        if kw in status_lower or kw in injury_lower:
            return "high"
    for kw in medium_keywords:
        if kw in status_lower or kw in injury_lower:
            return "medium"
    return "low"

def _simulated_injuries(team_name: str) -> List[InjuryInfo]:
    """Fallback simulated injury data"""
    import random
    random.seed(hash(team_name) % 10000)

    if random.random() > 0.3:  # 70% chance no injuries
        return []

    severities = ["low", "medium", "high"]
    return [InjuryInfo(
        player_name=f"Player_{random.randint(1, 99)}",
        team=team_name,
        injury_type=random.choice(["Hamstring", "Shoulder", "Back", "Knee"]),
        severity=random.choice(severities),
        status=random.choice(["Day-to-day", "Out", "10-day IL"]),
        return_estimate=None
    )]

def get_all_team_offense_stats() -> Dict[int, Dict]:
    """Fetch hitting stats for ALL teams in 1 bulk API request"""
    data = mlb_api_get("/teams/stats", {"season": 2026, "group": "hitting", "stats": "season"})
    offense_map = {}
    if not data or not data.get("stats"):
        return offense_map
    for split in data["stats"][0].get("splits", []):
        team_id = split.get("team", {}).get("id", 0)
        st = split.get("stat", {})
        gp = int(st.get("gamesPlayed", 1)) or 1
        runs = int(st.get("runs", 0))
        offense_map[team_id] = {
            "ops": float(st.get("ops", 0.730)),
            "runs_per_game": round(runs / gp, 2),
            "avg": float(st.get("avg", 0.245)),
            "obp": float(st.get("obp", 0.315)),
            "slg": float(st.get("slg", 0.410))
        }
    return offense_map


def get_all_team_bullpen_stats() -> Dict[int, Dict]:
    """Fetch pitching stats for ALL teams in 1 bulk API request"""
    data = mlb_api_get("/teams/stats", {"season": 2026, "group": "pitching", "stats": "season"})
    pitching_map = {}
    if not data or not data.get("stats"):
        return pitching_map
    for split in data["stats"][0].get("splits", []):
        team_id = split.get("team", {}).get("id", 0)
        st = split.get("stat", {})
        pitching_map[team_id] = {
            "era": float(st.get("era", 4.10)),
            "whip": float(st.get("whip", 1.28)),
            "k_per_9": float(st.get("strikeoutsPer9Inn", 8.8)),
            "bb_per_9": float(st.get("walksPer9Inn", 3.2))
        }
    return pitching_map


# ─── Team Standings / Records ─────────────────────────────────────────────────
def get_team_standings() -> Dict[int, Dict]:
    """Fetch current standings & team stats from MLB API"""
    data = mlb_api_get("/standings", {"leagueId": "103,104", "season": 2026, "standingsTypes": "regularSeason"})
    if not data or not data.get("records"):
        return {}

    # Bulk fetch offense & bullpen stats for all 30 teams
    all_offense = get_all_team_offense_stats()
    all_pitching = get_all_team_bullpen_stats()

    standings = {}
    for record in data["records"]:
        for team_record in record.get("teamRecords", []):
            team_id = team_record.get("team", {}).get("id", 0)
            wins = int(team_record.get("wins", 0))
            losses = int(team_record.get("losses", 0))
            win_pct = float(team_record.get("winningPercentage", "0"))

            offense = all_offense.get(team_id, {"ops": 0.730, "runs_per_game": 4.5, "avg": 0.245, "obp": 0.315, "slg": 0.410})
            pitching = all_pitching.get(team_id, {"era": 4.10, "whip": 1.28, "k_per_9": 8.8, "bb_per_9": 3.2})

            standings[team_id] = {
                "wins": wins,
                "losses": losses,
                "win_pct": win_pct,
                "games_back": team_record.get("gamesBack", "0"),
                "streak": team_record.get("streak", {}).get("streakCode", ""),
                "offense": offense,
                "bullpen": pitching
            }
    return standings

# ─── Cache Management ─────────────────────────────────────────────────────────
def clear_all_cache():
    """Clear all cached data"""
    for f in os.listdir(CACHE_DIR):
        if f.endswith(".json"):
            os.remove(os.path.join(CACHE_DIR, f))
    print("[Cache] All cached data cleared.")

