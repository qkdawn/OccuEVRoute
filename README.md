# OccuEVRoute

Course project for intelligent EV charging route planning.

Given a user location, vehicle battery state, and user constraints, the system recommends suitable charging stations and routes by combining road-network search, battery feasibility, charger availability, station access distance, and nearby POI context.

## Project Structure

```text
OccuEVRoute/
├── backend/          # FastAPI recommendation service
├── frontend/         # React + Vite + Leaflet frontend
├── data/             # Small inputs, samples, and processed data
├── docs/             # Proposal, report, and slide materials
├── ML/               # Downloaded UrbanEV raw datasets
├── models/           # Trained XGBoost models and artifacts
├── AGENTS.md         # Project-level AI coding instructions
└── src/              # Core project code
```

## Source Layout

```text
src/
├── data_processing/      # Data loading, cleaning, and feature generation
├── route_planning/       # BFS / UCS / A*, energy constraints, and route planning
└── waiting_prediction/   # XGBoost waiting-time and occupancy analysis
```

## Run the Application

### Quick start with Docker

The app expects route-planning artifacts under `data/processed/`. These files are
not committed to Git because they are generated and large. Download the processed
data package from GitHub Releases:

- [occuevroute-processed-data-2026-05-22.zip](https://github.com/qkdawn/OccuEVRoute/releases/download/data-v2026-05-22/occuevroute-processed-data-2026-05-22.zip)

The occupancy predictor also expects the compact simulation-week runtime bundle
under `data/runtime/occupancy_week/`. Download it from the same release:

- [occuevroute-occupancy-runtime-week-2023-02-06.zip](https://github.com/qkdawn/OccuEVRoute/releases/download/data-v2026-05-22/occuevroute-occupancy-runtime-week-2023-02-06.zip)

Extract the processed data zip so its files sit directly under `data/processed/`.
Extract the occupancy runtime zip under `data/runtime/` so it creates
`data/runtime/occupancy_week/`, then verify:

```powershell
python scripts/check_route_data.py
python scripts/check_runtime_data.py
```

Start the app:

```powershell
docker compose up --build
```

Then open `http://localhost:9090`.

The backend is available at `http://localhost:9000`; a smoke test is:

```powershell
Invoke-RestMethod http://localhost:9000/api/health
```

### Local development

Install backend/runtime dependencies:

```powershell
python -m pip install -r backend/requirements.txt
```

Install test and lint tooling when you need local checks:

```powershell
python -m pip install -r requirements-dev.txt
```

Backend:

```powershell
python -m uvicorn backend.main:app --reload --port 9000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Then open `http://localhost:5173`.

## Data Preparation

Route recommendation uses the enhanced road network by default:

- `data/processed/shenzhen_drive_with_station_access.graphml`
- `data/processed/station_road_access.csv`
- `data/processed/landmark_distances.npz`
- `data/processed/ch_index.pkl`
- `data/processed/station_poi_features.csv`
- `data/processed/shenzhen_boundary.geojson`

The demo occupancy predictor reads a compact runtime bundle by default:

- `data/runtime/occupancy_week/station-processed/*.csv.gz`
- `data/runtime/occupancy_week/station-processed/features/station_inf.csv`
- `data/runtime/occupancy_week/station-processed/features/station_profiles.csv`
- `data/runtime/occupancy_week/weather_central.csv`

This bundle contains the February 6-12, 2023 simulation week plus compact
precomputed station profile features, so the app can run without the full
`ML/Data/` source dataset. It is published as
`occuevroute-occupancy-runtime-week-2023-02-06.zip` on the `data-v2026-05-22`
GitHub Release. To rebuild it from the full source data, run:

```powershell
python src/data_processing/extract_runtime_occupancy_week.py
```

To regenerate data from source inputs, install the full data-processing
and model-training environment:

```powershell
python -m pip install -r requirements.txt
```

Then run:

```powershell
python src/data_processing/build_shenzhen_boundary_geojson.py
python src/data_processing/download_road_network_tiles.py
python src/data_processing/build_station_graph.py
python src/data_processing/build_station_poi_features.py
python src/data_processing/build_landmark_distances.py
python src/route_planning/ch_preprocess.py
```

The road download step includes regular drivable roads plus `highway=service`
internal roads, filters out `access=private/no` edges, clips the merged graph
to the Shenzhen boundary, and keeps the main Shenzhen road component. Station
features are also filtered to the Shenzhen boundary. A* uses the generated
16-landmark ALT table with directed forward/reverse distances and an undirected
fallback table. CH Dijkstra uses the generated `ch_index.pkl` contraction
hierarchy index.

Large raw datasets remain under `ML/Data/`.

## Release Data Package

Processed route data and compact runtime occupancy data should be published as
GitHub Release assets rather than committed to the repository. The current local
packages are:

```text
release/occuevroute-processed-data-2026-05-22.zip
release/occuevroute-occupancy-runtime-week-2023-02-06.zip
```

It is published on the `data-v2026-05-22` GitHub Release:

```text
https://github.com/qkdawn/OccuEVRoute/releases/tag/data-v2026-05-22
```

## Occupancy Prediction

The current multi-horizon occupancy model is documented in
`docs/models/occupancy_horizon_model.md`. It predicts station occupancy for
arbitrary future offsets within 0-120 minutes using XGBoost, lagged occupancy
features, time/weather/price context, POI features, and station-neighbor
profiles.

## 怎么跑

开两个powershell
```
前端窗口
cd E:\occuEVRoute\OccuEVRoute-main\frontend
$env:PATH = 'E:\occuEVRoute\OccuEVRoute-main\.tools\node-v22.21.1-win-x64;' + $env:PATH
& 'E:\occuEVRoute\OccuEVRoute-main\.tools\node-v22.21.1-win-x64\npm.cmd' run dev -- --host 127.0.0.1 --port 5173
```
```
后端窗口
 cd E:\occuEVRoute\OccuEVRoute-main
 .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 9000
```
路径是你的路径，最后在浏览器打开http://127.0.0.1:5173/
