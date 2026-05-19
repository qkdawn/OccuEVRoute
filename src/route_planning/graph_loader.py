"""Load road network and station-node data for route planning."""

from __future__ import annotations

from pathlib import Path
import math

import networkx as nx
import pandas as pd
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree
from shapely.ops import substring
from shapely import wkt


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GRAPH_FILE = PROJECT_ROOT / "data" / "processed" / "shenzhen_drive_with_station_access.graphml"
DEFAULT_STATION_ACCESS_FILE = PROJECT_ROOT / "data" / "processed" / "station_road_access.csv"


def load_road_graph(graph_file: Path = DEFAULT_GRAPH_FILE):
    """Load the road graph with pre-inserted charging-station access nodes."""
    if not graph_file.exists():
        raise FileNotFoundError(
            f"Enhanced road graph not found: {graph_file}. "
            "Run src/data_processing/build_station_graph.py first."
        )
    graph = nx.read_graphml(graph_file, force_multigraph=True)
    _restore_graphml_edge_types(graph)
    return graph


def load_station_access(station_file: Path = DEFAULT_STATION_ACCESS_FILE) -> pd.DataFrame:
    """Load charging stations with their nearest road-edge projection data."""
    if not station_file.exists():
        raise FileNotFoundError(f"Station-road mapping not found: {station_file}")
    stations = pd.read_csv(station_file)
    required = {
        "station_id",
        "longitude",
        "latitude",
        "charge_count",
        "road_edge_u",
        "road_edge_v",
        "road_edge_key",
        "road_projection_latitude",
        "road_projection_longitude",
        "road_snap_distance_m",
        "access_node",
    }
    missing = required - set(stations.columns)
    if missing:
        raise ValueError(f"Station-road mapping is missing columns: {sorted(missing)}")
    return stations


def build_graph_with_start_access(graph, latitude: float, longitude: float):
    """Return a per-request graph whose start point is inserted on the nearest road edge."""
    edge_snap = nearest_road_edge_snap(graph, latitude, longitude)
    start_node = "__start_access__"
    start_attrs = {
        "x": edge_snap["longitude"],
        "y": edge_snap["latitude"],
        "node_type": "start_access",
    }
    outgoing_edges = _start_access_outgoing_edges(graph, edge_snap)
    return _StartAccessGraph(graph, start_node, start_attrs, outgoing_edges), start_node, edge_snap


def nearest_road_edge_snap(graph, latitude: float, longitude: float) -> dict:
    """Find the nearest traversable road edge and project the point onto that edge."""
    point = Point(longitude, latitude)
    index = _road_edge_index(graph)
    nearest_index = index["tree"].nearest(point)
    if nearest_index is None:
        raise ValueError("Road graph has no traversable road edges.")
    edge = index["edges"][int(nearest_index)]
    line = index["lines"][int(nearest_index)]
    projected = line.interpolate(line.project(point))
    return {
        "u": edge[0],
        "v": edge[1],
        "key": edge[2],
        "point": projected,
        "latitude": float(projected.y),
        "longitude": float(projected.x),
        "distance_m": float(_haversine_m(latitude, longitude, float(projected.y), float(projected.x))),
    }


def _restore_graphml_edge_types(graph) -> None:
    for _, attrs in graph.nodes(data=True):
        for key in ["x", "y"]:
            if key in attrs:
                attrs[key] = _safe_float(attrs[key], 0.0)
    for _, _, _, attrs in graph.edges(keys=True, data=True):
        for key in ["length", "travel_time"]:
            if key in attrs:
                attrs[key] = _safe_float(attrs[key], 0.0)
        geometry = attrs.get("geometry")
        if isinstance(geometry, str):
            attrs["geometry"] = wkt.loads(geometry)


def _road_edge_index(graph) -> dict:
    cached = graph.graph.get("_road_edge_index")
    if cached is not None:
        return cached

    lines = []
    edges = []
    for u, v, key, attrs in graph.edges(keys=True, data=True):
        line = _edge_line(graph, u, v, attrs)
        if line.is_empty or len(line.coords) < 2:
            continue
        lines.append(line)
        edges.append((u, v, key))
    if not lines:
        raise ValueError("Road graph has no traversable road edges.")
    cached = {"tree": STRtree(lines), "lines": lines, "edges": edges}
    graph.graph["_road_edge_index"] = cached
    return cached


def _start_access_outgoing_edges(graph, edge_snap: dict) -> dict:
    point = edge_snap["point"]
    outgoing = {}
    _add_start_access_edge(outgoing, graph, edge_snap["u"], edge_snap["v"], edge_snap["key"], point)
    for reverse_key in graph.get_edge_data(edge_snap["v"], edge_snap["u"], default={}):
        _add_start_access_edge(outgoing, graph, edge_snap["v"], edge_snap["u"], reverse_key, point)
    return outgoing


def _add_start_access_edge(outgoing: dict, graph, u, v, key, point: Point) -> None:
    if not graph.has_edge(u, v, key):
        return
    edge_attrs = dict(graph.get_edge_data(u, v, key))
    line = _edge_line(graph, u, v, edge_attrs)
    fraction = _line_fraction(line, line.project(point))
    original_length_m = _safe_float(edge_attrs.get("length"), _haversine_m(*_node_lat_lon(graph, u), *_node_lat_lon(graph, v)))
    original_time_s = _safe_float(edge_attrs.get("travel_time"), original_length_m / 1000 / 30.0 * 3600)
    attrs = _segment_edge_attrs(edge_attrs, line, original_length_m, original_time_s, fraction, 1.0)
    attrs["start_split"] = True
    current = outgoing.get(v)
    if current is None or _safe_float(attrs.get("travel_time"), float("inf")) < _safe_float(current.get("travel_time"), float("inf")):
        outgoing[v] = attrs


class _StartAccessGraph:
    def __init__(self, base_graph, start_node: str, start_attrs: dict, outgoing_edges: dict):
        self._base_graph = base_graph
        self._start_node = start_node
        self._outgoing_edges = outgoing_edges
        self.nodes = _StartAccessNodes(base_graph.nodes, start_node, start_attrs)

    def successors(self, node):
        if node == self._start_node:
            return iter(self._outgoing_edges)
        return self._base_graph.successors(node)

    def get_edge_data(self, u, v, default=None):
        if u == self._start_node and v in self._outgoing_edges:
            return {0: self._outgoing_edges[v]}
        return self._base_graph.get_edge_data(u, v, default=default)


class _StartAccessNodes:
    def __init__(self, base_nodes, start_node: str, start_attrs: dict):
        self._base_nodes = base_nodes
        self._start_node = start_node
        self._start_attrs = start_attrs

    def __getitem__(self, node):
        if node == self._start_node:
            return self._start_attrs
        return self._base_nodes[node]


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
    if segment_fraction == 0:
        point = line.interpolate(low, normalized=True)
        segment = LineString([(float(point.x), float(point.y)), (float(point.x), float(point.y))])
    else:
        segment = substring(line, low, high, normalized=True)
    if not isinstance(segment, LineString):
        coords = list(getattr(segment, "coords", []))
        if len(coords) == 1:
            coords = [coords[0], coords[0]]
        segment = LineString(coords)
    if from_fraction > to_fraction and len(segment.coords) > 1:
        segment = LineString(list(segment.coords)[::-1])

    attrs = dict(edge_attrs)
    attrs["length"] = original_length_m * segment_fraction
    attrs["travel_time"] = original_time_s * segment_fraction
    attrs["geometry"] = segment
    return attrs


def _edge_line(graph, u, v, edge_attrs: dict) -> LineString:
    geometry = edge_attrs.get("geometry")
    if isinstance(geometry, LineString):
        return geometry
    if geometry is not None and hasattr(geometry, "geoms"):
        lines = [part for part in geometry.geoms if isinstance(part, LineString) and len(part.coords) >= 2]
        if lines:
            return max(lines, key=lambda part: part.length)
    return LineString(
        [
            (float(graph.nodes[u]["x"]), float(graph.nodes[u]["y"])),
            (float(graph.nodes[v]["x"]), float(graph.nodes[v]["y"])),
        ]
    )


def _line_fraction(line: LineString, projected_distance: float) -> float:
    if line.length == 0:
        return 0.0
    return max(0.0, min(1.0, projected_distance / line.length))


def _node_lat_lon(graph, node) -> tuple[float, float]:
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
