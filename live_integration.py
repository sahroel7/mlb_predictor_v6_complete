"""
live_integration.py - Integrasi Live Monitor ke Sistem Prediksi Anda

Cara pakai di kode Anda yang sudah ada:

    # Di main.py atau file entry point Anda:
    from live_integration import run_live_monitoring

    # Setelah generate prediksi:
    predictions = [...]  # hasil prediksi Anda
    run_live_monitoring(predictions, duration_minutes=180)

Atau import class langsung:

    from live_integration import LiveGameMonitor

    monitor = LiveGameMonitor()
    for pred in predictions:
        monitor.add_prediction(pred)
    monitor.start(duration_minutes=180)
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
import time

# Import dari live_monitor.py
from live_monitor import (
    LiveMonitor, LiveGameState, PitcherDetail, Alert,
    get_live_state, get_pitcher_detail, get_game_status,
    calc_comeback_risk, mlb_api_get
)


@dataclass
class PredictionInput:
    """Format input yang diharapkan dari sistem prediksi Anda"""
    game_pk: int
    pick_team: str           # Nama tim yang dipilih (contoh: "New York Yankees")
    away_team: str           # Nama tim away
    home_team: str           # Nama tim home
    # Field lainnya opsional — sistem live hanya butuh 4 field di atas


class LiveGameMonitor:
    """
    Wrapper class untuk integrasi mudah ke sistem prediksi Anda.

    Usage:
        monitor = LiveGameMonitor()

        # Tambah dari prediksi Anda
        for pred in your_predictions:
            monitor.add_prediction(pred)

        # Atau tambah manual
        monitor.add_game(game_pk=745920, pick_team="Yankees", 
                        away_team="Red Sox", home_team="Yankees")

        # Mulai monitoring
        monitor.start(duration_minutes=180)
    """

    def __init__(self, poll_interval: int = 30, stagger: float = 2.0):
        self.monitor = LiveMonitor(poll_interval=poll_interval, stagger=stagger)
        self.game_info: Dict[int, Dict] = {}  # game_pk -> {home, away, pick_is_home}

    def add_prediction(self, prediction: Dict):
        """
        Tambah game dari prediksi Anda.

        prediction dict harus punya:
        - game_pk (int)
        - pick (str) — nama tim yang dipilih
        - away_team (str)
        - home_team (str)
        """
        game_pk = prediction.get("game_pk")
        pick = prediction.get("pick")
        away = prediction.get("away_team")
        home = prediction.get("home_team")

        if not all([game_pk, pick, away, home]):
            print(f"⚠️ Skipping invalid prediction: {prediction}")
            return

        self.add_game(int(game_pk), pick, away, home)

    def add_game(self, game_pk: int, pick_team: str, away_team: str, home_team: str):
        """Tambah game manual"""
        is_home = (pick_team == home_team)
        self.game_info[game_pk] = {
            "home": home_team,
            "away": away_team,
            "pick_is_home": is_home,
            "pick_team": pick_team,
        }
        self.monitor.games[game_pk] = pick_team
        print(f"✅ Added: {away_team} @ {home_team} | Pick: {pick_team}")

    def start(self, duration_minutes: int = 0):
        """Mulai monitoring (duration_minutes=0 berarti tanpa batas waktu / kontinu sampai Ctrl+C)"""
        if not self.monitor.games:
            print("❌ No games to monitor. Add games first.")
            return

        print("\n" + "=" * 70)
        print("  LIVE MONITOR INTEGRATED WITH YOUR PREDICTION SYSTEM")
        print("=" * 70)

        # Override internal method untuk pakai game_info kita
        self._run_custom_monitoring(duration_minutes)

    def _run_custom_monitoring(self, duration_minutes: int = 0):
        """Custom monitoring loop dengan integrasi game_info"""
        import requests
        from datetime import datetime

        MLB_API_BASE = "https://statsapi.mlb.com/api/v1.1"

        def api_get(endpoint):
            try:
                r = requests.get(f"{MLB_API_BASE}{endpoint}", timeout=15)
                return r.json() if r.status_code == 200 else None
            except:
                return None

        games = list(self.monitor.games.keys())
        poll_interval = self.monitor.poll_interval
        stagger = self.monitor.stagger

        dur_str = f"{duration_minutes}min" if duration_minutes > 0 else "Continuous (Tanpa Batas Waktu)"
        print(f"\nMonitoring {len(games)} games...")
        print(f"Poll: {poll_interval}s | Stagger: {stagger}s | Duration: {dur_str}")
        print("Tekan Ctrl+C untuk menghentikan pemantauan\n")

        start_time = time.time()
        cycle = 0

        try:
            while duration_minutes <= 0 or (time.time() - start_time) < (duration_minutes * 60):
                cycle += 1
                cycle_start = time.time()

                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] === CYCLE #{cycle} ===")
                print("-" * 70)

                for i, game_pk in enumerate(games):
                    # Stagger delay
                    if i > 0:
                        elapsed = time.time() - cycle_start
                        target = i * stagger
                        if elapsed < target:
                            time.sleep(target - elapsed)

                    info = self.game_info.get(game_pk, {})
                    check_time = datetime.now().strftime('%H:%M:%S')
                    away = info.get('away', '?')
                    home = info.get('home', '?')
                    pick = info.get('pick_team', '?')

                    print(f"  [{check_time}] [{i+1}/{len(games)}] {away} @ {home} (Pick: {pick})")

                    # Check status
                    data = api_get(f"/game/{game_pk}/feed/live")
                    if not data:
                        print(f"      ⚠️ API error")
                        continue

                    status = data.get("gameData", {}).get("status", {}).get("abstractGameState", "Unknown")

                    if status not in ["Live", "In Progress"]:
                        print(f"      Status: {status} — skipping")
                        continue

                    # Parse live data
                    live = data.get("liveData", {})
                    plays = live.get("plays", {})
                    current = plays.get("currentPlay", {})
                    about = current.get("about", {})
                    count = current.get("count", {})
                    linescore = live.get("linescore", {})

                    inning = about.get("inning", 0)
                    half = "top" if about.get("isTopInning") else "bottom"
                    outs = count.get("outs", 0)

                    teams_score = linescore.get("teams", {})
                    score_home = teams_score.get("home", {}).get("runs", 0)
                    score_away = teams_score.get("away", {}).get("runs", 0)

                    # Base runners
                    runners = []
                    offense = linescore.get("offense", {})
                    for base, key in [("1B", "first"), ("2B", "second"), ("3B", "third")]:
                        if offense.get(key):
                            runners.append(base)
                    runners_str = ", ".join(runners) if runners else "Empty"

                    # Batter & Pitcher info
                    defense = linescore.get("defense", {})
                    pitcher = defense.get("pitcher", {})
                    pitcher_name = pitcher.get("fullName", "?")

                    batter = offense.get("batter", {})
                    batter_name = batter.get("fullName", "?")

                    # Determine pick score and deficit
                    is_home = info.get("pick_is_home", False)
                    pick_score = score_home if is_home else score_away
                    opp_score = score_away if is_home else score_home
                    deficit = abs(pick_score - opp_score)
                    winning = pick_score > opp_score

                    # Simple alert logic
                    if winning and inning >= 7 and deficit <= 2:
                        print(f"      ⚠️  CASH OUT WARNING: Lead {deficit} run in inning {inning}")
                        print(f"         Score: {score_away}-{score_home} | Runners: {runners_str} | Pitcher: {pitcher_name} | Batter: {batter_name}")
                    elif not winning and 5 <= inning <= 7 and deficit <= 2:
                        print(f"      📈 BUY LIVE OPPORTUNITY: Down {deficit} in inning {inning}")
                        print(f"         Score: {score_away}-{score_home} | Runners: {runners_str} | Pitcher: {pitcher_name} | Batter: {batter_name}")
                    elif winning and deficit >= 3 and inning >= 8:
                        print(f"      ✅ HOLD: Safe lead {deficit} in inning {inning}")
                    else:
                        print(f"      Score: {score_away}-{score_home} | Inning {inning} {half} | Runners: {runners_str} | Outs: {outs} | Pitcher: {pitcher_name} | Batter: {batter_name} | OK")

                # Wait
                elapsed = time.time() - cycle_start
                wait = max(0, poll_interval - elapsed)
                if wait > 0:
                    print(f"\n  [Waiting {wait:.0f}s...]")
                    time.sleep(wait)

        except KeyboardInterrupt:
            print("\n\nStopped.")

        runtime = (time.time() - start_time) / 60
        print(f"\n{'='*60}")
        print(f"Done. Runtime: {runtime:.1f} minutes | Cycles: {cycle}")
        print(f"{'='*60}")


def run_live_monitoring(predictions: List[Dict], duration_minutes: int = 180,
                        poll_interval: int = 30, stagger: float = 2.0):
    """
    Fungsi one-liner untuk integrasi ke sistem Anda.

    Args:
        predictions: List of dicts dengan keys: game_pk, pick, away_team, home_team
        duration_minutes: Berapa lama monitoring
        poll_interval: Interval antar cycle (detik)
        stagger: Jeda antar game (detik)
    """
    monitor = LiveGameMonitor(poll_interval=poll_interval, stagger=stagger)

    for pred in predictions:
        monitor.add_prediction(pred)

    monitor.start(duration_minutes)


# ─── Contoh penggunaan standalone ────────────────────────────────────────────
if __name__ == "__main__":
    # Contoh: monitor game manual
    monitor = LiveGameMonitor()

    # Tambah game (ganti dengan game PK yang sebenarnya)
    monitor.add_game(
        game_pk=745920,
        pick_team="New York Yankees",
        away_team="Boston Red Sox",
        home_team="New York Yankees"
    )

    monitor.start(duration_minutes=60)
