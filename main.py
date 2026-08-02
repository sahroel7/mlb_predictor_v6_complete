"""
main.py - MLB Prediction System v6.0 Entry Point
Commands: predict, backtest, compare, tune, interactive
"""

import sys
import os
import json
import argparse
from datetime import datetime
from typing import Optional

# Ensure imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Ensure UTF-8 encoding on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


from config import print_section, get_today_date, DATA_DIR, save_json
from data_fetchers import get_all_games, get_team_standings, clear_all_cache
from models import EnsembleModel
from game_fetcher import fetch_morning_data, fetch_afternoon_data, compare_morning_afternoon, print_comparison_report
from backtester import run_backtest, save_backtest_results
from output_formatter import print_predictions, format_backtest_summary, format_verification_report
from database import save_predictions_to_db, verify_predictions
from live_integration import run_live_monitoring


def cmd_predict(date_str: Optional[str] = None, verbose: bool = False):
    """Generate predictions for today's games"""
    print_section("MLB Prediction System v6.0")
    target_date = date_str or get_today_date()
    print(f"Date: {target_date}")
    print("Fetching games and data...")

    games = get_all_games(date_str)
    if not games:
        print("\n❌ No games found for this date.")
        return

    print(f"Found {len(games)} games.")

    # Fetch standings for momentum calculation
    print("Fetching team standings...")
    standings = get_team_standings()

    # Initialize model
    model = EnsembleModel()

    # Load tuned weights if available
    weights_file = os.path.join(DATA_DIR, "tuned_weights.json")
    if os.path.exists(weights_file):
        with open(weights_file, "r") as f:
            tuned = json.load(f)
            model.weights = tuned
            print("Using tuned weights from previous optimization.")

    # Generate predictions
    print("\nGenerating predictions...")
    predictions = []
    for game in games:
        pred = model.predict(game, standings)
        pred["date"] = target_date
        predictions.append(pred)

    # Setelah generate prediksi
    monitor_choice = input("Start live monitoring? (y/n): ").strip().lower()
    if monitor_choice == "y":
        print("Starting live monitoring...")
        run_live_monitoring(predictions, duration_minutes=180)

    # Display results
    print_predictions(predictions, verbose=verbose)

    # Save predictions to JSON
    pred_file = os.path.join(DATA_DIR, f"predictions_{target_date.replace('/', '')}.json")
    save_json(pred_file, predictions)
    print(f"\n💾 Predictions saved to {pred_file}")

    # Save to SQLite Database (UPSERT)
    save_predictions_to_db(predictions, games)
    print("🗄️ Predictions saved/updated in SQLite database (mlb_predictions.db)")


def cmd_verify(date_str: Optional[str] = None):
    """Verify predictions against actual game results"""
    print_section("MLB Verification Mode")
    print(f"Checking predictions in database...")

    verified_results, target_date = verify_predictions(date_str)
    if not verified_results:
        print(f"\n❌ No predictions found in database for date: {target_date or date_str}.")
        return

    report = format_verification_report(verified_results, target_date)
    print(report)




def cmd_backtest(num_games: int = 300):
    """Run backtest on simulated games"""
    print_section("Backtest Mode")
    print(f"Running {num_games} game simulation...")

    results = run_backtest(num_games)
    save_backtest_results(results)
    print(format_backtest_summary(results))


def cmd_compare(date_str: Optional[str] = None):
    """Compare morning vs afternoon data"""
    print_section("Morning vs Afternoon Comparison")

    morning = fetch_morning_data(date_str)
    print("\n[Simulating afternoon update...]")
    afternoon = fetch_afternoon_data(date_str)

    changes = compare_morning_afternoon(morning, afternoon)
    print_comparison_report(changes)


def cmd_tune(num_games: int = 300):
    """Tune ensemble weights using backtest"""
    print_section("Weight Tuning Mode")
    print(f"Running {num_games} game backtest for optimization...")

    # Generate backtest data
    model = EnsembleModel()
    backtest_data = []

    from backtester import generate_simulated_game, simulate_actual_result
    import random

    for i in range(num_games):
        game = generate_simulated_game(i + 1)
        standings = {
            game.away_team_id: {"win_pct": random.uniform(0.35, 0.65)},
            game.home_team_id: {"win_pct": random.uniform(0.35, 0.65)},
        }
        pred = model.predict(game, standings)
        actual = simulate_actual_result(pred)
        backtest_data.append({
            "home_win_prob": pred["home_win_prob"],
            "actual_home_win": actual
        })

    print("\nOptimizing weights...")
    optimized = model.tune_weights(backtest_data)

    print("\n📊 Optimized Weights:")
    for key, val in optimized.items():
        print(f"  {key}: {val:.3f}")

    # Save tuned weights
    weights_file = os.path.join(DATA_DIR, "tuned_weights.json")
    save_json(weights_file, optimized)
    print(f"\n💾 Tuned weights saved to {weights_file}")

    # Re-run backtest with new weights
    print("\nRe-running backtest with optimized weights...")
    model2 = EnsembleModel(weights=optimized)
    results = run_backtest(num_games, weights=optimized)
    save_backtest_results(results, "backtest_tuned.json")


def cmd_live_monitor_today(date_str: Optional[str] = None, duration: int = 0):
    """Run live play-by-play monitoring for active/today's games (auto-detects US time & active live games)"""
    print_section("MLB Live Game Monitor v1.0")
    
    from datetime import datetime, timedelta, timezone
    us_date_str = (datetime.now(timezone.utc) - timedelta(hours=4)).strftime("%Y-%m-%d")
    local_date_str = get_today_date()
    
    target_date = date_str or us_date_str
    print(f"Detecting MLB Active Schedule for US Date: {target_date} (Local Date: {local_date_str})")
    
    pred_file = os.path.join(DATA_DIR, f"predictions_{target_date.replace('/', '')}.json")

    # Jika file prediksi untuk tanggal US belum ada, coba periksa tanggal lokal
    if not os.path.exists(pred_file) and local_date_str != target_date:
        local_pred_file = os.path.join(DATA_DIR, f"predictions_{local_date_str.replace('/', '')}.json")
        if os.path.exists(local_pred_file):
            pred_file = local_pred_file
            target_date = local_date_str

    if not os.path.exists(pred_file):
        print(f"\n❌ Prediksi untuk tanggal {target_date} belum ditemukan. Membuat prediksi otomatis...")
        cmd_predict(target_date)

    if os.path.exists(pred_file):
        from config import load_json
        predictions = load_json(pred_file)
        if predictions:
            run_live_monitoring(predictions, duration_minutes=duration)
        else:
            print("❌ File prediksi kosong.")


def cmd_live_monitor_manual():
    """Manual live monitoring by entering Game PK and pick team"""
    print_section("MLB Live Game Monitor (Manual Input)")
    game_pk_str = input("Masukkan Game PK (contoh: 824651 atau pisahkan koma): ").strip()
    if not game_pk_str:
        print("❌ Game PK tidak boleh kosong.")
        return

    from live_integration import LiveGameMonitor
    monitor = LiveGameMonitor()

    pks = [p.strip() for p in game_pk_str.split(",") if p.strip().isdigit()]
    if not pks:
        print("❌ Game PK tidak valid.")
        return

    for pk in pks:
        pick = input(f"Masukkan nama tim pilihan (Pick) untuk Game PK {pk}: ").strip()
        away = input(f"Masukkan nama Away Team untuk Game PK {pk}: ").strip()
        home = input(f"Masukkan nama Home Team untuk Game PK {pk}: ").strip()
        monitor.add_game(int(pk), pick or "Pick", away or "Away", home or "Home")

    dur = input("Durasi monitoring dalam menit (default 180): ").strip()
    duration = int(dur) if dur and dur.isdigit() else 180
    monitor.start(duration_minutes=duration)


def cmd_interactive():
    """Interactive mode with numbered menu options"""
    while True:
        print()
        print("=" * 65)
        print("  ⚾ MLB PREDICTION SYSTEM v6.0 - INTERACTIVE MENU ⚾")
        print("=" * 65)
        print("  1. Predict Today's Games (Save/Update DB)")
        print("  2. Predict Specific Date (Save/Update DB)")
        print("  3. Verify Today's Predictions (Database Report)")
        print("  4. Verify Specific Date Predictions (Database Report)")
        print("  5. Live Monitor Today's Predictions (Real-Time Play-by-Play)")
        print("  6. Live Monitor Manual Game PK (Real-Time Input Custom)")
        print("  7. Backtest Simulation (No DB Save)")
        print("  8. Compare Morning vs Afternoon Data")
        print("  9. Tune Model Weights")
        print(" 10. Clear Cache Data")
        print(" 11. Exit / Quit")
        print("=" * 65)

        choice = input("\nPilih opsi (1-11): ").strip().lower()

        if choice in ["11", "exit", "quit", "q"]:
            print("Goodbye!")
            break
        elif choice == "1":
            verbose = input("Verbose output? (y/n, default n): ").strip().lower() == "y"
            cmd_predict(get_today_date(), verbose)
        elif choice == "2":
            date = input("Masukkan tanggal (YYYY-MM-DD): ").strip()
            if not date:
                print("❌ Tanggal tidak boleh kosong.")
                continue
            verbose = input("Verbose output? (y/n, default n): ").strip().lower() == "y"
            cmd_predict(date, verbose)
        elif choice == "3":
            cmd_verify(get_today_date())
        elif choice == "4":
            date = input("Masukkan tanggal verifikasi (YYYY-MM-DD): ").strip()
            if not date:
                print("❌ Tanggal tidak boleh kosong.")
                continue
            cmd_verify(date)
        elif choice == "5":
            cmd_live_monitor_today()
        elif choice == "6":
            cmd_live_monitor_manual()
        elif choice == "7":
            n = input("Jumlah game simulasi backtest (default 300): ").strip()
            cmd_backtest(int(n) if n and n.isdigit() else 300)
        elif choice == "8":
            date = input("Tanggal komparasi (YYYY-MM-DD, blank=today): ").strip()
            cmd_compare(date or None)
        elif choice == "9":
            n = input("Jumlah game untuk tuning (default 300): ").strip()
            cmd_tune(int(n) if n and n.isdigit() else 300)
        elif choice == "10":
            clear_all_cache()
        else:
            print("❌ Opsi tidak valid! Harap pilih angka antara 1-11.")


def main():
    parser = argparse.ArgumentParser(description="MLB Prediction System v6.0")
    parser.add_argument("command", nargs="?", default="predict",
                        choices=["predict", "verify", "backtest", "compare", "tune", "monitor", "interactive"],
                        help="Command to run")
    parser.add_argument("--date", "-d", help="Date for prediction (YYYY-MM-DD)")
    parser.add_argument("--games", "-g", type=int, default=300, help="Number of games for backtest")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()


    if args.command == "predict":
        cmd_predict(args.date, args.verbose)
    elif args.command == "verify":
        cmd_verify(args.date)
    elif args.command == "backtest":
        cmd_backtest(args.games)
    elif args.command == "compare":
        cmd_compare(args.date)
    elif args.command == "tune":
        cmd_tune(args.games)
    elif args.command == "monitor":
        cmd_live_monitor_today(args.date)
    elif args.command == "interactive":
        cmd_interactive()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()


