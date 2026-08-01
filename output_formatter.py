"""
output_formatter.py - Display Formatting for MLB Prediction System v6.0
"""

import sys
from typing import Dict, List, Optional
from config import print_section

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def format_prediction(prediction: Dict) -> str:
    """Format a single prediction for display"""
    lines = []
    lines.append("")
    lines.append("─" * 60)
    lines.append(f"  {prediction['away_team']} @ {prediction['home_team']}")
    lines.append("─" * 60)

    # Winner prediction
    away_prob = prediction['away_win_prob']
    home_prob = prediction['home_win_prob']
    pick = prediction['pick']
    conf = prediction['confidence_level']
    conf_val = prediction['confidence']

    lines.append(f"\n  🏆 PICK: {pick}")
    lines.append(f"  📊 Confidence: {conf} ({conf_val:.1%})")

    vb = prediction.get("value_bet", {})
    if vb:
        ev = vb.get("expected_value", 0.0)
        stake = vb.get("recommended_stake_pct", 0.0)
        ev_str = f"+{ev:.1%}" if ev > 0 else f"{ev:.1%}"
        lines.append(f"  💰 Value Bet (EV): {ev_str} | Rec. Bankroll Stake: {stake}% (Kelly)")

    lines.append(f"\n  Win Probability:")
    lines.append(f"    {prediction['away_team']}: {away_prob:.1%}")
    lines.append(f"    {prediction['home_team']}: {home_prob:.1%}")

    # Score prediction
    lines.append(f"\n  📈 Predicted Score:")
    lines.append(f"    {prediction['away_team']}: {prediction['predicted_away_score']:.1f}")
    lines.append(f"    {prediction['home_team']}: {prediction['predicted_home_score']:.1f}")
    lines.append(f"    Total: {prediction['predicted_total']:.1f}")

    # Pitcher comparison
    pc = prediction.get('pitcher_comparison', {})
    if pc:
        lines.append(f"\n  ⚾ Pitcher Matchup:")
        lines.append(f"    Away Grade: {pc.get('away_grade', 'N/A')}/100")
        lines.append(f"    Home Grade: {pc.get('home_grade', 'N/A')}/100")
        adv = pc.get('advantage', 0)
        if adv > 0.05:
            lines.append(f"    → Away pitcher advantage: +{adv:.3f}")
        elif adv < -0.05:
            lines.append(f"    → Home pitcher advantage: {adv:.3f}")
        else:
            lines.append(f"    → Pitcher matchup: Even")

    # Weather
    wi = prediction.get('weather_impact', {})
    if wi and wi.get('overall', 0) != 0:
        lines.append(f"\n  🌤️ Weather Impact: {wi['overall']:+.3f}")

    # Model breakdown visual format
    mb = prediction.get('model_breakdown', {})
    if mb:
        TEAM_ABBR = {
            "Arizona Diamondbacks": "ARI", "Atlanta Braves": "ATL", "Baltimore Orioles": "BAL",
            "Boston Red Sox": "BOS", "Chicago Cubs": "CHC", "Chicago White Sox": "CWS",
            "Cincinnati Reds": "CIN", "Cleveland Guardians": "CLE", "Colorado Rockies": "COL",
            "Detroit Tigers": "DET", "Houston Astros": "HOU", "Kansas City Royals": "KCR",
            "Los Angeles Angels": "LAA", "Los Angeles Dodgers": "LAD", "Miami Marlins": "MIA",
            "Milwaukee Brewers": "MIL", "Minnesota Twins": "MIN", "New York Mets": "NYM",
            "New York Yankees": "NYY", "Athletics": "ATH", "Oakland Athletics": "ATH",
            "Philadelphia Phillies": "PHI", "Pittsburgh Pirates": "PIT", "San Diego Padres": "SDP",
            "San Francisco Giants": "SFG", "Seattle Mariners": "SEA", "St. Louis Cardinals": "STL",
            "Tampa Bay Rays": "TBR", "Texas Rangers": "TEX", "Toronto Blue Jays": "TOR",
            "Washington Nationals": "WSN"
        }
        home_abbr = TEAM_ABBR.get(prediction['home_team'], prediction['home_team'][:3].upper())
        away_abbr = TEAM_ABBR.get(prediction['away_team'], prediction['away_team'][:3].upper())

        lines.append(f"\n  🔬 Model Breakdown ({home_abbr} vs {away_abbr}):")
        factor_display_names = {
            "monte_carlo": "poisson_mc",
            "elo": "elo",
            "offense": "offense",
            "pitcher": "pitcher",
            "bullpen": "bullpen",
            "weather": "weather",
            "momentum": "momentum",
            "injury": "injury"
        }
        ordered_keys = ["monte_carlo", "elo", "offense", "pitcher", "bullpen", "weather", "momentum", "injury"]
        for model_key in ordered_keys:
            if model_key not in mb:
                continue
            prob = mb[model_key]
            label = factor_display_names.get(model_key, model_key)
            home_prob_val = float(prob)
            away_prob_val = 1.0 - home_prob_val
            home_pct = home_prob_val * 100
            away_pct = away_prob_val * 100

            num_home_blocks = int(round(home_prob_val * 20))
            num_home_blocks = max(0, min(20, num_home_blocks))
            num_away_blocks = 20 - num_home_blocks
            bar = "█" * num_home_blocks + "░" * num_away_blocks

            lines.append(f"     {label:<19}: {home_abbr} {home_pct:4.1f}%  [{bar}]  {away_pct:4.1f}% {away_abbr}")

    lines.append("─" * 60)
    return "\n".join(lines)


def format_predictions_table(predictions: List[Dict]) -> str:
    """Format predictions as a compact table"""
    lines = []
    lines.append("")
    lines.append("=" * 110)
    lines.append(f"  {'Game':<32} {'Pick':<20} {'Conf':<8} {'Away%':<7} {'Home%':<7} {'Total':<7} {'+EV?':<6} {'Kelly%':<6}")
    lines.append("=" * 110)

    for p in predictions:
        game = f"{p['away_team'][:14]} @ {p['home_team'][:14]}"
        pick = p['pick'][:18]
        conf = p['confidence_level']
        away_p = f"{p['away_win_prob']:.0%}"
        home_p = f"{p['home_win_prob']:.0%}"
        total = f"{p['predicted_total']:.1f}"

        vb = p.get("value_bet", {})
        is_ev = "✅ Yes" if vb.get("is_positive_ev") else "❌ No"
        stake = f"{vb.get('recommended_stake_pct', 0.0):.1f}%"

        conf_emoji = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(conf, "⚪")
        lines.append(f"  {game:<32} {pick:<20} {conf_emoji} {conf:<6} {away_p:<7} {home_p:<7} {total:<7} {is_ev:<6} {stake:<6}")

    lines.append("=" * 110)
    return "\n".join(lines)


def format_daily_summary(predictions: List[Dict]) -> str:
    """Format daily summary statistics"""
    total = len(predictions)
    if total == 0:
        return "No predictions available."

    TEAM_ABBR = {
        "Arizona Diamondbacks": "ARI", "Atlanta Braves": "ATL", "Baltimore Orioles": "BAL",
        "Boston Red Sox": "BOS", "Chicago Cubs": "CHC", "Chicago White Sox": "CWS",
        "Cincinnati Reds": "CIN", "Cleveland Guardians": "CLE", "Colorado Rockies": "COL",
        "Detroit Tigers": "DET", "Houston Astros": "HOU", "Kansas City Royals": "KCR",
        "Los Angeles Angels": "LAA", "Los Angeles Dodgers": "LAD", "Miami Marlins": "MIA",
        "Milwaukee Brewers": "MIL", "Minnesota Twins": "MIN", "New York Mets": "NYM",
        "New York Yankees": "NYY", "Athletics": "ATH", "Oakland Athletics": "ATH",
        "Philadelphia Phillies": "PHI", "Pittsburgh Pirates": "PIT", "San Diego Padres": "SDP",
        "San Francisco Giants": "SFG", "Seattle Mariners": "SEA", "St. Louis Cardinals": "STL",
        "Tampa Bay Rays": "TBR", "Texas Rangers": "TEX", "Toronto Blue Jays": "TOR",
        "Washington Nationals": "WSN"
    }

    date_str = predictions[0].get("date", "2026-07-25")
    high = sum(1 for p in predictions if p['confidence_level'] == 'HIGH')
    medium = sum(1 for p in predictions if p['confidence_level'] == 'MEDIUM')
    low = sum(1 for p in predictions if p['confidence_level'] == 'LOW')

    avg_home_prob = sum(p['home_win_prob'] for p in predictions) / total
    avg_total_runs = sum(p['predicted_total'] for p in predictions) / total

    top_3 = sorted(predictions, key=lambda x: x.get("value_bet", {}).get("expected_value", 0.0), reverse=True)[:3]

    lines = []
    lines.append("")
    lines.append("=" * 70)
    lines.append("  DAILY PREDICTION SUMMARY")
    lines.append("=" * 70)
    lines.append(f"\n  📅 Date: {date_str}")
    lines.append(f"  🎮 Total Games: {total}")
    lines.append(f"  🎯 Confidence Distribution:")
    lines.append(f"     HIGH:   {high} games")
    lines.append(f"     MEDIUM: {medium} games")
    lines.append(f"     LOW:    {low} games")
    lines.append(f"  📊 Avg Home Win Prob: {avg_home_prob:.1%}")
    lines.append(f"  📈 Avg Total Runs: {avg_total_runs:.1f}")
    lines.append(f"\n  ⭐ TOP PICKS (Highest EV & Win Prob):")

    for idx, p in enumerate(top_3, 1):
        away_a = TEAM_ABBR.get(p['away_team'], p['away_team'][:3].upper())
        home_a = TEAM_ABBR.get(p['home_team'], p['home_team'][:3].upper())
        pick_a = TEAM_ABBR.get(p['pick'], p['pick'][:3].upper())
        win_p = p['home_win_prob'] if p['pick'] == p['home_team'] else p['away_win_prob']
        lines.append(f"     {idx}. {away_a} @ {home_a} → {pick_a} ({win_p:.1%})")

    lines.append(f"\n" + "=" * 70)
    lines.append(f"  Prediction complete!")
    lines.append(f"  Saved {total} predictions to SQLite database (mlb_predictions.db).")
    lines.append("=" * 70)

    return "\n".join(lines)


def format_backtest_summary(results: Dict) -> str:
    """Format backtest results"""
    lines = []
    lines.append("")
    lines.append("=" * 60)
    lines.append("  📊 BACKTEST SUMMARY")
    lines.append("=" * 60)
    lines.append(f"\n  Games Tested: {results['total_games']}")
    lines.append(f"  Overall Accuracy: {results['accuracy']:.1%}")
    lines.append(f"  Brier Score: {results['brier_score']:.4f}")
    lines.append(f"  Avg Score Error: {results['avg_score_error']:.2f} runs")
    lines.append(f"\n  By Confidence Level:")

    for level in ['high', 'medium', 'low']:
        data = results.get(f"{level}_confidence", {})
        total = data.get('total', 0)
        correct = data.get('correct', 0)
        acc = data.get('accuracy', 0)
        emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(level, "⚪")
        lines.append(f"    {emoji} {level.upper()}: {acc:.1%} ({correct}/{total})")

    lines.append("=" * 60)
    return "\n".join(lines)


def print_predictions(predictions: List[Dict], verbose: bool = False):
    """Print predictions to console"""
    if verbose:
        for p in predictions:
            print(format_prediction(p))
    else:
        print(format_predictions_table(predictions))

    print(format_daily_summary(predictions))


def format_verification_report(verified_results: List[Dict], date_str: str) -> str:
    """Format verification report comparing predictions vs actual results"""
    lines = []
    lines.append("")
    lines.append("=" * 104)
    lines.append("                                 ⚾ MLB PREDICTION VERIFICATION REPORT ⚾")
    lines.append("=" * 104)
    lines.append(f" Tanggal: {date_str} | Total Pertandingan Evaluasi: {len(verified_results)}")
    lines.append("")

    verified_count = 0
    correct_count = 0
    total_run_errors = []

    for idx, item in enumerate(verified_results, 1):
        away = item.get("away_team", "")
        home = item.get("home_team", "")
        lines.append(f" {idx}. {away} @ {home}")
        lines.append(" ──────────────────────────────────────────────────────────────────────────────────────────────────────")

        pick = item.get("predicted_pick", "")
        conf_level = item.get("confidence_level", "LOW")
        conf_val = item.get("confidence", 0.0)

        pred_away_s = item.get("predicted_away_score", 0.0)
        pred_home_s = item.get("predicted_home_score", 0.0)
        pred_total = item.get("predicted_total", 0.0)

        lines.append(f"   • Tim Diprediksi Win : {pick} (Confidence: {conf_level} - {conf_val:.1%})")
        lines.append(f"   • Prediksi Skor      : {away[:3].upper()} {pred_away_s:.1f} - {pred_home_s:.1f} {home[:3].upper()}  │  Total Runs Prediksi : {pred_total:.1f}")

        v_status = item.get("verification_status")
        if v_status == "VERIFIED" or item.get("status") == "COMPLETED":
            verified_count += 1
            act_away = item.get("actual_away_score", 0)
            act_home = item.get("actual_home_score", 0)
            act_total = item.get("actual_total", 0)
            act_winner = item.get("actual_winner", "")
            is_corr = item.get("is_correct", 0)

            if is_corr == 1:
                correct_count += 1
                result_emoji = "✅ BENAR"
            else:
                result_emoji = "❌ SALAH"

            run_err = abs(pred_total - act_total)
            total_run_errors.append(run_err)

            lines.append(f"   • Realita Hasil      : {away[:3].upper()} {act_away} - {act_home} {home[:3].upper()}      │  Total Runs Realita  : {act_total}")
            lines.append(f"   • Hasil Prediksi Win : {result_emoji} ({act_winner} Menang)")
            lines.append(f"   • Selisih Total Runs : {run_err:.1f} runs (Prediksi {pred_total:.1f} vs Asli {act_total})")
        else:
            lines.append("   • Realita Hasil      : ⏳ PERTANDINGAN BELUM SELESAI / BELUM FINAL")

        lines.append("")

    lines.append("=" * 104)
    lines.append("                                           📊 RINGKASAN HASIL")
    lines.append("=" * 104)
    lines.append(f"   • Total Pertandingan Evaluasi : {len(verified_results)}")
    lines.append(f"   • Pertandingan Finished       : {verified_count}")

    if verified_count > 0:
        acc = (correct_count / verified_count) * 100
        avg_err = sum(total_run_errors) / verified_count
        lines.append(f"   • Prediksi Win Benar          : {correct_count} / {verified_count} (Akurasi: {acc:.1f}%)")
        lines.append(f"   • Prediksi Win Salah          : {verified_count - correct_count} / {verified_count}")
        lines.append(f"   • Rata-rata Eror Total Runs   : {avg_err:.2f} runs")
        lines.append("   • Status Database             : Data berhasil diperbarui ke 'COMPLETED'")
    else:
        lines.append("   • Info                        : Belum ada pertandingan yang selesai untuk dikalkulasi.")
    lines.append("=" * 104)

    return "\n".join(lines)

