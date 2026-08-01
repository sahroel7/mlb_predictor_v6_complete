"""
models.py - Prediction Models v6.0 (Enhanced)
ELO, Offense, Bullpen, Pitcher Analysis, Poisson/Monte Carlo, Ensemble, Value Betting
"""

import math
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from scipy import stats
from scipy.optimize import minimize

from config import DEFAULT_WEIGHTS, CONFIDENCE_THRESHOLDS, FIP_CONSTANT
from data_fetchers import GameData, PitcherStats, WeatherData, InjuryInfo


# ─── ELO Model ────────────────────────────────────────────────────────────────
class ELOModel:
    """ELO rating system for MLB teams with dynamic standings initialization"""

    def __init__(self, k_factor: float = 20.0, home_advantage: float = 24.0):
        self.k_factor = k_factor
        self.home_advantage = home_advantage
        self.ratings: Dict[int, float] = {}
        self._initialize_ratings()

    def _initialize_ratings(self):
        """Initialize all teams with 1500 ELO base"""
        from config import TEAM_ID_MAP
        for team_id in TEAM_ID_MAP.values():
            self.ratings[team_id] = 1500.0

    def update_from_standings(self, standings: Dict):
        """Dynamically update team ELO ratings based on actual season win percentages"""
        if not standings:
            return
        for team_id, data in standings.items():
            win_pct = data.get("win_pct", 0.5)
            # Clamp win_pct to [0.20, 0.80]
            win_pct = max(0.20, min(0.80, win_pct))
            # Convert win_pct to ELO offset: 1500 + 400 * log10(win_pct / (1 - win_pct))
            elo_rating = 1500.0 + 400.0 * math.log10(win_pct / (1.0 - win_pct))
            self.ratings[team_id] = round(elo_rating, 1)

    def expected_score(self, rating_a: float, rating_b: float) -> float:
        """Calculate expected score for team A vs team B"""
        return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))

    def predict_win_prob(self, away_team_id: int, home_team_id: int) -> float:
        """Return probability of home team winning"""
        away_rating = self.ratings.get(away_team_id, 1500.0)
        home_rating = self.ratings.get(home_team_id, 1500.0)
        home_rating += self.home_advantage
        return self.expected_score(home_rating, away_rating)

    def update_ratings(self, away_team_id: int, home_team_id: int, 
                       away_score: int, home_score: int):
        """Update ELO ratings after a game"""
        away_rating = self.ratings.get(away_team_id, 1500.0)
        home_rating = self.ratings.get(home_team_id, 1500.0)

        home_expected = self.expected_score(home_rating + self.home_advantage, away_rating)
        away_expected = 1.0 - home_expected

        home_actual = 1.0 if home_score > away_score else 0.5 if home_score == away_score else 0.0
        away_actual = 1.0 - home_actual

        self.ratings[home_team_id] = home_rating + self.k_factor * (home_actual - home_expected)
        self.ratings[away_team_id] = away_rating + self.k_factor * (away_actual - away_expected)

    def get_rating(self, team_id: int) -> float:
        return self.ratings.get(team_id, 1500.0)


# ─── Team Offense Model ───────────────────────────────────────────────────────
class TeamOffenseModel:
    """Team batting & offensive output model (OPS, Runs/Game)"""

    def get_offense_win_prob(self, away_team_id: int, home_team_id: int, standings: Optional[Dict] = None) -> float:
        """Calculate home team win probability based on team offense metrics"""
        if not standings:
            return 0.5

        away_off = standings.get(away_team_id, {}).get("offense", {})
        home_off = standings.get(home_team_id, {}).get("offense", {})

        if not away_off or not home_off:
            return 0.5

        away_ops = away_off.get("ops", 0.730)
        home_ops = home_off.get("ops", 0.730)
        away_rpg = away_off.get("runs_per_game", 4.5)
        home_rpg = home_off.get("runs_per_game", 4.5)

        # OPS differential impact (.100 OPS diff ~ 8% win prob shift)
        ops_diff = home_ops - away_ops
        rpg_diff = (home_rpg - away_rpg) / 4.5

        prob = 0.5 + (ops_diff * 1.4 + rpg_diff * 0.25) / 2.0
        return max(0.20, min(0.80, round(prob, 3)))


# ─── Bullpen Model ────────────────────────────────────────────────────────────
class BullpenModel:
    """Bullpen strength analysis using real API metrics"""

    def __init__(self):
        self.bullpen_data: Dict[int, Dict] = {}

    def estimate_bullpen_strength(self, team_id: int, standings: Optional[Dict] = None) -> float:
        """Estimate bullpen strength (0-1 scale, higher = better)"""
        data = {}
        if standings and team_id in standings:
            data = standings[team_id].get("bullpen", {})
        if not data:
            data = self.bullpen_data.get(team_id, {})
        if not data:
            return 0.5  # Neutral

        era = data.get("era", 4.10)
        whip = data.get("whip", 1.28)
        k_per_9 = data.get("k_per_9", 8.8)

        # Normalize to 0-1
        era_score = max(0.0, min(1.0, (6.0 - era) / 3.5))
        whip_score = max(0.0, min(1.0, (1.8 - whip) / 1.0))
        k_score = max(0.0, min(1.0, (k_per_9 - 5.0) / 8.0))

        return round((era_score * 0.40 + whip_score * 0.35 + k_score * 0.25), 3)

    def bullpen_advantage(self, away_team_id: int, home_team_id: int, standings: Optional[Dict] = None) -> float:
        """Return bullpen advantage for home team (-1 to 1)"""
        away_strength = self.estimate_bullpen_strength(away_team_id, standings)
        home_strength = self.estimate_bullpen_strength(home_team_id, standings)

        if away_strength + home_strength == 0:
            return 0.0
        return round(home_strength - away_strength, 3)


# ─── Pitcher Model ──────────────────────────────────────────────────────────────
class PitcherModel:
    """Starting pitcher matchup analysis with Bayesian shrinkage for small IP"""

    def __init__(self):
        self.weights = {
            "era": 0.25,
            "whip": 0.20,
            "k_per_9": 0.15,
            "bb_per_9": 0.15,
            "hr_per_9": 0.10,
            "fip": 0.15,
        }

    def compare_pitchers(self, away: PitcherStats, home: PitcherStats) -> Dict[str, float]:
        """Compare two pitchers across all metrics"""
        def norm(val1, val2, lower_is_better=True):
            if val1 is None or val2 is None or (val1 + val2) == 0:
                return 0.0
            diff = val2 - val1 if lower_is_better else val1 - val2
            avg = (abs(val1) + abs(val2)) / 2.0
            return max(-1.0, min(1.0, diff / avg))

        return {
            "era": norm(away.era, home.era, True),
            "whip": norm(away.whip, home.whip, True),
            "k_per_9": norm(away.k_per_9, home.k_per_9, False),
            "bb_per_9": norm(away.bb_per_9, home.bb_per_9, True),
            "hr_per_9": norm(away.hr_per_9, home.hr_per_9, True),
            "fip": norm(away.fip, home.fip, True),
            "ip": norm(away.ip, home.ip, False),
        }

    def get_advantage_score(self, away: PitcherStats, home: PitcherStats) -> float:
        """Overall pitcher advantage for home team (-1 to 1)"""
        comparison = self.compare_pitchers(away, home)
        score = sum(comparison.get(k, 0) * self.weights.get(k, 0) 
                    for k in self.weights.keys())
        total_weight = sum(self.weights.values())
        return round(score / total_weight, 3) if total_weight > 0 else 0.0

    def pitcher_score(self, p: PitcherStats) -> float:
        """Single pitcher quality score (0-100) with Bayesian Shrinkage"""
        if not p or p.ip <= 0:
            return 50.0

        # Regress small sample sizes towards league average (4.30 ERA, 1.30 WHIP)
        ip_weight = min(1.0, p.ip / 30.0)
        reg_era = p.era * ip_weight + 4.30 * (1 - ip_weight)
        reg_whip = p.whip * ip_weight + 1.30 * (1 - ip_weight)
        reg_fip = p.fip * ip_weight + 4.30 * (1 - ip_weight)
        reg_k9 = p.k_per_9 * ip_weight + 8.5 * (1 - ip_weight)

        era_score = max(0, min(100, (6.5 - reg_era) / 4.5 * 100))
        whip_score = max(0, min(100, (2.0 - reg_whip) / 1.2 * 100))
        k_score = max(0, min(100, reg_k9 / 14.0 * 100))
        fip_score = max(0, min(100, (6.5 - reg_fip) / 4.5 * 100))

        return round(era_score * 0.30 + whip_score * 0.25 + k_score * 0.20 + fip_score * 0.25, 1)


# ─── Weather Model ────────────────────────────────────────────────────────────
class WeatherModel:
    """Weather impact on game outcomes"""

    def weather_impact(self, weather) -> Dict[str, float]:
        """Calculate weather impact on scoring (-1 to 1)"""
        if not weather or weather.is_dome:
            return {"offense": 0.0, "pitching": 0.0, "overall": 0.0}

        temp = weather.temperature or 70
        wind_speed = weather.wind_speed or 5

        # Temperature impact
        if temp < 45:
            temp_factor = -0.25
        elif temp < 55:
            temp_factor = -0.10
        elif temp < 75:
            temp_factor = 0.0
        elif temp < 85:
            temp_factor = 0.10
        else:
            temp_factor = 0.20

        # Wind impact (out = helps hitters, in = helps pitchers)
        wind_factor = 0.0
        if wind_speed > 10:
            wind_dir = weather.wind_direction or ""
            if any(d in wind_dir for d in ["S", "SW", "SE"]):
                wind_factor = 0.15  # Wind out
            elif any(d in wind_dir for d in ["N", "NW", "NE"]):
                wind_factor = -0.15  # Wind in

        precip = weather.precipitation_chance or 0
        precip_factor = -0.1 if precip > 50 else 0.0

        overall = temp_factor + wind_factor + precip_factor
        return {
            "offense": round(temp_factor + wind_factor, 3),
            "pitching": round(-wind_factor + precip_factor, 3),
            "overall": round(overall, 3)
        }


# ─── Injury Model ───────────────────────────────────────────────────────────────
class InjuryModel:
    """Injury impact assessment"""

    def __init__(self):
        self.severity_weights = {"low": 0.02, "medium": 0.05, "high": 0.12}

    def team_impact(self, injuries: List[InjuryInfo]) -> float:
        """Calculate total injury impact on team (0 to ~0.5)"""
        if not injuries:
            return 0.0

        total = 0.0
        for injury in injuries:
            weight = self.severity_weights.get(injury.severity, 0.03)
            total += weight

        return min(total, 0.5)

    def injury_advantage(self, away_injuries: List[InjuryInfo], 
                         home_injuries: List[InjuryInfo]) -> float:
        """Return injury advantage for home team (-1 to 1)"""
        away_impact = self.team_impact(away_injuries)
        home_impact = self.team_impact(home_injuries)

        if away_impact + home_impact == 0:
            return 0.0
        return home_impact - away_impact


# ─── Poisson / Monte Carlo ────────────────────────────────────────────────────
class PoissonMonteCarlo:
    """Score prediction using Poisson distribution + Monte Carlo simulation"""

    def __init__(self, simulations: int = 20000):
        self.simulations = simulations

    def predict_score(self, away_rpg: float = 4.5, home_rpg: float = 4.5,
                      pitcher_advantage: float = 0.0,
                      weather_impact: float = 0.0) -> Dict:
        """Predict score distribution based on team offense & pitcher advantage"""
        away_rate = away_rpg
        home_rate = home_rpg * 1.03  # Slight home park factor

        # Pitcher advantage adjustments
        away_rate *= (1 + pitcher_advantage * 0.25)
        home_rate *= (1 - pitcher_advantage * 0.25)

        # Weather adjustment
        away_rate *= (1 + weather_impact * 0.15)
        home_rate *= (1 + weather_impact * 0.15)

        away_rate = max(0.8, away_rate)
        home_rate = max(0.8, home_rate)

        away_scores = np.random.poisson(away_rate, self.simulations)
        home_scores = np.random.poisson(home_rate, self.simulations)

        away_wins = np.sum(away_scores > home_scores)
        home_wins = np.sum(home_scores > away_scores)
        ties = np.sum(away_scores == home_scores)

        return {
            "away_avg_runs": round(float(np.mean(away_scores)), 2),
            "home_avg_runs": round(float(np.mean(home_scores)), 2),
            "away_win_prob": round(float(away_wins / self.simulations), 3),
            "home_win_prob": round(float(home_wins / self.simulations), 3),
            "tie_prob": round(float(ties / self.simulations), 3),
            "over_under_line": round(float(np.mean(away_scores) + np.mean(home_scores)), 1),
            "away_score_std": round(float(np.std(away_scores)), 2),
            "home_score_std": round(float(np.std(home_scores)), 2),
        }


# ─── Ensemble Model ───────────────────────────────────────────────────────────
class EnsembleModel:
    """Weighted ensemble combining all statistical models & value betting"""

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        self.elo = ELOModel()
        self.offense = TeamOffenseModel()
        self.bullpen = BullpenModel()
        self.pitcher = PitcherModel()
        self.weather = WeatherModel()
        self.injury = InjuryModel()
        self.mc = PoissonMonteCarlo()

    def predict(self, game: GameData, standings: Optional[Dict] = None) -> Dict:
        """Generate synchronized prediction for a game"""

        # Update ELO dynamically if standings provided
        if standings:
            self.elo.update_from_standings(standings)

        # 1. ELO prediction
        elo_prob = self.elo.predict_win_prob(game.away_team_id, game.home_team_id)

        # 2. Team Offense
        offense_prob = self.offense.get_offense_win_prob(game.away_team_id, game.home_team_id, standings)

        # 3. Bullpen analysis
        bullpen_adv = self.bullpen.bullpen_advantage(game.away_team_id, game.home_team_id, standings)
        bullpen_prob = 0.5 + bullpen_adv * 0.15

        # 4. Pitcher matchup
        pitcher_adv = 0.0
        if game.away_pitcher and game.home_pitcher:
            pitcher_adv = self.pitcher.get_advantage_score(game.away_pitcher, game.home_pitcher)
        pitcher_prob = 0.5 - pitcher_adv * 0.20  # Negative advantage = home better

        # 5. Weather impact
        weather_impact = self.weather.weather_impact(game.weather)
        weather_prob = 0.5 + weather_impact["overall"] * 0.05

        # 6. Momentum (from standings win_pct)
        momentum_prob = 0.5
        away_rpg = 4.5
        home_rpg = 4.5
        if standings:
            away_st = standings.get(game.away_team_id, {})
            home_st = standings.get(game.home_team_id, {})
            if away_st and home_st:
                away_pct = away_st.get("win_pct", 0.5)
                home_pct = home_st.get("win_pct", 0.5)
                momentum_prob = 0.5 + (home_pct - away_pct) * 0.25
                away_rpg = away_st.get("offense", {}).get("runs_per_game", 4.5)
                home_rpg = home_st.get("offense", {}).get("runs_per_game", 4.5)

        # 7. Injury
        injury_adv = self.injury.injury_advantage(game.away_injuries, game.home_injuries)
        injury_prob = 0.5 + injury_adv * 0.3

        # Monte Carlo Score Simulation
        mc_result = self.mc.predict_score(
            away_rpg=away_rpg,
            home_rpg=home_rpg,
            pitcher_advantage=pitcher_adv,
            weather_impact=weather_impact["overall"]
        )
        mc_prob = mc_result["home_win_prob"] / max(0.01, (mc_result["home_win_prob"] + mc_result["away_win_prob"]))

        # Ensemble weighted average
        w = self.weights
        total_w = sum(w.values())
        ensemble_prob = (
            elo_prob * w.get("elo", 0.20) +
            offense_prob * w.get("offense", 0.20) +
            pitcher_prob * w.get("pitcher", 0.25) +
            bullpen_prob * w.get("bullpen", 0.15) +
            mc_prob * w.get("monte_carlo", 0.10) +
            weather_prob * w.get("weather", 0.05) +
            momentum_prob * w.get("momentum", 0.03) +
            injury_prob * w.get("injury", 0.02)
        ) / total_w

        # Confidence level
        confidence = abs(ensemble_prob - 0.5) * 2  # Scale to 0-1
        if confidence >= CONFIDENCE_THRESHOLDS["HIGH"]:
            conf_level = "HIGH"
        elif confidence >= CONFIDENCE_THRESHOLDS["MEDIUM"]:
            conf_level = "MEDIUM"
        else:
            conf_level = "LOW"

        # Pitcher grades
        away_grade = self.pitcher.pitcher_score(game.away_pitcher) if game.away_pitcher else 50.0
        home_grade = self.pitcher.pitcher_score(game.home_pitcher) if game.home_pitcher else 50.0

        pick = game.home_team if ensemble_prob > 0.5 else game.away_team
        pick_prob = ensemble_prob if pick == game.home_team else (1.0 - ensemble_prob)

        # Calculate Expected Value (+EV) & Kelly Bet Size assuming standard market odds (-110 / 1.91)
        decimal_odds = 1.91
        ev = (pick_prob * decimal_odds) - 1.0
        b = decimal_odds - 1.0
        p = pick_prob
        q = 1.0 - p
        kelly_fraction = max(0.0, (b * p - q) / b) if b > 0 else 0.0
        recommended_stake_pct = round(min(0.05, kelly_fraction * 0.25) * 100, 1)  # Fractional Kelly max 5%

        return {
            "game_pk": game.game_pk,
            "away_team": game.away_team,
            "home_team": game.home_team,
            "away_win_prob": round(1 - ensemble_prob, 3),
            "home_win_prob": round(ensemble_prob, 3),
            "predicted_away_score": mc_result["away_avg_runs"],
            "predicted_home_score": mc_result["home_avg_runs"],
            "predicted_total": mc_result["over_under_line"],
            "confidence": round(confidence, 3),
            "confidence_level": conf_level,
            "pick": pick,
            "value_bet": {
                "expected_value": round(ev, 3),
                "is_positive_ev": ev > 0.02,
                "recommended_stake_pct": recommended_stake_pct
            },
            "model_breakdown": {
                "elo": round(elo_prob, 3),
                "offense": round(offense_prob, 3),
                "pitcher": round(pitcher_prob, 3),
                "bullpen": round(bullpen_prob, 3),
                "monte_carlo": round(mc_prob, 3),
                "weather": round(weather_prob, 3),
                "momentum": round(momentum_prob, 3),
                "injury": round(injury_prob, 3),
            },
            "pitcher_comparison": {
                "away_grade": away_grade,
                "home_grade": home_grade,
                "advantage": round(pitcher_adv, 3),
            },
            "weather_impact": weather_impact,
            "mc_simulation": mc_result,
        }

    def tune_weights(self, backtest_results: List[Dict]) -> Dict[str, float]:
        """Optimize ensemble weights using backtest data"""
        def objective(weights_list):
            keys = ["elo", "offense", "pitcher", "bullpen", "monte_carlo", "weather", "momentum", "injury"]
            w = {k: weights_list[i] for i, k in enumerate(keys)}
            brier = 0.0
            for result in backtest_results:
                actual = 1.0 if result["actual_home_win"] else 0.0
                predicted = result["home_win_prob"]
                brier += (predicted - actual) ** 2
            return brier / len(backtest_results)

        keys = ["elo", "offense", "pitcher", "bullpen", "monte_carlo", "weather", "momentum", "injury"]
        x0 = [self.weights.get(k, 0.125) for k in keys]

        constraints = {"type": "eq", "fun": lambda w: sum(w) - 1.0}
        bounds = [(0.01, 0.40)] * 8

        result = minimize(objective, x0, method="SLSQP", bounds=bounds, constraints=constraints)

        if result.success:
            optimized = {keys[i]: round(result.x[i], 3) for i in range(8)}
            self.weights = optimized
            return optimized

        return self.weights

