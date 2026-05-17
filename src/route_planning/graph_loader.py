"""Load road network and station-node data for route planning."""

from __future__ import annotations

from pathlib import Path

import osmnx as ox
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GRAPH_FILE = PROJECT_ROOT / "data" / "external" / "shenzhen_drive.graphml"
DEFAULT_STATION_NODE_FILE = PROJECT_ROOT / "data" / "processed" / "station_road_nodes.csv"


def load_road_graph(graph_file: Path = DEFAULT_GRAPH_FILE):
    """Load the OSMnx road graph from GraphML."""
    if not graph_file.exists():
        raise FileNotFoundError(f"Road graph not found: {graph_file}")
    return ox.load_graphml(graph_file)


def load_station_nodes(station_file: Path = DEFAULT_STATION_NODE_FILE) -> pd.DataFrame:
    """Load charging stations with their nearest road nodes."""
    if not station_file.exists():
        raise FileNotFoundError(f"Station-road mapping not found: {station_file}")
    stations = pd.read_csv(station_file)
    required = {"station_id", "longitude", "latitude", "charge_count", "road_node"}
    missing = required - set(stations.columns)
    if missing:
        raise ValueError(f"Station-road mapping is missing columns: {sorted(missing)}")
    return stations


def nearest_road_node(graph, latitude: float, longitude: float) -> str:
    """Map a latitude/longitude point to the nearest road graph node."""
    return ox.distance.nearest_nodes(graph, X=longitude, Y=latitude)
