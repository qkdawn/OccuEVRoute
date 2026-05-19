"""Aggregate nearby POI counts for each charging station."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree
from shapely.geometry import Point, shape


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATION_FILE = (
    PROJECT_ROOT
    / "ML"
    / "Data"
    / "UrbanEVDataset"
    / "UrbanEVDataset"
    / "20220901-20230228_station-processed"
    / "features"
    / "station_inf.csv"
)
DEFAULT_POI_FILE = (
    PROJECT_ROOT
    / "ML"
    / "Data"
    / "UrbanEVSupplemental"
    / "UrbanEVSupplemental"
    / "20221201-shenzhen-poi.csv"
)
DEFAULT_OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "station_poi_features.csv"
DEFAULT_BOUNDARY_FILE = PROJECT_ROOT / "data" / "processed" / "shenzhen_boundary.geojson"
EARTH_RADIUS_M = 6_371_008.8
POI_TYPE_COLUMNS = {
    "lifestyle services": "poi_lifestyle_services_count",
    "business and residential": "poi_business_residential_count",
    "food and beverage services": "poi_food_beverage_count",
}


def build_station_poi_features(
    station_file: Path,
    poi_file: Path,
    radius_m: float,
    boundary_file: Path = DEFAULT_BOUNDARY_FILE,
) -> pd.DataFrame:
    stations = pd.read_csv(station_file)
    pois = pd.read_csv(poi_file)
    required_station = {"station_id", "latitude", "longitude"}
    required_poi = {"primary_types", "latitude", "longitude"}
    missing_station = required_station - set(stations.columns)
    missing_poi = required_poi - set(pois.columns)
    if missing_station:
        raise ValueError(f"Station file is missing columns: {sorted(missing_station)}")
    if missing_poi:
        raise ValueError(f"POI file is missing columns: {sorted(missing_poi)}")

    stations = _filter_stations_to_boundary(stations, boundary_file)

    poi_coords = np.radians(pois[["latitude", "longitude"]].to_numpy(dtype=float))
    station_coords = np.radians(stations[["latitude", "longitude"]].to_numpy(dtype=float))
    tree = BallTree(poi_coords, metric="haversine")
    neighbor_indices = tree.query_radius(station_coords, r=radius_m / EARTH_RADIUS_M)

    rows = []
    poi_types = pois["primary_types"].reset_index(drop=True)
    for station, indices in zip(stations.itertuples(index=False), neighbor_indices):
        nearby_types = poi_types.iloc[indices]
        counts = nearby_types.value_counts()
        row = {
            "station_id": int(station.station_id),
            "poi_total_count": int(len(indices)),
        }
        for poi_type, column in POI_TYPE_COLUMNS.items():
            row[column] = int(counts.get(poi_type, 0))
        rows.append(row)
    return pd.DataFrame(rows)


def _filter_stations_to_boundary(stations: pd.DataFrame, boundary_file: Path) -> pd.DataFrame:
    if not boundary_file.exists():
        raise FileNotFoundError(f"Boundary GeoJSON not found: {boundary_file}")
    with boundary_file.open("r", encoding="utf-8") as file:
        geojson = json.load(file)
    boundary = shape(geojson["features"][0]["geometry"])
    inside = stations.apply(
        lambda station: boundary.covers(Point(float(station["longitude"]), float(station["latitude"]))),
        axis=1,
    )
    removed = int((~inside).sum())
    if removed:
        print(f"Filtered out {removed:,} stations outside Shenzhen boundary")
    return stations[inside].reset_index(drop=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build per-station POI aggregation features.")
    parser.add_argument("--stations", type=Path, default=DEFAULT_STATION_FILE)
    parser.add_argument("--poi", type=Path, default=DEFAULT_POI_FILE)
    parser.add_argument("--boundary", type=Path, default=DEFAULT_BOUNDARY_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_FILE)
    parser.add_argument("--radius-m", type=float, default=500.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    features = build_station_poi_features(args.stations, args.poi, args.radius_m, args.boundary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(args.output, index=False)
    print(f"Saved POI features: {args.output}")
    print(f"Stations: {len(features):,}")
    print(f"Radius: {args.radius_m:.0f}m")


if __name__ == "__main__":
    main()
