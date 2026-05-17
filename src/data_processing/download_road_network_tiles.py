"""Download Shenzhen road network in tiles and merge it into one GraphML.

This is more reliable than one large Overpass request. Tiles are built from
the UrbanEV station coordinate bounding box, and every tile is downloaded from
OpenStreetMap as a real drive network.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import networkx as nx
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
DEFAULT_OUTPUT_FILE = PROJECT_ROOT / "data" / "external" / "shenzhen_drive.graphml"
DEFAULT_TILE_DIR = PROJECT_ROOT / "data" / "external" / "road_tiles"
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "external" / "osmnx_cache"
DEFAULT_SPEED_KPH = 40


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
        return ox.load_graphml(tile_path)

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
                simplify=True,
            )
            graph = add_travel_times(graph)
            ox.save_graphml(graph, tile_path)
            print(f"Saved tile r{row} c{col}: nodes={len(graph.nodes):,}, edges={len(graph.edges):,}")
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
    merged.graph["name"] = "shenzhen_drive_tiled"
    return merged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Shenzhen road network by tiles.")
    parser.add_argument("--station-file", type=Path, default=DEFAULT_STATION_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_FILE)
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
    print(
        f"Station bounds with padding: west={west}, south={south}, east={east}, north={north}"
    )
    print(f"Downloading {len(tiles)} tiles ({args.rows} rows x {args.cols} cols)")

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
    ox.save_graphml(merged, args.output)
    print(f"Saved merged road network: {args.output}")
    print(f"Nodes: {len(merged.nodes):,}")
    print(f"Edges: {len(merged.edges):,}")


if __name__ == "__main__":
    main()
