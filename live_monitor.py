"""
live_monitor.py - MLB Live Play-by-Play Monitor v1.0
Standalone module untuk monitoring live MLB games.
Bisa di-integrasikan ke sistem prediksi apapun.

Cara pakai:
    from live_monitor import LiveMonitor

    monitor = LiveMonitor()
    monitor.add_game(game_pk=745920, pick_team="New York Yankees")
    monitor.add_game(game_pk=745921, pick_team="Los Angeles Dodgers")
    monitor.start_monitoring(duration_minutes=180)

Atau via CLI:
    py live_monitor.py --games 745920,745921 --picks "Yankees,Dodgers"
"""

import requests
import json
import time
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

MLB_API_BASE = "https://statsapi.mlb.com/api/v1"
LIVE_POLL_INTERVAL = 30  # seconds between full cycles
STAGGER_DELAY = 2.0      # seconds between each game check


# ─── Data Classes ──────────────────────────────────────────────────────────
@dataclass
class LiveGameState:
    game_pk: int
    inning: int
    half_inning: str          # "top" or "bottom"
    outs: int
    balls: int
    strikes: int
    score_home: int
    score_away: int
    runners: Dict              # {"first": {...}, "second": {...}, "third": {...}}
    current_pitcher_home: Optional[Dict]
    current_pitcher_away: Optional[Dict]
    current_batter: Optional[Dict]
    game_status: str           # "Live", "Final", "Scheduled", etc.
    last_play: Optional[str]

    def format_score(self) -> str:
        return f"{self.score_away}-{self.score_home}"

    def format_runners(self) -> str:
        bases = []
        if self.runners.get("first"):
            bases.append("1B")
        if self.runners.get("second"):
            bases.append("2B")
        if self.runners.get("third"):
            bases.append("3B")
        return ", ".join(bases) if bases else "Empty"


@dataclass
class PitcherDetail:
    name: str
    era: float
    whip: Optional[float]
    strikeouts: int
    walks: int
    hits: int
    runs: int
    throws: str          # "L" or "R"
    ip: str              # Innings pitched in this game
    total_pitches: int

    def format(self) -> str:
        return (f"{self.name} (ERA: {self.era}, WHIP: {self.whip or 'N/A'}, "
                f"K: {self.strikeouts}, BB: {self.walks}, H: {self.hits}, "
                f"R: {self.runs}, Hand: {self.throws}, IP: {self.ip})")


@dataclass
class BatterDetail:
    name: str
    ops: float
    avg: float
    home_runs: int
    rbi: int
    bats: str          # "L", "R", or "S"

    def format(self) -> str:
        return f"{self.name} (OPS: {self.ops:.3f}, AVG: {self.avg:.3f}, HR: {self.home_runs}, Hand: {self.bats})"


@dataclass
class Alert:
    alert_type: str      # "CASH_OUT", "BUY_LIVE", "HOLD", "GAME_STARTED", "PITCHING_CHANGE"
    urgency: str         # "CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"
    game_pk: int
    game_desc: str
    reason: str
    pitcher_our: Optional[PitcherDetail]
    pitcher_opp: Optional[PitcherDetail]
    base_runners: str
    outs: int
    comeback_risk: float
    timestamp: str
    batter_current: Optional[BatterDetail] = None
    batter_on_deck: Optional[BatterDetail] = None

    def print_full(self):
        emoji = {"CASH_OUT": "🚨", "BUY_LIVE": "📈", "HOLD": "✅", 
                 "GAME_STARTED": "🎮", "PITCHING_CHANGE": "⚾"}.get(self.alert_type, "⚠️")
        color = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", 
                 "LOW": "🟢", "INFO": "🔵"}.get(self.urgency, "⚪")

        print()
        print("=" * 70)
        print(f"{emoji} {color} ALERT: {self.alert_type} — {self.urgency}")
        print("=" * 70)
        print(f"📍 {self.game_desc}")
        print(f"⏰ {self.timestamp}")
        print()
        print("📋 REASON:")
        print(self.reason)

        if self.pitcher_our:
            print()
            print("─" * 70)
            print("⚾ PITCHER KITA (yang melindungi / yang akan masuk):")
            print(f"   {self.pitcher_our.format()}")

        if self.pitcher_opp:
            print()
            print("─" * 70)
            print("⚾ PITCHER LAWAN:")
            print(f"   {self.pitcher_opp.format()}")

        if self.batter_current:
            print()
            print("─" * 70)
            print("🏏 PEMUKUL AKTIF (At-Bat):")
            print(f"   {self.batter_current.format()}")

        if self.batter_on_deck:
            print(f"🏏 PEMUKUL ANTRAN (On-Deck):")
            print(f"   {self.batter_on_deck.format()}")

        if self.base_runners:
            print()
            print("─" * 70)
            print(f"🏃 BASE RUNNERS: {self.base_runners}")
            print(f"   Outs: {self.outs}")

        if self.comeback_risk > 0:
            print()
            print("─" * 70)
            print(f"📊 COMEBACK RISK: {self.comeback_risk:.1%}")

        print("=" * 70)


# ─── API Helpers ───────────────────────────────────────────────────────────
def mlb_api_get(endpoint: str, timeout: int = 15) -> Optional[Dict]:
    """Simple GET to MLB Stats API"""
    base = "https://statsapi.mlb.com/api/v1.1" if "/feed/live" in endpoint else MLB_API_BASE
    url = f"{base}{endpoint}"
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  [API Error] {url}: {e}")
        return None


def get_live_state(game_pk: int) -> Optional[LiveGameState]:
    """Fetch live game state from MLB API"""
    data = mlb_api_get(f"/game/{game_pk}/feed/live")
    if not data:
        return None

    try:
        live = data.get("liveData", {})
        plays = live.get("plays", {})
        current = plays.get("currentPlay", {})
        about = current.get("about", {})
        matchup = current.get("matchup", {})
        count = current.get("count", {})
        linescore = live.get("linescore", {})

        # Score
        teams = linescore.get("teams", {})
        score_home = teams.get("home", {}).get("runs", 0)
        score_away = teams.get("away", {}).get("runs", 0)

        # Base runners
        runners = {"first": None, "second": None, "third": None}
        offense = linescore.get("offense", {})
        for base, key in [("first", "first"), ("second", "second"), ("third", "third")]:
            runner = offense.get(key, {})
            if runner and runner.get("id"):
                runners[base] = {
                    "id": runner.get("id"),
                    "name": runner.get("fullName", "?"),
                }

        # Current pitchers from defense
        defense = linescore.get("defense", {})
        pitcher_home = defense.get("pitcher", {})
        pitcher_away = None  # Will get from boxscore if needed

        # Current batter
        batter = matchup.get("batter", {})
        current_batter = {
            "id": batter.get("id"),
            "name": batter.get("fullName", "?"),
            "hand": matchup.get("batSide", {}).get("code", "R"),
        } if batter else None

        # Last play
        all_plays = plays.get("allPlays", [])
        last_play = None
        if all_plays:
            last = all_plays[-1]
            last_play = last.get("result", {}).get("description", "")

        # Game status
        status = data.get("gameData", {}).get("status", {})
        abstract = status.get("abstractGameState", "Unknown")

        return LiveGameState(
            game_pk=game_pk,
            inning=about.get("inning", 0),
            half_inning="top" if about.get("isTopInning") else "bottom",
            outs=count.get("outs", 0),
            balls=count.get("balls", 0),
            strikes=count.get("strikes", 0),
            score_home=score_home,
            score_away=score_away,
            runners=runners,
            current_pitcher_home=pitcher_home if pitcher_home else None,
            current_pitcher_away=pitcher_away,
            current_batter=current_batter,
            game_status=abstract,
            last_play=last_play,
        )
    except Exception as e:
        print(f"  [Parse Error] Game {game_pk}: {e}")
        return None


def get_pitcher_detail(game_pk: int, team_type: str) -> Optional[PitcherDetail]:
    """Get detailed pitcher stats from boxscore"""
    data = mlb_api_get(f"/game/{game_pk}/boxscore")
    if not data:
        return None

    try:
        team = data.get("teams", {}).get(team_type, {})
        pitchers = team.get("pitchers", [])
        if not pitchers:
            return None

        # Current pitcher = last one in list
        pid = pitchers[-1]
        players = team.get("players", {})
        p_data = players.get(f"ID{pid}", {})

        person = p_data.get("person", {})
        stats = p_data.get("stats", {}).get("pitching", {})
        season = p_data.get("seasonStats", {}).get("pitching", {})

        return PitcherDetail(
            name=person.get("fullName", f"Pitcher {pid}"),
            era=float(season.get("era", 99)) if season.get("era") else 99.0,
            whip=float(season.get("whip")) if season.get("whip") else None,
            strikeouts=int(stats.get("strikeOuts", 0)),
            walks=int(stats.get("baseOnBalls", 0)),
            hits=int(stats.get("hits", 0)),
            runs=int(stats.get("runs", 0)),
            throws=person.get("pitchHand", {}).get("code", "R"),
            ip=stats.get("inningsPitched", "0"),
            total_pitches=int(stats.get("pitchesThrown", 0)),
        )
    except Exception as e:
        print(f"  [Pitcher Error] Game {game_pk}: {e}")
        return None


def get_batter_detail(game_pk: int, team_type: str, player_id: Optional[int] = None) -> Optional[BatterDetail]:
    """Get detailed batter stats from boxscore"""
    if not player_id:
        return None
    data = mlb_api_get(f"/game/{game_pk}/boxscore")
    if not data:
        return None

    try:
        team = data.get("teams", {}).get(team_type, {})
        players = team.get("players", {})
        b_data = players.get(f"ID{player_id}", {})
        if not b_data:
            return None

        person = b_data.get("person", {})
        season = b_data.get("seasonStats", {}).get("batting", {})

        ops_val = season.get("ops")
        avg_val = season.get("avg")

        ops = float(ops_val) if ops_val is not None else 0.730
        avg = float(avg_val) if avg_val is not None else 0.245

        return BatterDetail(
            name=person.get("fullName", f"Batter {player_id}"),
            ops=ops,
            avg=avg,
            home_runs=int(season.get("homeRuns", 0)),
            rbi=int(season.get("rbi", 0)),
            bats=person.get("batSide", {}).get("code", "R")
        )
    except Exception as e:
        return None


def get_game_status(game_pk: int) -> str:
    """Check if game is Live, Final, Scheduled, etc."""
    data = mlb_api_get(f"/game/{game_pk}/feed/live")
    if not data:
        return "Unknown"
    status = data.get("gameData", {}).get("status", {})
    return status.get("abstractGameState", "Unknown")


# ─── Risk Calculator ─────────────────────────────────────────────────────────
def calc_comeback_risk(inning: int, deficit: int, runners_count: int, outs: int,
                       batter_ops: float = 0.730, on_deck_ops: float = 0.730) -> float:
    """Calculate comeback probability based on FanGraphs data + Batter Threat Matrix"""
    if deficit <= 0:
        return 0.0

    base_rates = {6: 0.133, 7: 0.090, 8: 0.046, 9: 0.025}
    base = base_rates.get(inning, 0.01)

    mult = {1: 2.0, 2: 1.0, 3: 0.5}.get(deficit, 0.1)
    runner_mult = 1.0 + (runners_count * 0.3)
    outs_mult = 1.0 + ((2 - outs) * 0.2)

    # Batter Threat Multiplier (AVG OPS = 0.730)
    avg_ops = (batter_ops + on_deck_ops) / 2.0
    batter_mult = max(0.5, min(1.5, avg_ops / 0.730))

    return min(base * mult * runner_mult * outs_mult * batter_mult, 0.50)


# ─── Main Monitor Class ─────────────────────────────────────────────────────
class LiveMonitor:
    """
    Main class for live MLB game monitoring.

    Usage:
        monitor = LiveMonitor()
        monitor.add_game(745920, "Yankees")
        monitor.add_game(745921, "Dodgers")
        monitor.start_monitoring(duration_minutes=180)
    """

    def __init__(self, poll_interval: int = LIVE_POLL_INTERVAL, 
                 stagger: float = STAGGER_DELAY):
        self.games: Dict[int, str] = {}  # game_pk -> pick_team
        self.poll_interval = poll_interval
        self.stagger = stagger
        self.alerts: List[Alert] = []
        self.last_pitchers: Dict[int, Tuple[Optional[int], Optional[int]]] = {}  # game_pk -> (home_pid, away_pid)
        self.alerted_innings: Dict[int, Dict[str, int]] = {}  # game_pk -> {alert_type: inning}

    def add_game(self, game_pk: int, pick_team: str):
        """Add a game to monitor. pick_team = team name you bet on."""
        self.games[game_pk] = pick_team
        print(f"✅ Added Game {game_pk} — Pick: {pick_team}")

    def remove_game(self, game_pk: int):
        """Remove a game from monitoring"""
        if game_pk in self.games:
            del self.games[game_pk]
            print(f"🗑️ Removed Game {game_pk}")

    def _is_pick_home(self, game_pk: int, state: LiveGameState) -> bool:
        """Check if our pick is the home team"""
        # We need to know team names. Get from schedule or store when adding.
        # For simplicity, we'll store team names when adding.
        return False  # Override below

    def _analyze(self, game_pk: int, state: LiveGameState, 
                 pick_team: str, is_home: bool) -> Optional[Alert]:
        """Analyze game and generate alert if needed"""

        pick_score = state.score_home if is_home else state.score_away
        opp_score = state.score_away if is_home else state.score_home
        deficit = abs(pick_score - opp_score)
        winning = pick_score > opp_score

        # Get pitcher details
        our_team_type = "home" if is_home else "away"
        opp_team_type = "away" if is_home else "home"

        our_pitcher = get_pitcher_detail(game_pk, our_team_type)
        opp_pitcher = get_pitcher_detail(game_pk, opp_team_type)

        # Get batter & on-deck details
        batter_id = state.current_batter.get("id") if state.current_batter else None
        opp_batter = get_batter_detail(game_pk, opp_team_type, batter_id)
        our_batter = get_batter_detail(game_pk, our_team_type, batter_id)

        # Detect pitching change
        current_home_pid = state.current_pitcher_home.get("id") if state.current_pitcher_home else None
        last_home, last_away = self.last_pitchers.get(game_pk, (None, None))

        pitching_changed = False
        if current_home_pid and last_home and current_home_pid != last_home:
            pitching_changed = True

        self.last_pitchers[game_pk] = (current_home_pid, None)

        # Format game description
        game_desc = f"Game {game_pk} | Inning {state.inning} {state.half_inning} | Score: {state.format_score()}"

        # === ALERT 1: PITCHING CHANGE ===
        if pitching_changed and our_pitcher:
            return Alert(
                alert_type="PITCHING_CHANGE",
                urgency="HIGH",
                game_pk=game_pk,
                game_desc=game_desc,
                reason=f"⚾ PITCHING CHANGE! {our_pitcher.name} masuk (ERA: {our_pitcher.era})",
                pitcher_our=our_pitcher,
                pitcher_opp=opp_pitcher,
                base_runners=state.format_runners(),
                outs=state.outs,
                comeback_risk=0.0,
                timestamp=datetime.now().strftime("%H:%M:%S"),
                batter_current=opp_batter
            )

        # === ALERT 2: CASH OUT ===
        if winning and state.inning >= 6 and our_pitcher and our_pitcher.era > 4.50:
            opp_b_ops = opp_batter.ops if opp_batter else 0.730
            risk = calc_comeback_risk(state.inning, deficit, 
                                      sum(1 for r in state.runners.values() if r), 
                                      state.outs,
                                      batter_ops=opp_b_ops)

            # Suppress false alert if opponent batter is very weak (OPS < 0.630) and risk < 0.25
            if not (opp_batter and opp_batter.ops < 0.630 and risk < 0.25):
                alerted = self.alerted_innings.get(game_pk, {}).get("CASH_OUT", -1)
                if risk > 0.20 and state.inning != alerted:
                    self.alerted_innings.setdefault(game_pk, {})["CASH_OUT"] = state.inning

                    reasons = [f"⚾ Pitcher kita ({our_pitcher.name}) ERA {our_pitcher.era} — lemah!"]
                    if opp_batter:
                        reasons.append(f"🏏 Batter lawan ({opp_batter.name}) OPS {opp_batter.ops:.3f} sedang di-plate!")
                    if opp_pitcher and opp_pitcher.era < 3.50:
                        reasons.append(f"⚾ Pitcher lawan ({opp_pitcher.name}) ERA {opp_pitcher.era} — kuat!")
                    if state.runners:
                        reasons.append(f"🏃 Runners: {state.format_runners()}")
                    reasons.append(f"📊 Comeback risk: {risk:.1%}")

                    return Alert(
                        alert_type="CASH_OUT",
                        urgency="CRITICAL" if risk > 0.30 else "HIGH",
                        game_pk=game_pk,
                        game_desc=game_desc,
                        reason="\n".join(reasons),
                        pitcher_our=our_pitcher,
                        pitcher_opp=opp_pitcher,
                        base_runners=state.format_runners(),
                        outs=state.outs,
                        comeback_risk=risk,
                        timestamp=datetime.now().strftime("%H:%M:%S"),
                        batter_current=opp_batter
                    )

        # === ALERT 3: BUY LIVE ===
        if not winning and 5 <= state.inning <= 7 and deficit <= 2:
            if opp_pitcher and opp_pitcher.era > 4.20:
                our_b_ops = our_batter.ops if our_batter else 0.730
                # Trigger Buy Live especially when our hitters have solid threat (OPS >= 0.700)
                if our_b_ops >= 0.700:
                    alerted = self.alerted_innings.get(game_pk, {}).get("BUY_LIVE", -1)
                    if state.inning != alerted:
                        self.alerted_innings.setdefault(game_pk, {})["BUY_LIVE"] = state.inning

                        reasons = [f"⚾ Lawan masuk pitcher jelek ({opp_pitcher.name}) ERA {opp_pitcher.era}!"]
                        if our_batter:
                            reasons.append(f"🏏 Pemukul inti kita ({our_batter.name}) OPS {our_batter.ops:.3f} siap memukul!")
                        if our_pitcher and our_pitcher.era < 3.50:
                            reasons.append(f"⚾ Pitcher kita ({our_pitcher.name}) ERA {our_pitcher.era} — kuat!")
                        reasons.append(f"📊 Deficit hanya {deficit} run di inning {state.inning}")

                        return Alert(
                            alert_type="BUY_LIVE",
                            urgency="HIGH",
                            game_pk=game_pk,
                            game_desc=game_desc,
                            reason="\n".join(reasons),
                            pitcher_our=our_pitcher,
                            pitcher_opp=opp_pitcher,
                            base_runners=state.format_runners(),
                            outs=state.outs,
                            comeback_risk=0.0,
                            timestamp=datetime.now().strftime("%H:%M:%S"),
                            batter_current=our_batter
                        )

        # === ALERT 4: HOLD ===
        if winning and deficit >= 3 and state.inning >= 8:
            alerted = self.alerted_innings.get(game_pk, {}).get("HOLD", -1)
            if state.inning != alerted:
                self.alerted_innings.setdefault(game_pk, {})["HOLD"] = state.inning
                return Alert(
                    alert_type="HOLD",
                    urgency="LOW",
                    game_pk=game_pk,
                    game_desc=game_desc,
                    reason=f"✅ Unggul {deficit} run di inning {state.inning}. Aman.",
                    pitcher_our=our_pitcher,
                    pitcher_opp=opp_pitcher,
                    base_runners=state.format_runners(),
                    outs=state.outs,
                    comeback_risk=0.0,
                    timestamp=datetime.now().strftime("%H:%M:%S")
                )

        return None

    def start_monitoring(self, duration_minutes: int = 180):
        """Start monitoring all added games"""
        print("\n" + "=" * 70)
        print("  MLB LIVE MONITOR v1.0")
        print("=" * 70)
        print(f"Games: {len(self.games)}")
        print(f"Poll interval: {self.poll_interval}s")
        print(f"Stagger delay: {self.stagger}s")
        print(f"Duration: {duration_minutes} minutes")
        print("Press Ctrl+C to stop\n")

        # First, get team names for each game
        game_info = {}
        for game_pk in self.games:
            data = mlb_api_get(f"/game/{game_pk}/feed/live")
            if data:
                teams = data.get("gameData", {}).get("teams", {})
                home = teams.get("home", {}).get("name", "Home")
                away = teams.get("away", {}).get("name", "Away")
                game_info[game_pk] = {"home": home, "away": away}

                # Check if pick is home or away
                pick = self.games[game_pk]
                is_home = (pick == home)
                game_info[game_pk]["pick_is_home"] = is_home
                game_info[game_pk]["pick_team"] = pick
            else:
                game_info[game_pk] = {"home": "?", "away": "?", "pick_is_home": False, "pick_team": self.games[game_pk]}

        start_time = time.time()
        cycle = 0

        try:
            while (time.time() - start_time) < (duration_minutes * 60):
                cycle += 1
                cycle_start = time.time()

                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] === CYCLE #{cycle} ===")
                print("-" * 70)

                for i, game_pk in enumerate(self.games):
                    # Stagger
                    if i > 0:
                        elapsed = time.time() - cycle_start
                        target = i * self.stagger
                        if elapsed < target:
                            time.sleep(target - elapsed)

                    info = game_info[game_pk]
                    check_time = datetime.now().strftime('%H:%M:%S')
                    print(f"  [{check_time}] [{i+1}/{len(self.games)}] {info['away']} @ {info['home']}")

                    # Check status first
                    status = get_game_status(game_pk)
                    if status not in ["Live", "In Progress"]:
                        print(f"      Status: {status} — skipping")
                        continue

                    # Get live state
                    state = get_live_state(game_pk)
                    if not state:
                        print(f"      ⚠️ Failed to fetch live data")
                        continue

                    # Analyze
                    alert = self._analyze(game_pk, state, info["pick_team"], info["pick_is_home"])

                    if alert:
                        self.alerts.append(alert)
                        alert.print_full()
                    else:
                        print(f"      {state.away_team if hasattr(state, 'away_team') else info['away']} {state.score_away}-{state.score_home} {state.home_team if hasattr(state, 'home_team') else info['home']}")
                        print(f"      Inning {state.inning} {state.half_inning} | Runners: {state.format_runners()} | Outs: {state.outs} | OK")

                # Wait for next cycle
                elapsed = time.time() - cycle_start
                wait = max(0, self.poll_interval - elapsed)
                if wait > 0:
                    print(f"\n  [Waiting {wait:.0f}s for next cycle...]")
                    time.sleep(wait)

        except KeyboardInterrupt:
            print("\n\nStopped by user.")

        # Summary
        print(f"\n{'='*60}")
        print("MONITORING SUMMARY")
        print(f"{'='*60}")
        print(f"Runtime: {(time.time()-start_time)/60:.1f} minutes")
        print(f"Cycles: {cycle}")
        print(f"Alerts: {len(self.alerts)}")

        by_type = {}
        for a in self.alerts:
            by_type[a.alert_type] = by_type.get(a.alert_type, 0) + 1
        for t, c in by_type.items():
            print(f"  {t}: {c}")

        return self.alerts


# ─── CLI Entry Point ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="MLB Live Play-by-Play Monitor")
    parser.add_argument("--games", "-g", required=True, help="Comma-separated game PKs, e.g., 745920,745921")
    parser.add_argument("--picks", "-p", required=True, help="Comma-separated pick teams, e.g., Yankees,Dodgers")
    parser.add_argument("--duration", "-d", type=int, default=180, help="Monitoring duration in minutes")
    parser.add_argument("--stagger", "-s", type=float, default=2.0, help="Delay between games in seconds")
    parser.add_argument("--interval", "-i", type=int, default=30, help="Poll interval in seconds")

    args = parser.parse_args()

    game_pks = [int(x.strip()) for x in args.games.split(",")]
    picks = [x.strip() for x in args.picks.split(",")]

    if len(game_pks) != len(picks):
        print("Error: Number of games and picks must match!")
        return

    monitor = LiveMonitor(poll_interval=args.interval, stagger=args.stagger)
    for pk, pick in zip(game_pks, picks):
        monitor.add_game(pk, pick)

    monitor.start_monitoring(args.duration)


if __name__ == "__main__":
    main()
