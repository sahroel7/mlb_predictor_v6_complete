"""
game_fetcher.py - Fetch schedule & compare morning vs afternoon data
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional

from config import get_today_date, print_section
from data_fetchers import get_all_games, GameData


def fetch_morning_data(date_str: Optional[str] = None) -> List[GameData]:
    """Fetch games in the morning (probable pitchers may be TBD)"""
    print("[Morning Fetch] Getting early schedule...")
    return get_all_games(date_str)


def fetch_afternoon_data(date_str: Optional[str] = None) -> List[GameData]:
    """Fetch games in the afternoon (lineups confirmed)"""
    print("[Afternoon Fetch] Getting updated schedule with confirmed lineups...")
    return get_all_games(date_str)


def compare_morning_afternoon(morning: List[GameData], afternoon: List[GameData]) -> Dict:
    """Compare morning vs afternoon data to detect changes"""
    changes = {
        "pitcher_changes": [],
        "weather_changes": [],
        "status_changes": [],
        "total_morning_games": len(morning),
        "total_afternoon_games": len(afternoon),
    }

    morning_map = {g.game_pk: g for g in morning}
    afternoon_map = {g.game_pk: g for g in afternoon}

    for pk, afternoon_game in afternoon_map.items():
        morning_game = morning_map.get(pk)
        if not morning_game:
            continue

        # Check pitcher changes
        morning_away = morning_game.away_pitcher.name if morning_game.away_pitcher else "TBD"
        afternoon_away = afternoon_game.away_pitcher.name if afternoon_game.away_pitcher else "TBD"
        morning_home = morning_game.home_pitcher.name if morning_game.home_pitcher else "TBD"
        afternoon_home = afternoon_game.home_pitcher.name if afternoon_game.home_pitcher else "TBD"

        if morning_away != afternoon_away or morning_home != afternoon_home:
            changes["pitcher_changes"].append({
                "game": f"{afternoon_game.away_team} @ {afternoon_game.home_team}",
                "away_before": morning_away,
                "away_after": afternoon_away,
                "home_before": morning_home,
                "home_after": afternoon_home,
            })

        # Check weather changes
        if (morning_game.weather and afternoon_game.weather and 
            not morning_game.is_dome and not afternoon_game.is_dome):
            m_temp = morning_game.weather.temperature or 0
            a_temp = afternoon_game.weather.temperature or 0
            if abs(m_temp - a_temp) > 5:
                changes["weather_changes"].append({
                    "game": f"{afternoon_game.away_team} @ {afternoon_game.home_team}",
                    "temp_before": m_temp,
                    "temp_after": a_temp,
                })

        # Check status changes
        if morning_game.status != afternoon_game.status:
            changes["status_changes"].append({
                "game": f"{afternoon_game.away_team} @ {afternoon_game.home_team}",
                "before": morning_game.status,
                "after": afternoon_game.status,
            })

    return changes


def print_comparison_report(changes: Dict):
    """Print formatted comparison report"""
    print_section("Morning vs Afternoon Comparison")

    print(f"Total Games: {changes['total_morning_games']} (morning) / {changes['total_afternoon_games']} (afternoon)")

    if changes["pitcher_changes"]:
        print(f"\n🔄 Pitcher Changes ({len(changes['pitcher_changes'])}):")
        for change in changes["pitcher_changes"]:
            print(f"  {change['game']}:")
            print(f"    Away: {change['away_before']} → {change['away_after']}")
            print(f"    Home: {change['home_before']} → {change['home_after']}")
    else:
        print("\n✅ No pitcher changes detected")

    if changes["weather_changes"]:
        print(f"\n🌤️ Weather Changes ({len(changes['weather_changes'])}):")
        for change in changes["weather_changes"]:
            print(f"  {change['game']}: {change['temp_before']}°F → {change['temp_after']}°F")
    else:
        print("\n✅ No significant weather changes")

    if changes["status_changes"]:
        print(f"\n⚠️ Status Changes ({len(changes['status_changes'])}):")
        for change in changes["status_changes"]:
            print(f"  {change['game']}: {change['before']} → {change['after']}")
    else:
        print("\n✅ No status changes")
