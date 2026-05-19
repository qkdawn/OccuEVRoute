"""Build a road graph with charging-station access points inserted as graph nodes."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import networkx as nx
import osmnx as ox
import pandas as pd
from shapely.geometry import LineString, Point
from shapely.geometry import shape
from shapely.ops import substring


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GRAPH_FILE = PROJECT_ROOT / "data" / "external" / "shenzhen_drive.graphml"
DEFAULT_RAW_STATION_FILE = (
    PROJECT_ROOT
    / "ML"
    / "Data"
    / "UrbanEVDataset"
    / "UrbanEVDataset"
    / "20220901-20230228_station-processed"
    / "features"
    / "station_inf.csv"
)
DEFAULT_STATION_ACCESS_FILE = PROJECT_ROOT / "data" / "processed" / "station_road_access.csv"
DEFAULT_OUTPUT_GRAPH_FILE = PROJECT_ROOT / "data" / "processed" / "shenzhen_drive_with_station_access.graphml"
DEFAULT_BOUNDARY_FILE = PROJECT_ROOT / "data" / "processed" / "shenzhen_boundary.geojson"
ACCESS_SPEED_KPH = 15.0


def build_station_graph(
    graph_file: Path,
    station_file: Path,
    boundary_file: Path = DEFAULT_BOUNDARY_FILE,
) -> tuple[nx.MultiDiGraph, pd.DataFrame]:
    graph = ox.load_graphml(graph_file)
    stations = pd.read_csv(station_file)
    stations = _filter_stations_to_boundary(stations, boundary_file)
    stations = _ensure_station_projection_data(graph, stations)

    graph = graph.copy()
    stations = stations.copy()
    stations["access_node"] = stations["station_id"].map(lambda station_id: f"access_{int(station_id)}")

    _add_access_nodes(graph, stations)
    split_groups = _directed_split_groups(graph, stations)
    for (u, v, key), group in split_groups.items():
        if graph.has_edge(u, v, key):
            _split_directed_edge(graph, u, v, key, group)

    return graph, stations


def _filter_stations_to_boundary(stations: pd.DataFrame, boundary_file: Path) -> pd.DataFrame:
    if not boundary_file.exists():
        raise FileNotFoundError(f"Boundary GeoJSON not found: {boundary_file}")
    required = {"longitude", "latitude"}
    missing = required - set(stations.columns)
    if missing:
        raise ValueError(f"Station file is missing columns: {sorted(missing)}")

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


def _ensure_station_projection_data(graph: nx.MultiDiGraph, stations: pd.DataFrame) -> pd.DataFrame:
    projection_fields = {
        "road_edge_u",
        "road_edge_v",
        "road_edge_key",
        "road_projection_latitude",
        "road_projection_longitude",
        "road_snap_distance_m",
    }
    if projection_fields.issubset(stations.columns):
        _validate_stations(stations)
        return stations

    required = {"station_id", "longitude", "latitude"}
    missing = required - set(stations.columns)
    if missing:
        raise ValueError(f"Station file is missing columns: {sorted(missing)}")

    nearest_edges = ox.distance.nearest_edges(
        graph,
        X=stations["longitude"].to_numpy(),
        Y=stations["latitude"].to_numpy(),
    )
    mapped = stations.copy()
    edge_snaps = [
        _edge_snap(graph, edge, float(station.latitude), float(station.longitude))
        for edge, station in zip(nearest_edges, mapped.itertuples(index=False))
    ]
    for field in projection_fields:
        mapped[field] = [snap[field] for snap in edge_snaps]
    return mapped


def _validate_stations(stations: pd.DataFrame) -> None:
    required = {
        "station_id",
        "longitude",
        "latitude",
        "road_edge_u",
        "road_edge_v",
        "road_edge_key",
        "road_projection_latitude",
        "road_projection_longitude",
        "road_snap_distance_m",
    }
    missing = required - set(stations.columns)
    if missing:
        raise ValueError(f"Station file is missing columns: {sorted(missing)}")


def _edge_snap(graph: nx.MultiDiGraph, edge: tuple, latitude: float, longitude: float) -> dict:
    u, v, key = edge
    edge_attrs = graph.get_edge_data(u, v, key)
    geometry = edge_attrs.get("geometry")
    if geometry is None:
        geometry = _edge_line(graph, u, v, edge_attrs)

    point = Point(longitude, latitude)
    projected_point = geometry.interpolate(geometry.project(point))
    return {
        "road_edge_u": str(u),
        "road_edge_v": str(v),
        "road_edge_key": int(key),
        "road_projection_latitude": float(projected_point.y),
        "road_projection_longitude": float(projected_point.x),
        "road_snap_distance_m": _haversine_m(
            latitude,
            longitude,
            float(projected_point.y),
            float(projected_point.x),
        ),
    }


def _add_access_nodes(graph: nx.MultiDiGraph, stations: pd.DataFrame) -> None:
    for station in stations.itertuples(index=False):
        access_node = str(station.access_node)
        graph.add_node(
            access_node,
            x=float(station.road_projection_longitude),
            y=float(station.road_projection_latitude),
            node_type="station_access",
            station_id=int(station.station_id),
        )


def _directed_split_groups(graph: nx.MultiDiGraph, stations: pd.DataFrame) -> dict[tuple[Any, Any, int], list[pd.Series]]:
    groups: dict[tuple[Any, Any, int], dict[int, pd.Series]] = defaultdict(dict)
    for _, station in stations.iterrows():
        u = _coerce_node_id(graph, station["road_edge_u"])
        v = _coerce_node_id(graph, station["road_edge_v"])
        key = int(station["road_edge_key"])
        station_id = int(station["station_id"])
        groups[(u, v, key)][station_id] = station
        for reverse_key in graph.get_edge_data(v, u, default={}):
            groups[(v, u, int(reverse_key))][station_id] = station
    return {edge: list(station_by_id.values()) for edge, station_by_id in groups.items()}


def _split_directed_edge(
    graph: nx.MultiDiGraph,
    u,
    v,
    key: int,
    stations: list[pd.Series],
) -> None:
    edge_attrs = dict(graph.get_edge_data(u, v, key))
    line = _edge_line(graph, u, v, edge_attrs)
    sorted_stations = sorted(
        stations,
        key=lambda station: line.project(_station_projection_point(station)),
    )
    original_length_m = _safe_float(edge_attrs.get("length"), _haversine_m(*_node_lat_lon(graph, u), *_node_lat_lon(graph, v)))
    original_time_s = _safe_float(edge_attrs.get("travel_time"), original_length_m / 1000 / ACCESS_SPEED_KPH * 3600)

    points = [(u, Point(float(graph.nodes[u]["x"]), float(graph.nodes[u]["y"])), 0.0)]
    for station in sorted_stations:
        point = _station_projection_point(station)
        points.append((str(station["access_node"]), point, _line_fraction(line, line.project(point))))
    points.append((v, Point(float(graph.nodes[v]["x"]), float(graph.nodes[v]["y"])), 1.0))

    graph.remove_edge(u, v, key)
    for index, ((from_node, _, from_fraction), (to_node, _, to_fraction)) in enumerate(zip(points, points[1:])):
        segment_attrs = _segment_edge_attrs(
            edge_attrs,
            line,
            original_length_m,
            original_time_s,
            from_fraction,
            to_fraction,
        )
        graph.add_edge(from_node, to_node, key=index, **segment_attrs)


def _segment_edge_attrs(
    edge_attrs: dict,
    line: LineString,
    original_length_m: float,
    original_time_s: float,
    from_fraction: float,
    to_fraction: float,
) -> dict:
    low = min(from_fraction, to_fraction)
    high = max(from_fraction, to_fraction)
    segment_fraction = max(0.0, high - low)
    segment = substring(line, low, high, normalized=True)
    if from_fraction > to_fraction:
        segment = LineString(list(segment.coords)[::-1])

    attrs = dict(edge_attrs)
    attrs["length"] = original_length_m * segment_fraction
    attrs["travel_time"] = original_time_s * segment_fraction
    attrs["geometry"] = segment
    attrs["station_split"] = True
    return attrs


def _edge_line(graph: nx.MultiDiGraph, u, v, edge_attrs: dict) -> LineString:
    geometry = edge_attrs.get("geometry")
    if geometry is not None:
        return geometry
    return LineString(
        [
            (float(graph.nodes[u]["x"]), float(graph.nodes[u]["y"])),
            (float(graph.nodes[v]["x"]), float(graph.nodes[v]["y"])),
        ]
    )


def _station_projection_point(station: pd.Series) -> Point:
    return Point(float(station["road_projection_longitude"]), float(station["road_projection_latitude"]))


def _line_fraction(line: LineString, projected_distance: float) -> float:
    if line.length == 0:
        return 0.0
    return max(0.0, min(1.0, projected_distance / line.length))


def _coerce_node_id(graph: nx.MultiDiGraph, value):
    if value in graph.nodes:
        return value
    try:
        int_value = int(value)
    except (TypeError, ValueError):
        return value
    if int_value in graph.nodes:
        return int_value
    return value


def _node_lat_lon(graph: nx.MultiDiGraph, node) -> tuple[float, float]:
    data = graph.nodes[node]
    return float(data["y"]), float(data["x"])


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_m = 6371008.8
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    return 2 * radius_m * math.asin(math.sqrt(a))


def _safe_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a Shenzhen road graph with charging-station access nodes.")
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH_FILE)
    parser.add_argument("--stations", type=Path, default=DEFAULT_RAW_STATION_FILE)
    parser.add_argument("--boundary", type=Path, default=DEFAULT_BOUNDARY_FILE)
    parser.add_argument("--output-station-access", type=Path, default=DEFAULT_STATION_ACCESS_FILE)
    parser.add_argument("--output-graph", type=Path, default=DEFAULT_OUTPUT_GRAPH_FILE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.graph.exists():
        raise FileNotFoundError(f"Road graph not found: {args.graph}")
    if not args.stations.exists():
        raise FileNotFoundError(f"Station-road mapping not found: {args.stations}")

    graph, stations = build_station_graph(args.graph, args.stations, args.boundary)
    args.output_graph.parent.mkdir(parents=True, exist_ok=True)
    args.output_station_access.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(graph, args.output_graph)
    stations.to_csv(args.output_station_access, index=False)

    print(f"Saved enhanced graph: {args.output_graph}")
    print(f"Saved station-access mapping: {args.output_station_access}")
    print(f"Nodes: {graph.number_of_nodes():,}")
    print(f"Edges: {graph.number_of_edges():,}")
    print(f"Stations inserted: {len(stations):,}")


if __name__ == "__main__":
    main()
