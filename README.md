# Chase – Wildcard Route Optimizer

A **static web app** that helps cyclists find routes maximising elevation gain within a customisable radius constraint. All heavy lifting happens at **build time** so the final site can be hosted for free on GitHub Pages.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Build Machine (your laptop)                                        │
│                                                                     │
│  1. Docker / ORS  ──►  real cycling paths + elevation profiles      │
│  2. Python scripts ──►  routes.json + elevation.json                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
              │
              ▼  (static files committed / deployed)
┌─────────────────────────────────────────────────────────────────────┐
│  GitHub Pages  ──►  web/index.html + routes.json + elevation.json   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1 – Prerequisites

| Tool | Version |
|------|---------|
| Docker + Docker Compose | ≥ 20.x |
| Python | ≥ 3.11 |
| wget | any |

### 2 – Download OpenStreetMap data

```bash
bash download_osm.sh
```

This downloads the North Rhine-Westphalia `.pbf` extract from Geofabrik into `./docker/data/`.

### 3 – Start OpenRouteService

```bash
# First run builds the routing graphs (can take 10-30 min)
docker compose up -d

# Watch progress
docker compose logs -f openrouteservice
```

ORS is ready when `http://localhost:8080/ors/v2/health` returns `{"status":"ready"}`.

### 4 – Install Python dependencies

```bash
cd scripts
pip install -r requirements.txt
cd ..
```

### 5 – Download SRTM elevation tiles

```bash
python scripts/download_elevation.py --lat 51.5 --lon 7.0 --radius 80
```

Output: `build/elevation.tif`

### 6 – Compute and rank routes

```bash
python scripts/compute_routes.py --lat 51.5 --lon 7.0 --radius 80 --top 10
```

Output: `build/routes.json`, `build/elevation.json`

### 7 – (Optional) Export GPX files

```bash
python scripts/export_gpx.py
```

Output: `build/gpx/route_01.gpx`, `build/gpx/route_02.gpx`, …

### 8 – Preview locally

Open `web/index.html` via a local HTTP server (required for `fetch()` to work):

```bash
python -m http.server 8000 --directory .
# Then open http://localhost:8000/web/
```

---

## Project Structure

```
chase/
├── docker-compose.yml          # ORS container
├── docker/
│   ├── config/ors-config.yml   # ORS profile config (cycling-road + cycling-mountain)
│   ├── data/                   # OSM .pbf files (gitignored)
│   └── graphs/                 # Pre-built routing graphs (gitignored)
├── download_osm.sh             # One-time OSM data download
├── scripts/
│   ├── requirements.txt
│   ├── download_elevation.py   # Fetch SRTM tiles → build/elevation.tif
│   ├── compute_routes.py       # ORS routing + FIETS ranking → build/*.json
│   └── export_gpx.py           # JSON → GPX files
├── build/
│   ├── routes.json             # Route metadata (committed after build)
│   ├── elevation.json          # Elevation profiles (committed after build)
│   └── gpx/                    # GPX exports (optional)
└── web/
    ├── index.html              # App shell
    ├── style.css               # Dark theme
    └── app.js                  # Leaflet + Chart.js logic
```

---

## FIETS Score

Routes are ranked by the **FIETS difficulty score**, commonly used by Dutch cycling federations:

```
FIETS = (total_ascent_m²) / (distance_km × 10)
```

Higher score = steeper / more rewarding route.

---

## Customisation

| Parameter | Where |
|-----------|-------|
| Centre point & radius | CLI flags `--lat`, `--lon`, `--radius` |
| Number of top routes | `--top N` in `compute_routes.py` |
| ORS cycling profile | Edit `ORS_BASE` URL in `compute_routes.py` |
| Cycling profiles enabled | `docker/config/ors-config.yml` |

---

## Deployment (GitHub Pages)

After running the build scripts, commit `build/routes.json` and `build/elevation.json`, then push. GitHub Pages will serve `web/index.html` as a zero-runtime static app.
