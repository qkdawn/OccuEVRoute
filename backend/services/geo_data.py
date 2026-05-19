"""Geographic boundary and POI feature helpers."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any

import pandas as pd
from shapely.geometry import Point, mapping, shape


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
DEFAULT_BOUNDARY_GEOJSON_FILE = PROJECT_ROOT / "data" / "processed" / "shenzhen_boundary.geojson"
DEFAULT_POI_FEATURE_FILE = PROJECT_ROOT / "data" / "processed" / "station_poi_features.csv"


@lru_cache(maxsize=1)
def get_shenzhen_boundary():
    """Load Shenzhen TAZ polygons as one WGS84 service-area geometry."""
    if DEFAULT_BOUNDARY_GEOJSON_FILE.exists():
        with DEFAULT_BOUNDARY_GEOJSON_FILE.open("r", encoding="utf-8") as file:
            geojson = json.load(file)
        return shape(geojson["features"][0]["geometry"])
    if not DEFAULT_BOUNDARY_FILE.exists():
        raise FileNotFoundError(
            f"Shenzhen boundary file not found: {DEFAULT_BOUNDARY_GEOJSON_FILE} or {DEFAULT_BOUNDARY_FILE}"
        )
    import geopandas as gpd

    districts = gpd.read_file(DEFAULT_BOUNDARY_FILE)
    districts = districts.set_crs("EPSG:3857", allow_override=True).to_crs("EPSG:4326")
    return districts.geometry.union_all()


def contains_shenzhen(latitude: float, longitude: float) -> bool:
    """Return whether a WGS84 point is inside the Shenzhen service area."""
    point = Point(float(longitude), float(latitude))
    return bool(get_shenzhen_boundary().covers(point))


def shenzhen_boundary_geojson() -> dict[str, Any]:
    """Return a FeatureCollection containing the merged Shenzhen boundary."""
    if DEFAULT_BOUNDARY_GEOJSON_FILE.exists():
        with DEFAULT_BOUNDARY_GEOJSON_FILE.open("r", encoding="utf-8") as file:
            return json.load(file)
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "Shenzhen"},
                "geometry": mapping(get_shenzhen_boundary()),
            }
        ],
    }


@lru_cache(maxsize=1)
def load_station_poi_features() -> pd.DataFrame:
    """Load optional per-station POI aggregation features."""
    columns = [
        "station_id",
        "poi_total_count",
        "poi_lifestyle_services_count",
        "poi_business_residential_count",
        "poi_food_beverage_count",
    ]
    if not DEFAULT_POI_FEATURE_FILE.exists():
        return pd.DataFrame(columns=columns)
    features = pd.read_csv(DEFAULT_POI_FEATURE_FILE)
    missing = set(columns) - set(features.columns)
    if missing:
        raise ValueError(f"POI feature file is missing columns: {sorted(missing)}")
    return features[columns]
