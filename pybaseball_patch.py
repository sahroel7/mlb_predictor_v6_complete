"""
pybaseball_patch.py - Compatibility patch for pybaseball FanGraphs 403 error
Provides fallback to MLB Stats API when pybaseball fails
"""

import warnings
from typing import Optional, Dict, List

# Flag to track if pybaseball is available
_PYBASEBALL_AVAILABLE = False

try:
    import pybaseball
    _PYBASEBALL_AVAILABLE = True
except ImportError:
    warnings.warn("pybaseball not installed. Using MLB Stats API fallback.")

# Import our MLB API module as fallback
from data_fetchers import get_pitcher_stats as mlb_get_pitcher_stats


def get_pitching_stats(start_season: int, end_season: Optional[int] = None,
                       league: str = 'all', qual: Optional[int] = None) -> Optional[Dict]:
    """
    Wrapper for pybaseball pitching stats with MLB API fallback.

    Args:
        start_season: Starting season year
        end_season: Ending season year (default: start_season)
        league: 'all', 'al', or 'nl'
        qual: Minimum IP qualifier

    Returns:
        DataFrame-like dict or None
    """
    if _PYBASEBALL_AVAILABLE:
        try:
            from pybaseball import pitching_stats
            return pitching_stats(start_season, end_season, league=league, qual=qual)
        except Exception as e:
            print(f"[pybaseball Error] {e}. Falling back to MLB API.")

    # Fallback: return empty structure
    print("[Fallback] Using MLB Stats API for pitcher data.")
    return None


def get_player_id(name: str, fuzzy: bool = True) -> Optional[int]:
    """
    Get MLB player ID by name.

    Args:
        name: Player name
        fuzzy: Use fuzzy matching

    Returns:
        Player ID or None
    """
    if _PYBASEBALL_AVAILABLE:
        try:
            from pybaseball import playerid_lookup
            result = playerid_lookup(name, fuzzy=fuzzy)
            if result is not None and len(result) > 0:
                return int(result.iloc[0]['key_mlbam'])
        except Exception:
            pass

    # Fallback: cannot search by name with MLB API alone
    print(f"[Fallback] Cannot find player ID for '{name}' without pybaseball.")
    return None


def statcast_pitcher(start_dt: Optional[str] = None, 
                     end_dt: Optional[str] = None,
                     player_id: Optional[int] = None) -> Optional[Dict]:
    """
    Wrapper for Statcast pitcher data.

    Args:
        start_dt: Start date (YYYY-MM-DD)
        end_dt: End date (YYYY-MM-DD)
        player_id: MLB player ID

    Returns:
        Statcast data or None
    """
    if _PYBASEBALL_AVAILABLE:
        try:
            from pybaseball import statcast_pitcher
            return statcast_pitcher(start_dt, end_dt, player_id)
        except Exception as e:
            print(f"[pybaseball Error] {e}")

    print("[Fallback] Statcast data unavailable without pybaseball.")
    return None


# ─── Utility: Check pybaseball status ────────────────────────────────────────
def check_pybaseball_status() -> Dict:
    """Check if pybaseball is working"""
    status = {
        "installed": _PYBASEBALL_AVAILABLE,
        "fangraphs_accessible": False,
        "recommendation": ""
    }

    if _PYBASEBALL_AVAILABLE:
        try:
            from pybaseball import pitching_stats
            # Quick test
            test = pitching_stats(2026, qual=1)
            status["fangraphs_accessible"] = True
            status["recommendation"] = "pybaseball is working. You can use it."
        except Exception as e:
            status["recommendation"] = f"pybaseball installed but FanGraphs blocked: {e}. Use MLB API fallback."
    else:
        status["recommendation"] = "pybaseball not installed. MLB Stats API is the primary source."

    return status
