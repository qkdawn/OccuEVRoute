"""Build a lightweight WGS84 GeoJSON boundary for Shenzhen."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BOUNDARY_FILE = (
    PROJECT_ROOT
    / "ML"
    / "Data"
    / "UrbanEVSupplemental"
    / "UrbanEVSupplemental"
    / "shenzhen_districts"
    / "Shenzhen.shp"
)
DEFAULT_OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "shenzhen_boundary.geojson"


def build_boundary_geojson(boundary_file: Path) -> dict:
    districts = gpd.read_file(boundary_file)
    districts = districts.set_crs("EPSG:3857", allow_override=True).to_crs("EPSG:4326")
    boundary = districts.geometry.union_all()
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "Shenzhen"},
                "geometry": mapping(boundary),
            }
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Shenzhen boundary GeoJSON.")
    parser.add_argument("--boundary", type=Path, default=DEFAULT_BOUNDARY_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_FILE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    geojson = build_boundary_geojson(args.boundary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as file:
        json.dump(geojson, file, ensure_ascii=False)
    print(f"Saved Shenzhen boundary: {args.output}")


if __name__ == "__main__":
    main()
