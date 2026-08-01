"""
database.py - SQLite Database Storage & Verification for MLB Predictions v6.0
"""

import os
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from config import DATA_DIR, get_today_date
from data_fetchers import mlb_api_get

DB_PATH = os.path.join(DATA_DIR, "mlb_predictions.db")


def normalize_date_str(d_str: Optional[str]) -> str:
    """
    Normalize date string into standard YYYY-MM-DD ISO format.
    Supports input formats: YYYY-MM-DD, MM/DD/YYYY, MM-DD-YYYY, DD/MM/YYYY
    """
    if not d_str:
        return get_today_date()
    d_str = d_str.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(d_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return d_str



def get_connection() -> sqlite3.Connection:
    """Get connection to SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize predictions table if it doesn't exist"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                game_id INTEGER PRIMARY KEY,
                date TEXT NOT NULL,
                away_team TEXT NOT NULL,
                home_team TEXT NOT NULL,
                away_pitcher TEXT,
                home_pitcher TEXT,
                predicted_pick TEXT NOT NULL,
                confidence_level TEXT NOT NULL,
                confidence REAL NOT NULL,
                away_win_prob REAL NOT NULL,
                home_win_prob REAL NOT NULL,
                predicted_away_score REAL NOT NULL,
                predicted_home_score REAL NOT NULL,
                predicted_total REAL NOT NULL,
                updated_at TEXT NOT NULL,
                actual_away_score INTEGER,
                actual_home_score INTEGER,
                actual_total INTEGER,
                actual_winner TEXT,
                is_correct INTEGER,
                status TEXT DEFAULT 'PENDING'
            )
        """)
        conn.commit()


def save_predictions_to_db(predictions: List[Dict], games_list: Optional[List] = None):
    """
    Save or update predictions in SQLite database (UPSERT).
    If a game prediction already exists for the day, it updates to the latest prediction.
    Only called for today's predictions (not backtest).
    """
    init_db()

    # Map game_pk to pitcher names if available
    pitcher_map = {}
    if games_list:
        for g in games_list:
            away_p = g.away_pitcher.name if getattr(g, 'away_pitcher', None) else "TBD"
            home_p = g.home_pitcher.name if getattr(g, 'home_pitcher', None) else "TBD"
            pitcher_map[g.game_pk] = (away_p, home_p)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        cursor = conn.cursor()
        for p in predictions:
            game_id = p["game_pk"]
            date_str = normalize_date_str(p.get("date"))
            away_team = p["away_team"]
            home_team = p["home_team"]

            away_pitcher, home_pitcher = pitcher_map.get(game_id, ("TBD", "TBD"))

            cursor.execute("""
                INSERT INTO predictions (
                    game_id, date, away_team, home_team, away_pitcher, home_pitcher,
                    predicted_pick, confidence_level, confidence, away_win_prob, home_win_prob,
                    predicted_away_score, predicted_home_score, predicted_total, updated_at, status
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING'
                )
                ON CONFLICT(game_id) DO UPDATE SET
                    date = excluded.date,
                    away_team = excluded.away_team,
                    home_team = excluded.home_team,
                    away_pitcher = excluded.away_pitcher,
                    home_pitcher = excluded.home_pitcher,
                    predicted_pick = excluded.predicted_pick,
                    confidence_level = excluded.confidence_level,
                    confidence = excluded.confidence,
                    away_win_prob = excluded.away_win_prob,
                    home_win_prob = excluded.home_win_prob,
                    predicted_away_score = excluded.predicted_away_score,
                    predicted_home_score = excluded.predicted_home_score,
                    predicted_total = excluded.predicted_total,
                    updated_at = excluded.updated_at
                WHERE status = 'PENDING'
            """, (
                game_id, date_str, away_team, home_team, away_pitcher, home_pitcher,
                p["pick"], p["confidence_level"], p["confidence"], p["away_win_prob"], p["home_win_prob"],
                p["predicted_away_score"], p["predicted_home_score"], p["predicted_total"], now_str
            ))
        conn.commit()


def get_predictions_by_date(date_str: str) -> List[Dict]:
    """Retrieve all predictions (pending & completed) for a specific date"""
    init_db()
    norm_date = normalize_date_str(date_str)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM predictions WHERE date = ?", (norm_date,))
        return [dict(row) for row in cursor.fetchall()]


def get_pending_predictions(date_str: Optional[str] = None) -> List[Dict]:
    """Fetch all pending predictions from DB"""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        if date_str:
            norm_date = normalize_date_str(date_str)
            cursor.execute("SELECT * FROM predictions WHERE date = ? AND status = 'PENDING'", (norm_date,))
        else:
            cursor.execute("SELECT * FROM predictions WHERE status = 'PENDING'")
        return [dict(row) for row in cursor.fetchall()]


def fetch_actual_game_result(game_id: int) -> Optional[Dict]:
    """
    Fetch actual game result from MLB API for a given game_id.
    Returns dict with scores and winner if game is Final, else None.
    Handles rescheduled/postponed games where MLB API returns multiple dates.
    """
    data = mlb_api_get("/schedule", {"sportId": 1, "gamePk": game_id}, use_cache=False)
    if not data or not data.get("dates"):
        return None

    for date_info in data.get("dates", []):
        for game in date_info.get("games", []):
            abstract_state = game.get("status", {}).get("abstractGameState", "")
            detailed_state = game.get("status", {}).get("detailedState", "")

            if abstract_state != "Final" and detailed_state != "Completed Early":
                continue

            teams = game.get("teams", {})
            away_score = teams.get("away", {}).get("score")
            home_score = teams.get("home", {}).get("score")

            if away_score is None or home_score is None:
                continue

            away_team_name = teams.get("away", {}).get("team", {}).get("name", "")
            home_team_name = teams.get("home", {}).get("team", {}).get("name", "")

            if away_score > home_score:
                winner = away_team_name
            elif home_score > away_score:
                winner = home_team_name
            else:
                winner = "TIE"

            return {
                "away_score": int(away_score),
                "home_score": int(home_score),
                "total_runs": int(away_score + home_score),
                "winner": winner,
                "status": detailed_state
            }

    return None


def update_verified_prediction(game_id: int, actual_away: int, actual_home: int, actual_winner: str, is_correct: int):
    """Update prediction record in DB with actual game results"""
    init_db()
    actual_total = actual_away + actual_home
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE predictions SET
                actual_away_score = ?,
                actual_home_score = ?,
                actual_total = ?,
                actual_winner = ?,
                is_correct = ?,
                status = 'COMPLETED'
            WHERE game_id = ?
        """, (actual_away, actual_home, actual_total, actual_winner, is_correct, game_id))
        conn.commit()


def verify_predictions(date_str: Optional[str] = None) -> Tuple[List[Dict], str]:
    """
    Verify predictions against actual MLB game results for a date.
    Updates any PENDING predictions that have finished.
    Returns (verified_results_list, normalized_date_str).
    """
    init_db()
    target_date = normalize_date_str(date_str)
    predictions = get_predictions_by_date(target_date)

    if not predictions:
        # Fallback to any pending predictions across all dates if specific date has none
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM predictions WHERE status = 'PENDING'")
            pending_all = [dict(row) for row in cursor.fetchall()]
            if pending_all:
                predictions = pending_all
                target_date = pending_all[0]["date"]

    results = []
    for pred in predictions:
        if pred["status"] == "COMPLETED":
            pred["verification_status"] = "VERIFIED"
            results.append(pred)
            continue

        game_id = pred["game_id"]
        actual = fetch_actual_game_result(game_id)

        if not actual:
            pred["verification_status"] = "NOT_FINISHED"
            results.append(pred)
            continue

        predicted_winner = pred["predicted_pick"]
        actual_winner = actual["winner"]
        is_correct = 1 if (predicted_winner.lower() in actual_winner.lower() or actual_winner.lower() in predicted_winner.lower()) else 0

        update_verified_prediction(
            game_id=game_id,
            actual_away=actual["away_score"],
            actual_home=actual["home_score"],
            actual_winner=actual_winner,
            is_correct=is_correct
        )

        pred["actual_away_score"] = actual["away_score"]
        pred["actual_home_score"] = actual["home_score"]
        pred["actual_total"] = actual["total_runs"]
        pred["actual_winner"] = actual_winner
        pred["is_correct"] = is_correct
        pred["status"] = "COMPLETED"
        pred["verification_status"] = "VERIFIED"

        results.append(pred)

    return results, target_date
