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

Docker:

```powershell
docker compose up --build
```

Then open `http://localhost:9090`.

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
- `data/processed/station_poi_features.csv`
- `data/processed/shenzhen_boundary.geojson`

If these files are missing, run:

```powershell
python src/data_processing/build_shenzhen_boundary_geojson.py
python src/data_processing/download_road_network_tiles.py
python src/data_processing/build_station_graph.py
python src/data_processing/build_station_poi_features.py
python src/data_processing/build_landmark_distances.py
```

The road download step includes regular drivable roads plus `highway=service`
internal roads, filters out `access=private/no` edges, clips the merged graph
to the Shenzhen boundary, and keeps the main Shenzhen road component. Station
features are also filtered to the Shenzhen boundary. A* uses the generated
16-landmark ALT table with directed forward/reverse distances and an undirected
fallback table.

Large raw datasets remain under `ML/Data/`.
