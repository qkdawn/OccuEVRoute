"""Validate route-planning data files required by the app."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

REQUIRED_FILES = {
    "shenzhen_boundary.geojson": "Shenzhen boundary used by the API and map",
    "shenzhen_drive_with_station_access.graphml": "Road graph with station access nodes",
    "station_road_access.csv": "Station-to-road access mapping",
    "station_poi_features.csv": "Nearby POI features for ranked stations",
    "landmark_distances.npz": "ALT A* landmark distance table",
    "ch_index.pkl": "Contraction hierarchy index",
}


def main() -> None:
    missing = []
    print(f"Checking route data in {PROCESSED_DIR}")
    for filename, description in REQUIRED_FILES.items():
        path = PROCESSED_DIR / filename
        if not path.exists():
            missing.append(filename)
            print(f"missing  {filename} - {description}")
            continue
        print(f"ok       {filename} ({path.stat().st_size / 1024 / 1024:.1f} MB)")

    if missing:
        joined = ", ".join(missing)
        raise SystemExit(f"Missing required route data files: {joined}")
    print("Route data is ready.")


if __name__ == "__main__":
    main()
