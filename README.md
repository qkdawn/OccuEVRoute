# OccuEVRoute

OccuEVRoute is a course-demo EV charging route planner for Shenzhen. It combines road-network search, battery feasibility, station availability, route diagnostics, occupancy prediction, and nearby POI context to recommend charging stations.

The app runs locally with FastAPI and Vite. Docker is not required.

## Project Layout

```text
OccuEVRoute/
├── backend/          # FastAPI API schemas, routes, and response shaping
├── frontend/         # React + Vite + Leaflet map UI
├── src/
│   ├── data_processing/      # Data ingestion and generated route artifacts
│   ├── route_planning/       # BFS, UCS, A*, ALT A*, CH, scoring, constraints
│   └── waiting_prediction/   # Occupancy and waiting prediction models
├── data/             # Runtime data and generated route artifacts
├── docs/             # Reports, diagrams, and model notes
├── models/           # Runtime model artifacts
└── start-occuevroute.bat
```

## Runtime Data

The route planner expects generated artifacts under `data/processed/`, and the occupancy predictor expects a compact runtime bundle under `data/runtime/occupancy_week/`. These large files are published as GitHub Release assets instead of being committed.

Download:

- [occuevroute-processed-data-2026-05-27.zip](https://github.com/qkdawn/OccuEVRoute/releases/download/data-v2026-05-27/occuevroute-processed-data-2026-05-27.zip)
- [occuevroute-occupancy-runtime-week-2023-02-06.zip](https://github.com/qkdawn/OccuEVRoute/releases/download/data-v2026-05-27/occuevroute-occupancy-runtime-week-2023-02-06.zip)

Extract the first zip so its files sit directly under `data/processed/`. Extract the second zip under `data/runtime/` so it creates `data/runtime/occupancy_week/`.

Verify the data:

```powershell
python scripts/check_route_data.py
python scripts/check_runtime_data.py
```

Important route artifacts include:

```text
data/processed/shenzhen_drive_with_station_access.graphml
data/processed/station_road_access.csv
data/processed/landmark_distances.npz
data/processed/ch_index.pkl
data/processed/station_poi_features.csv
data/processed/shenzhen_boundary.geojson
```

## Run The Demo

Install Python dependencies first if needed:

```powershell
python -m pip install -r backend/requirements.txt
```

Start the full local demo:

```powershell
.\start-occuevroute.bat
```

The launcher:

- starts FastAPI on `http://127.0.0.1:9000`
- waits for `/api/health` and `/api/boundary`
- builds and serves the frontend with Vite preview on `http://127.0.0.1:9090`
- opens `http://127.0.0.1:9090`

Check that Python and npm are available without starting the app:

```powershell
.\start-occuevroute.bat --check
```

## Manual Startup

Backend:

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 9000
```

Frontend preview:

```powershell
cd frontend
npm install
npm run deploy
```

Open `http://127.0.0.1:9090`. Vite proxies `/api` requests to `http://127.0.0.1:9000`.

Backend health check:

```powershell
Invoke-RestMethod http://127.0.0.1:9000/api/health
```

## Local Development

Install development dependencies:

```powershell
python -m pip install -r requirements-dev.txt
cd frontend
npm install
```

Backend with reload:

```powershell
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 9000
```

Frontend dev server:

```powershell
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173`. The dev server also proxies `/api` to `http://127.0.0.1:9000`.

## API Surface

The frontend uses these backend endpoints:

```text
GET  /api/health
GET  /api/boundary
GET  /api/location-search
POST /api/recommendations
```

Recommendation responses include:

- `route_coordinates`: true drivable route geometry
- `route_trace_coordinates`: final parent/query path nodes for map explanation
- `search_trace.candidate_route_events`: timestamped candidate route snapshots shown during playback
- `search_trace.layers`: search frontier nodes and trace edges

## Search Visualization

The map playback is designed for course explanation:

- regular search points show the latest visible frontier
- CH search points are emphasized, but CH shortcut trace edges are hidden
- candidate route points appear only after the search step that produced them
- final route nodes appear after search playback completes
- the thick blue route always uses true drivable road geometry

For CH, the query uses shortcut weights internally for speed. Shortcuts are not drawn as road geometry during search; the final route is reconstructed and expanded back to real road geometry.

## Checks

Backend/search trace tests:

```powershell
python -m pytest tests/test_search_traces.py
```

Frontend checks:

```powershell
cd frontend
npm run lint
npm run build
```

## Regenerate Route Data

Install the full data-processing environment:

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

The road download step includes regular drivable roads plus `highway=service` internal roads, filters out `access=private/no` edges, clips the graph to the Shenzhen boundary, and keeps the main Shenzhen road component.

## Occupancy Model

The runtime occupancy bundle contains the February 6-12, 2023 simulation week plus compact station profile features. To rebuild it from the full UrbanEV source data, run:

```powershell
python src/data_processing/extract_runtime_occupancy_week.py
```

The current multi-horizon occupancy model is documented in `docs/models/occupancy_horizon_model.md`.
