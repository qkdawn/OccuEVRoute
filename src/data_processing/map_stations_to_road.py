"""Map UrbanEV charging stations to their nearest road-network nodes."""

from __future__ import annotations

import argparse
from pathlib import Path

import osmnx as ox
import pandas as pd


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
DEFAULT_GRAPH_FILE = PROJECT_ROOT / "data" / "external" / "shenzhen_drive.graphml"
DEFAULT_OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "station_road_nodes.csv"


def map_stations(
    station_file: Path,
    graph_file: Path,
    max_distance_m: float | None = None,
) -> pd.DataFrame:
    stations = pd.read_csv(station_file)
    required = {"station_id", "longitude", "latitude"}
    missing = required - set(stations.columns)
    if missing:
        raise ValueError(f"Station file is missing columns: {sorted(missing)}")

    graph = ox.load_graphml(graph_file)
    nearest_nodes, distances = ox.distance.nearest_nodes(
        graph,
        X=stations["longitude"].to_numpy(),
        Y=stations["latitude"].to_numpy(),
        return_dist=True,
    )

    mapped = stations.copy()
    mapped["road_node"] = nearest_nodes
    mapped["road_node_distance_m"] = distances
    if max_distance_m is not None:
        mapped = mapped[mapped["road_node_distance_m"] <= max_distance_m].copy()
    return mapped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Map charging stations to road nodes.")
    parser.add_argument("--station-file", type=Path, default=DEFAULT_STATION_FILE)
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_FILE)
    parser.add_argument(
        "--max-distance-m",
        type=float,
        default=None,
        help="Optionally keep only stations within this distance of the road graph.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.station_file.exists():
        raise FileNotFoundError(f"Station file not found: {args.station_file}")
    if not args.graph.exists():
        raise FileNotFoundError(
            f"Road graph not found: {args.graph}. Run download_road_network.py first."
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    mapped = map_stations(args.station_file, args.graph, args.max_distance_m)
    mapped.to_csv(args.output, index=False)

    print(f"Saved station-road mapping: {args.output}")
    print(f"Stations: {len(mapped):,}")
    print(
        "Nearest-node distance meters: "
        f"mean={mapped['road_node_distance_m'].mean():.1f}, "
        f"max={mapped['road_node_distance_m'].max():.1f}"
    )


if __name__ == "__main__":
    main()
