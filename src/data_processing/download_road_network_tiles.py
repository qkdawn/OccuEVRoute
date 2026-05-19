"""Download Shenzhen road network in tiles and merge it into one GraphML.

This is more reliable than one large Overpass request. Tiles are built from
the UrbanEV station coordinate bounding box. The downloaded network includes
regular drivable roads plus public service roads such as parking aisles and
campus/internal access roads, while filtering out private/no-access edges.
"""

from __future__ import annotations

import argparse
import ast
import json
import time
from pathlib import Path
from typing import Any

import networkx as nx
import osmnx as ox
import pandas as pd
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
DEFAULT_OUTPUT_FILE = PROJECT_ROOT / "data" / "external" / "shenzhen_drive.graphml"
DEFAULT_BOUNDARY_FILE = PROJECT_ROOT / "data" / "processed" / "shenzhen_boundary.geojson"
DEFAULT_TILE_DIR = PROJECT_ROOT / "data" / "external" / "road_tiles_public_drive"
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "external" / "osmnx_cache"
DEFAULT_SPEED_KPH = 40
DISALLOWED_ACCESS_VALUES = {"private", "no"}
DRIVE_SERVICE_FILTER = (
    '["highway"~"motorway|trunk|primary|secondary|tertiary|unclassified|'
    'residential|living_street|motorway_link|trunk_link|primary_link|'
    'secondary_link|tertiary_link|service"]'
    '["access"!~"private|no"]'
)


def station_bounds(station_file: Path, padding_degrees: float) -> tuple[float, float, float, float]:
    stations = pd.read_csv(station_file)
    required = {"longitude", "latitude"}
    missing = required - set(stations.columns)
    if missing:
        raise ValueError(f"Station file is missing columns: {sorted(missing)}")

    west = float(stations["longitude"].min() - padding_degrees)
    south = float(stations["latitude"].min() - padding_degrees)
    east = float(stations["longitude"].max() + padding_degrees)
    north = float(stations["latitude"].max() + padding_degrees)
    return west, south, east, north


def make_tiles(
    west: float,
    south: float,
    east: float,
    north: float,
    cols: int,
    rows: int,
    overlap_degrees: float,
) -> list[tuple[int, int, float, float, float, float]]:
    lon_step = (east - west) / cols
    lat_step = (north - south) / rows
    tiles = []
    for row in range(rows):
        for col in range(cols):
            tile_west = west + col * lon_step
            tile_east = west + (col + 1) * lon_step
            tile_south = south + row * lat_step
            tile_north = south + (row + 1) * lat_step
            tiles.append(
                (
                    row,
                    col,
                    max(west, tile_west - overlap_degrees),
                    max(south, tile_south - overlap_degrees),
                    min(east, tile_east + overlap_degrees),
                    min(north, tile_north + overlap_degrees),
                )
            )
    return tiles


def configure_osmnx(overpass_url: str, timeout_seconds: int) -> None:
    ox.settings.use_cache = True
    ox.settings.log_console = True
    ox.settings.cache_folder = DEFAULT_CACHE_DIR
    ox.settings.overpass_url = overpass_url
    ox.settings.requests_timeout = timeout_seconds


def add_travel_times(graph):
    graph = ox.add_edge_speeds(graph, fallback=DEFAULT_SPEED_KPH)
    graph = ox.add_edge_travel_times(graph)
    return graph


def remove_private_access_edges(graph: nx.MultiDiGraph) -> int:
    blocked_edges = []
    for u, v, key, attrs in graph.edges(keys=True, data=True):
        if _has_disallowed_access(attrs.get("access")):
            blocked_edges.append((u, v, key))
    graph.remove_edges_from(blocked_edges)
    graph.remove_nodes_from(list(nx.isolates(graph)))
    return len(blocked_edges)


def _has_disallowed_access(value: Any) -> bool:
    return any(str(item).strip().lower() in DISALLOWED_ACCESS_VALUES for item in _as_list(value))


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if isinstance(value, str) and value.startswith("["):
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return [value]
        if isinstance(parsed, (list, tuple, set)):
            return list(parsed)
    return [value]


def download_tile(
    row: int,
    col: int,
    west: float,
    south: float,
    east: float,
    north: float,
    tile_dir: Path,
    retries: int,
):
    tile_path = tile_dir / f"tile_r{row:02d}_c{col:02d}.graphml"
    if tile_path.exists():
        print(f"Using existing tile r{row} c{col}: {tile_path}")
        graph = ox.load_graphml(tile_path)
        removed = remove_private_access_edges(graph)
        if removed:
            print(f"Removed {removed:,} private/no-access edges from cached tile r{row} c{col}")
        return graph

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            print(
                f"Downloading tile r{row} c{col} attempt {attempt}/{retries}: "
                f"west={west}, south={south}, east={east}, north={north}"
            )
            graph = ox.graph_from_bbox(
                (west, south, east, north),
                network_type="drive",
                custom_filter=DRIVE_SERVICE_FILTER,
                simplify=True,
            )
            removed = remove_private_access_edges(graph)
            graph = add_travel_times(graph)
            ox.save_graphml(graph, tile_path)
            print(
                f"Saved tile r{row} c{col}: nodes={len(graph.nodes):,}, "
                f"edges={len(graph.edges):,}, filtered_edges={removed:,}"
            )
            return graph
        except Exception as exc:
            last_error = exc
            print(f"Tile r{row} c{col} failed: {type(exc).__name__}: {exc}")
            if attempt < retries:
                time.sleep(10 * attempt)
    raise RuntimeError(f"Failed tile r{row} c{col}") from last_error


def merge_graphs(graphs: list) -> nx.MultiDiGraph:
    if not graphs:
        raise ValueError("No graphs to merge.")

    merged = nx.compose_all(graphs)
    merged.graph.update(graphs[0].graph)
    merged.graph["name"] = "shenzhen_public_drive_tiled"
    removed = remove_private_access_edges(merged)
    if removed:
        print(f"Removed {removed:,} private/no-access edges after merging tiles")
    return merged


def clip_to_boundary_main_component(graph: nx.MultiDiGraph, boundary_file: Path) -> tuple[nx.MultiDiGraph, int, int]:
    if not boundary_file.exists():
        raise FileNotFoundError(f"Boundary GeoJSON not found: {boundary_file}")

    with boundary_file.open("r", encoding="utf-8") as file:
        geojson = json.load(file)
    boundary = shape(geojson["features"][0]["geometry"])

    outside_nodes = [
        node
        for node, attrs in graph.nodes(data=True)
        if not boundary.covers(Point(float(attrs["x"]), float(attrs["y"])))
    ]
    clipped = graph.copy()
    clipped.remove_nodes_from(outside_nodes)
    clipped.remove_nodes_from(list(nx.isolates(clipped)))
    if clipped.number_of_nodes() == 0:
        raise ValueError("No road graph nodes remain after Shenzhen boundary clipping.")

    components = sorted(nx.weakly_connected_components(clipped), key=len, reverse=True)
    main_component = set(components[0])
    off_component_nodes = [node for node in clipped.nodes if node not in main_component]
    clipped.remove_nodes_from(off_component_nodes)
    clipped.graph.update(graph.graph)
    clipped.graph["name"] = "shenzhen_public_drive_main_component"
    return clipped, len(outside_nodes), len(off_component_nodes)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Shenzhen road network by tiles.")
    parser.add_argument("--station-file", type=Path, default=DEFAULT_STATION_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_FILE)
    parser.add_argument("--boundary", type=Path, default=DEFAULT_BOUNDARY_FILE)
    parser.add_argument("--tile-dir", type=Path, default=DEFAULT_TILE_DIR)
    parser.add_argument("--padding-degrees", type=float, default=0.02)
    parser.add_argument("--overlap-degrees", type=float, default=0.003)
    parser.add_argument("--cols", type=int, default=4)
    parser.add_argument("--rows", type=int, default=4)
    parser.add_argument("--overpass-url", default="https://overpass-api.de/api")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--retries", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.station_file.exists():
        raise FileNotFoundError(f"Station file not found: {args.station_file}")
    if args.cols <= 0 or args.rows <= 0:
        raise ValueError("--cols and --rows must be positive.")

    configure_osmnx(args.overpass_url, args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.tile_dir.mkdir(parents=True, exist_ok=True)

    west, south, east, north = station_bounds(args.station_file, args.padding_degrees)
    tiles = make_tiles(west, south, east, north, args.cols, args.rows, args.overlap_degrees)
    print(f"Station bounds with padding: west={west}, south={south}, east={east}, north={north}")
    print(f"Downloading {len(tiles)} tiles ({args.rows} rows x {args.cols} cols)")
    print(f"Using custom OSM filter: {DRIVE_SERVICE_FILTER}")

    graphs = []
    for row, col, tile_west, tile_south, tile_east, tile_north in tiles:
        graph = download_tile(
            row,
            col,
            tile_west,
            tile_south,
            tile_east,
            tile_north,
            args.tile_dir,
            args.retries,
        )
        graphs.append(graph)

    merged = merge_graphs(graphs)
    merged, outside_nodes, off_component_nodes = clip_to_boundary_main_component(merged, args.boundary)
    print(f"Removed {outside_nodes:,} nodes outside Shenzhen boundary")
    print(f"Removed {off_component_nodes:,} nodes outside the main Shenzhen road component")
    ox.save_graphml(merged, args.output)
    print(f"Saved merged road network: {args.output}")
    print(f"Nodes: {len(merged.nodes):,}")
    print(f"Edges: {len(merged.edges):,}")


if __name__ == "__main__":
    main()
