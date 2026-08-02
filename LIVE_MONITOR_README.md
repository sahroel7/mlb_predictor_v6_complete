# MLB Live Play-by-Play Monitor v1.0
## Modul Standalone untuk Integrasi ke Sistem Prediksi Anda

---

## 📦 File yang Dibutuhkan

Tambahkan 2 file ini ke repository Anda:

| File | Fungsi |
|------|--------|
| `live_monitor.py` | Modul utama (standalone, bisa jalan sendiri) |
| `live_integration.py` | Wrapper untuk integrasi ke sistem Anda |

**Tidak perlu mengubah kode prediksi Anda yang sudah ada!**

---

## 🚀 Cara Pakai

### Opsi 1: CLI Standalone (Tidak perlu sistem prediksi)

```bash
# Monitor 2 game
py live_monitor.py --games 745920,745921 --picks "Yankees,Dodgers" --duration 180

# Parameter:
#   --games    : Comma-separated game PKs dari MLB API
#   --picks    : Comma-separated nama tim yang dipilih
#   --duration : Durasi monitoring dalam menit (default: 180)
#   --stagger  : Jeda antar game dalam detik (default: 2.0)
#   --interval : Interval antar cycle dalam detik (default: 30)
```

### Opsi 2: Integrasi ke Sistem Prediksi Anda

**Di file main.py atau entry point Anda:**

```python
from live_integration import run_live_monitoring

# Setelah generate prediksi
predictions = [
    {
        "game_pk": 745920,
        "pick": "New York Yankees",
        "away_team": "Boston Red Sox",
        "home_team": "New York Yankees"
    },
    {
        "game_pk": 745921,
        "pick": "Los Angeles Dodgers",
        "away_team": "San Francisco Giants",
        "home_team": "Los Angeles Dodgers"
    }
]

# Jalankan monitoring
run_live_monitoring(predictions, duration_minutes=180)
```

**Atau pakai class:**

```python
from live_integration import LiveGameMonitor

monitor = LiveGameMonitor()

# Tambah dari prediksi Anda
for pred in predictions:
    monitor.add_prediction(pred)

# Atau tambah manual
monitor.add_game(
    game_pk=745920,
    pick_team="Yankees",
    away_team="Red Sox",
    home_team="Yankees"
)

# Mulai
monitor.start(duration_minutes=180)
```

---

## 📊 Data yang Ditampilkan per Game

Setiap cycle (30 detik), sistem menampilkan:

```
[20:45:02] [1/2] Red Sox @ Yankees (Pick: Yankees)
      Score: 3-5 | Inning 7 bottom | Runners: 1B, 3B | Outs: 1
      Pitcher: Jonathan Loáisiga | OK

[20:45:04] [2/2] Giants @ Dodgers (Pick: Dodgers)
      ⚠️  CASH OUT WARNING: Lead 1 run in inning 8
      Score: 2-3 | Runners: 2B | Pitcher: Blake Treinen
```

---

## 🚨 Jenis Alert

| Alert | Trigger | Action |
|-------|---------|--------|
| **CASH OUT** | Pick unggul tapi lead tipis (≤2 run) di inning 7+ | Jual tiket |
| **BUY LIVE** | Pick tertinggal tapi deficit ≤2 di inning 5-7 | Beli odds tinggi |
| **HOLD** | Unggul 3+ run di inning 8+ | Aman, tunggu |

---

## ⚙️ Konfigurasi Polling

| Parameter | Default | Rekomendasi |
|-----------|---------|-------------|
| `interval` | 30 detik | 30s (aman), 20s (lebih responsif) |
| `stagger` | 2 detik | 2s (<10 game), 3s (10-15 game) |
| `duration` | 180 menit | 240s (4 jam untuk game MLB) |

**Keamanan API:**
- 15 game × 2 detik stagger = 30 detik per cycle
- MLB Stats API tidak punya hard rate limit yang ketat
- 30 req/menit = sangat aman

---

## 🔧 Cara Dapatkan Game PK

Game PK adalah ID unik dari MLB API. Cara dapatkan:

```python
from live_monitor import mlb_api_get

# Dari schedule
schedule = mlb_api_get("/schedule/games/?sportId=1&date=07/22/2026")
for date in schedule.get("dates", []):
    for game in date.get("games", []):
        print(f"PK: {game['gamePk']} | {game['teams']['away']['team']['name']} @ {game['teams']['home']['team']['name']}")
```

Atau lihat di URL MLB.com:
- `https://www.mlb.com/gameday/yankees-vs-red-sox/2026/07/22/745920`
- Game PK = **745920**

---

## 📁 Struktur File di Repo Anda

```
mlb_predictor_v6_complete/     ← repo Anda
├── main.py                    ← kode Anda (TIDAK DIUBAH)
├── config.py                  ← kode Anda (TIDAK DIUBAH)
├── models.py                  ← kode Anda (TIDAK DIUBAH)
├── ...                        ← file lain Anda
├── live_monitor.py            ← ⭐ TAMBAH INI
└── live_integration.py        ← ⭐ TAMBAH INI
```

---

## ⚠️ Catatan

- Modul ini **standalone** — tidak mengubah kode prediksi Anda
- Hanya butuh `requests` (sudah ada di requirements Anda)
- Data dari MLB Stats API (official, gratis, real-time)
- Tidak perlu API key untuk live feed
- Bisa dihentikan kapan saja dengan `Ctrl + C`
