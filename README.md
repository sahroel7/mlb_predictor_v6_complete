# MLB Prediction System v6.0

## 🎯 Overview
Sistem prediksi MLB lengkap dengan integrasi **MLB Stats API (Official)** untuk data pitcher real-time, menggantikan pybaseball yang diblokir FanGraphs (403 Forbidden).

## 📁 File Structure

| File | Size | Purpose |
|------|------|---------|
| `main.py` | 6.4 KB | Entry point CLI |
| `config.py` | 5.0 KB | Configuration & utilities |
| `data_fetchers.py` | 20.7 KB | MLB API, Weather, ESPN Injury |
| `models.py` | 18.6 KB | ELO, Bullpen, Pitcher, Ensemble |
| `game_fetcher.py` | 4.4 KB | Morning vs afternoon comparison |
| `backtester.py` | 8.1 KB | Backtesting 300 games |
| `output_formatter.py` | 5.7 KB | Display formatting |
| `pybaseball_patch.py` | 3.8 KB | pybaseball compatibility patch |
| `mlb_api_pitchers.py` | 21.9 KB | Standalone MLB API pitcher module |
| `requirements_v6.txt` | 0.1 KB | Dependencies |

**Total: ~95 KB (10 files)**

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements_v6.txt
```

### 2. Set API Key (Optional but Recommended)
```bash
# Windows
set OPENWEATHER_API_KEY=your_key_here

# Linux/Mac
export OPENWEATHER_API_KEY=your_key_here
```
Get free API key: [openweathermap.org/api](https://openweathermap.org/api)

### 3. Run Predictions
```bash
# Predict today's games
py main.py predict

# Predict specific date
py main.py predict --date 07/22/2026

# Verbose output
py main.py predict -v
```

### 4. Other Commands
```bash
py main.py backtest          # Backtest 300 games
py main.py backtest -g 100   # Backtest 100 games
py main.py compare           # Morning vs afternoon comparison
py main.py tune              # Tune ensemble weights
py main.py interactive       # Interactive mode
```

## ⚾ Data Sources

### MLB Stats API (Primary)
- **Endpoint**: `statsapi.mlb.com/api/v1`
- **Data**: ERA, WHIP, K/9, BB/9, HR/9, FIP (calculated), IP, Games, Recent Form
- **Update**: Real-time, cached 6 hours
- **Rate Limit**: Generous (official API)

### OpenWeatherMap Forecast API
- **Endpoint**: `/data/2.5/forecast` (5-day/3-hour)
- **NOT**: `/data/2.5/weather` (current)
- **Logic**: Find forecast closest to game time
- **Dome Stadiums**: Auto-neutral (8 stadiums)

### ESPN Injury API
- **Endpoint**: `site.api.espn.com/apis/site/v2/sports/baseball/mlb/injuries`
- **Fallback**: Simulated data if API fails
- **Severity**: low/medium/high classification

## 🔧 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MLB Prediction v6.0                       │
├─────────────────────────────────────────────────────────────┤
│  main.py (CLI Entry)                                        │
│    ├── predict → data_fetchers → models → output_formatter  │
│    ├── backtest → backtester                                │
│    ├── compare → game_fetcher                               │
│    └── tune → models (Bayesian Optimization)                │
├─────────────────────────────────────────────────────────────┤
│  data_fetchers.py                                           │
│    ├── MLB Stats API: Schedule, Pitchers, Standings        │
│    ├── OpenWeatherMap: 5-day Forecast (not Current)          │
│    └── ESPN: Injury data with severity classification      │
├─────────────────────────────────────────────────────────────┤
│  models.py                                                  │
│    ├── ELOModel: Team ratings with home advantage            │
│    ├── BullpenModel: Bullpen strength estimation             │
│    ├── PitcherModel: Starting pitcher matchup analysis     │
│    ├── WeatherModel: Weather impact on scoring               │
│    ├── InjuryModel: Injury impact assessment               │
│    ├── PoissonMonteCarlo: Score prediction (10k sims)     │
│    └── EnsembleModel: Weighted ensemble + tuning           │
├─────────────────────────────────────────────────────────────┤
│  Cache: 6-hour JSON cache in /cache directory               │
└─────────────────────────────────────────────────────────────┘
```

## 📊 Model Weights (Default)

| Factor | Weight | Description |
|--------|--------|-------------|
| ELO | 0.20 | Team strength rating |
| Bullpen | 0.15 | Relief pitching quality |
| Pitcher | 0.25 | Starting pitcher matchup |
| Weather | 0.10 | Weather conditions |
| Home Advantage | 0.05 | Home field edge |
| Momentum | 0.10 | Recent team performance |
| Rest | 0.05 | Rest days impact |
| Injury | 0.10 | Key player injuries |

**Tuning**: Run `py main.py tune` to optimize via SLSQP.

## 🎯 Confidence Levels

| Level | Threshold | Color |
|-------|-----------|-------|
| HIGH | ≥ 65% | 🟢 |
| MEDIUM | ≥ 55% | 🟡 |
| LOW | < 55% | 🔴 |

## 🔄 pybaseball → MLB API Migration

| Feature | pybaseball | MLB Stats API |
|---------|-----------|---------------|
| Status | ❌ 403 Forbidden | ✅ Official, reliable |
| Real-time | ❌ Delayed | ✅ Real-time |
| FIP | ✅ Built-in | ✅ Calculated from raw |
| Game Logs | ✅ | ✅ Last 5 starts |
| Rate Limit | ❌ Strict | ✅ Generous |

## 🧪 Testing

```bash
# Run full system test
py main.py predict -v

# Run backtest
py main.py backtest -g 300

# Check pybaseball status
py -c "from pybaseball_patch import check_pybaseball_status; print(check_pybaseball_status())"
```

## ⚠️ Known Limitations

1. **Weather**: Requires OpenWeatherMap API key for real data. Falls back to simulation without key.
2. **Bullpen**: Uses estimated data (MLB API bullpen endpoint can be added in v6.1).
3. **Historical**: Backtest uses simulated data. For real historical backtest, integrate Retrosheet.
4. **Venue Coords**: Only major venues mapped for weather. Add more in `data_fetchers.py`.

## 📝 Changelog v6.0

- ✅ Replaced pybaseball with MLB Stats API (official, real-time)
- ✅ Added FIP calculation from raw MLB API data
- ✅ Added recent form (last 5 starts) per pitcher
- ✅ Integrated OpenWeatherMap Forecast API (not Current)
- ✅ Added ESPN injury scraper with severity classification
- ✅ Added weight tuning via scipy SLSQP optimization
- ✅ Added morning vs afternoon comparison
- ✅ 6-hour JSON caching system
- ✅ Full backtesting engine (300 games)
- ✅ pybaseball compatibility patch for fallback

## 📄 License

MIT License - Free for personal and commercial use.

## 🤝 Credits

- Data: MLB Advanced Media, OpenWeatherMap, ESPN
- FIP Formula: Tom Tango
- ELO System: Arpad Elo
