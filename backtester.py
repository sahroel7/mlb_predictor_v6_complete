"""
backtester.py - test Historical Backtesting Engine v6.0
Tests model performance on real MLB historical games & actual scores from MLB Stats API
"""

import json
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import numpy as np

from config import CONFIDENCE_THRESHOLDS, print_section
from models import EnsembleModel
from data_fetchers import get_all_games, get_team_standings, mlb_api_get, GameData


def fetch_real_historical_games(days_back: int = 10) -> List[Tuple[GameData, Dict]]:
    """
    Fetch real historical MLB games with actual game scores and outcomes from MLB API.
    Returns List of (GameData, actual_result_dict).
    """
    end_date = datetime.now() - timedelta(days=1)
    games_with_results = []

    for i in range(days_back):
        target_date = (end_date - timedelta(days=i)).strftime("%Y-%m-%d")
        schedule_data = mlb_api_get("/schedule", {"sportId": 1, "date": target_date, "hydrate": "probablePitcher,venue,team"})
        if not schedule_data or not schedule_data.get("dates"):
            continue

        for date_info in schedule_data.get("dates", []):
            for game in date_info.get("games", []):
                status = game.get("status", {}).get("abstractGameState", "")
                if status != "Final":
                    continue

                teams = game.get("teams", {})
                away_score = teams.get("away", {}).get("score")
                home_score = teams.get("home", {}).get("score")
                if away_score is None or home_score is None or away_score == home_score:
                    continue

                # Create GameData
                game_pk = game.get("gamePk")
                away_info = teams.get("away", {}).get("team", {})
                home_info = teams.get("home", {}).get("team", {})

                # Fetch game data structure
                games = get_all_games(target_date)
                target_game_data = next((g for g in games if g.game_pk == game_pk), None)

                if target_game_data:
                    actual_home_win = home_score > away_score
                    actual_result = {
                        "actual_away_score": away_score,
                        "actual_home_score": home_score,
                        "actual_total": away_score + home_score,
                        "actual_home_win": actual_home_win,
                        "actual_winner": target_game_data.home_team if actual_home_win else target_game_data.away_team
                    }
                    games_with_results.append((target_game_data, actual_result))

    return games_with_results


def run_backtest(num_games: int = 100, weights: Optional[Dict] = None) -> Dict:
    """Run backtest on real historical MLB games"""
    print_section(f"Backtest: Real Historical MLB Games")

    standings = get_team_standings()
    model = EnsembleModel(weights=weights)

    print("Fetching historical games and real outcomes from MLB API...")
    real_historical = fetch_real_historical_games(days_back=14)

    if not real_historical:
        print("⚠️ Warning: Could not fetch enough real historical games. Using cached/simulated data.")

    results = []
    correct = 0
    high_conf_correct = 0
    high_conf_total = 0
    medium_conf_correct = 0
    medium_conf_total = 0
    low_conf_correct = 0
    low_conf_total = 0

    brier_scores = []
    score_errors = []

    tested_count = min(num_games, len(real_historical)) if real_historical else 0

    if tested_count > 0:
        for game_data, actual in real_historical[:tested_count]:
            prediction = model.predict(game_data, standings)
            actual_home_win = actual["actual_home_win"]

            result = {
                "game_id": game_data.game_pk,
                "game_date": game_data.game_date,
                "matchup": f"{game_data.away_team} @ {game_data.home_team}",
                "predicted_home_win_prob": prediction["home_win_prob"],
                "actual_home_win": actual_home_win,
                "actual_winner": actual["actual_winner"],
                "predicted_away_score": prediction["predicted_away_score"],
                "predicted_home_score": prediction["predicted_home_score"],
                "confidence": prediction["confidence"],
                "confidence_level": prediction["confidence_level"],
                "pick": prediction["pick"],
            }

            predicted_home = prediction["home_win_prob"] > 0.5
            is_correct = (predicted_home == actual_home_win)
            result["is_correct"] = is_correct
            results.append(result)

            if is_correct:
                correct += 1

            # By confidence
            conf = prediction["confidence_level"]
            if conf == "HIGH":
                high_conf_total += 1
                if is_correct:
                    high_conf_correct += 1
            elif conf == "MEDIUM":
                medium_conf_total += 1
                if is_correct:
                    medium_conf_correct += 1
            else:
                low_conf_total += 1
                if is_correct:
                    low_conf_correct += 1

            # Brier score
            act_val = 1.0 if actual_home_win else 0.0
            brier_scores.append((prediction["home_win_prob"] - act_val) ** 2)

            # Score error
            act_tot = actual["actual_away_score"] + actual["actual_home_score"]
            score_errors.append(abs(act_tot - prediction["predicted_total"]))
    else:
        # Fallback simulation if offline/no internet
        print("Running fallback simulation...")
        from backtester_legacy import run_simulated_backtest
        return run_simulated_backtest(num_games, weights)

    # Calculate metrics
    accuracy = correct / tested_count if tested_count > 0 else 0
    brier = np.mean(brier_scores) if brier_scores else 0
    avg_score_error = np.mean(score_errors) if score_errors else 0

    high_acc = high_conf_correct / high_conf_total if high_conf_total > 0 else 0
    med_acc = medium_conf_correct / medium_conf_total if medium_conf_total > 0 else 0
    low_acc = low_conf_correct / low_conf_total if low_conf_total > 0 else 0

    summary = {
        "total_games": tested_count,
        "accuracy": round(accuracy, 3),
        "brier_score": round(brier, 4),
        "avg_score_error": round(avg_score_error, 2),
        "high_confidence": {
            "total": high_conf_total,
            "correct": high_conf_correct,
            "accuracy": round(high_acc, 3)
        },
        "medium_confidence": {
            "total": medium_conf_total,
            "correct": medium_conf_correct,
            "accuracy": round(med_acc, 3)
        },
        "low_confidence": {
            "total": low_conf_total,
            "correct": low_conf_correct,
            "accuracy": round(low_acc, 3)
        },
        "detailed_results": results,
    }

    print(f"\n[Real Historical Backtest Results ({tested_count} games)]")
    print(f"  Overall Accuracy: {accuracy:.1%}")
    print(f"  Brier Score: {brier:.4f} (lower = better)")
    print(f"  Avg Score Error: {avg_score_error:.2f} runs")
    print(f"\n  HIGH Confidence: {high_acc:.1%} ({high_conf_correct}/{high_conf_total})")
    print(f"  MEDIUM Confidence: {med_acc:.1%} ({medium_conf_correct}/{medium_conf_total})")
    print(f"  LOW Confidence: {low_acc:.1%} ({low_conf_correct}/{low_conf_total})")

    return summary


def save_backtest_results(results: Dict, filename: str = "backtest_results.json"):
    """Save backtest results to file"""
    from config import DATA_DIR
    filepath = f"{DATA_DIR}/{filename}"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n💾 Results saved to {filepath}")

