"""
config.py - Configuration & Utilities for MLB Prediction System v6.0
"""

import os
import json
from datetime import datetime

# ─── API Keys ───────────────────────────────────────────────────────────────
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "a53507467d2588672e108fca96999af9")

# ─── MLB Stats API ────────────────────────────────────────────────────────────
MLB_API_BASE = "https://statsapi.mlb.com/api/v1"

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
DATA_DIR = os.path.join(BASE_DIR, "data")

# Ensure directories exist
for d in [CACHE_DIR, DATA_DIR]:
    os.makedirs(d, exist_ok=True)

# ─── Dome Stadiums (No Weather Impact) ────────────────────────────────────────
DOME_STADIUMS = {
    "Tropicana Field", "Rogers Centre", "Minute Maid Park",
    "T-Mobile Park", "Globe Life Field", "loanDepot park",
    "American Family Field", "Chase Field"
}

# ─── Team Mappings ────────────────────────────────────────────────────────────
TEAM_ID_MAP = {
    "ARI": 109, "ATL": 144, "BAL": 110, "BOS": 111, "CHC": 112,
    "CIN": 113, "CLE": 114, "COL": 115, "CWS": 145, "DET": 116,
    "HOU": 117, "KC": 118, "LAA": 108, "LAD": 119, "MIA": 146,
    "MIL": 158, "MIN": 142, "NYM": 121, "NYY": 147, "OAK": 133,
    "PHI": 143, "PIT": 134, "SD": 135, "SEA": 136, "SF": 137,
    "STL": 138, "TB": 139, "TEX": 140, "TOR": 141, "WSH": 120
}

TEAM_ABBREV_MAP = {v: k for k, v in TEAM_ID_MAP.items()}

TEAM_NAMES = {
    109: "Arizona Diamondbacks", 144: "Atlanta Braves", 110: "Baltimore Orioles",
    111: "Boston Red Sox", 112: "Chicago Cubs", 113: "Cincinnati Reds",
    114: "Cleveland Guardians", 115: "Colorado Rockies", 145: "Chicago White Sox",
    116: "Detroit Tigers", 117: "Houston Astros", 118: "Kansas City Royals",
    108: "Los Angeles Angels", 119: "Los Angeles Dodgers", 146: "Miami Marlins",
    158: "Milwaukee Brewers", 142: "Minnesota Twins", 121: "New York Mets",
    147: "New York Yankees", 133: "Oakland Athletics", 143: "Philadelphia Phillies",
    134: "Pittsburgh Pirates", 135: "San Diego Padres", 136: "Seattle Mariners",
    137: "San Francisco Giants", 138: "St. Louis Cardinals", 139: "Tampa Bay Rays",
    140: "Texas Rangers", 141: "Toronto Blue Jays", 120: "Washington Nationals"
}

# ─── Venue Coordinates (All 30 MLB Stadiums) ──────────────────────────────────
VENUE_COORDINATES = {
    "Yankee Stadium": (40.8296, -73.9262),
    "Fenway Park": (42.3467, -71.0972),
    "Wrigley Field": (41.9484, -87.6553),
    "Dodger Stadium": (34.0739, -118.2400),
    "Oracle Park": (37.7786, -122.3893),
    "Citi Field": (40.7571, -73.8458),
    "Citizens Bank Park": (39.9061, -75.1665),
    "Truist Park": (33.8908, -84.4678),
    "Busch Stadium": (38.6226, -90.1928),
    "PNC Park": (40.4469, -80.0057),
    "Great American Ball Park": (39.0979, -84.5082),
    "American Family Field": (43.0280, -87.9712),
    "Target Field": (44.9817, -93.2777),
    "Guaranteed Rate Field": (41.8300, -87.6339),
    "Comerica Park": (42.3390, -83.0485),
    "Progressive Field": (41.4962, -81.6852),
    "Kauffman Stadium": (39.0517, -94.4803),
    "Coors Field": (39.7559, -104.9942),
    "Chase Field": (33.4453, -112.0667),
    "Petco Park": (32.7076, -117.1570),
    "Angel Stadium": (33.8003, -117.8827),
    "Oakland Coliseum": (37.7516, -122.2005),
    "Sutter Health Park": (38.5802, -121.5065),
    "T-Mobile Park": (47.5914, -122.3323),
    "Globe Life Field": (32.7473, -97.0825),
    "Minute Maid Park": (29.7573, -95.3555),
    "Tropicana Field": (27.7682, -82.6534),
    "loanDepot park": (25.7781, -80.2197),
    "Rogers Centre": (43.6414, -79.3894),
    "Nationals Park": (38.8730, -77.0074),
    "Oriole Park at Camden Yards": (39.2839, -76.6198)
}

# ─── Model Weights (Balanced - Including Offense & Monte Carlo) ──────────────
DEFAULT_WEIGHTS = {
    "elo": 0.20,
    "offense": 0.20,
    "pitcher": 0.25,
    "bullpen": 0.15,
    "monte_carlo": 0.10,
    "weather": 0.05,
    "momentum": 0.03,
    "injury": 0.02
}

# ─── FIP Constant ─────────────────────────────────────────────────────────────
FIP_CONSTANT = 3.15

# ─── Confidence Thresholds ────────────────────────────────────────────────────
CONFIDENCE_THRESHOLDS = {
    "HIGH": 0.65,
    "MEDIUM": 0.55,
    "LOW": 0.0
}

# ─── Cache Duration ───────────────────────────────────────────────────────────
CACHE_DURATION_HOURS = 6

# ─── Utility Functions ────────────────────────────────────────────────────────
def get_today_date() -> str:
    """Return today's date as YYYY-MM-DD"""
    return datetime.now().strftime("%Y-%m-%d")


def format_date_api(date_obj: datetime) -> str:
    """Format datetime for MLB API"""
    return date_obj.strftime("%m/%d/%Y")

def load_json(filepath: str) -> dict:
    """Load JSON file safely"""
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return {}

def save_json(filepath: str, data: dict):
    """Save data to JSON file"""
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

def print_section(title: str):
    """Print formatted section header"""
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)
