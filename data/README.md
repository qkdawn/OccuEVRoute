# Data

This directory holds local data files. Large generated artifacts are not tracked
by Git.

- `processed/`: Runtime route-planning artifacts used directly by Docker, the
  FastAPI backend, and the CLI.
- `external/`: OSMnx/OpenStreetMap downloads and road-network cache files used
  to regenerate `processed/`.
- `raw/`, `interim/`, `sample/`, `bundles/`: Optional local working folders for
  data experiments.

Route-planning runtime requires these files in `processed/`:

- `shenzhen_boundary.geojson`
- `shenzhen_drive_with_station_access.graphml`
- `station_road_access.csv`
- `station_poi_features.csv`
- `landmark_distances.npz`
- `ch_index.pkl`

Check a local checkout with:

```powershell
python scripts/check_route_data.py
```

For collaborators, publish `processed/` as a GitHub Release zip asset rather
than committing it to normal Git history. The current package is:

- [occuevroute-processed-data-2026-05-22.zip](https://github.com/qkdawn/OccuEVRoute/releases/download/data-v2026-05-22/occuevroute-processed-data-2026-05-22.zip)

Large UrbanEV source datasets remain under `ML/Data/`.
