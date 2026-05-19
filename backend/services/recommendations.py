"""Recommendation service wrapping the route-planning package."""

from __future__ import annotations

import math
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROUTE_PLANNING_DIR = PROJECT_ROOT / "src" / "route_planning"
if str(ROUTE_PLANNING_DIR) not in sys.path:
    sys.path.insert(0, str(ROUTE_PLANNING_DIR))

from constraints import UserConstraints
from graph_loader import load_road_graph, load_station_access, nearest_road_edge_snap
from landmark_heuristic import LandmarkHeuristic
from recommender import recommend_charging_stations

from backend.schemas import RecommendationItem, RecommendationRequest, RecommendationResponse
from backend.services.geo_data import contains_shenzhen, load_station_poi_features


@lru_cache(maxsize=1)
def get_graph():
    return load_road_graph()


@lru_cache(maxsize=1)
def get_stations() -> pd.DataFrame:
    return load_station_access()


@lru_cache(maxsize=1)
def get_station_poi_features() -> pd.DataFrame:
    return load_station_poi_features()


@lru_cache(maxsize=1)
def get_landmark_heuristic() -> LandmarkHeuristic | None:
    return LandmarkHeuristic.load()


def warmup_data() -> None:
    graph = get_graph()
    nearest_road_edge_snap(graph, 22.65, 114.05)
    get_stations()
    get_station_poi_features()
    get_landmark_heuristic()


def recommend(request: RecommendationRequest) -> RecommendationResponse:
    if not contains_shenzhen(request.lat, request.lng):
        raise ValueError("Please choose a location within Shenzhen.")
    constraints = UserConstraints(
        max_candidates=request.max_candidates,
        max_search_radius_km=request.max_search_radius_km,
        max_drive_time_min=request.max_drive_time_min,
        current_soc=request.current_soc,
        battery_capacity_kwh=request.battery_capacity_kwh,
        consumption_kwh_per_km=request.consumption_kwh_per_km,
        min_arrival_soc=request.min_arrival_soc,
        min_charge_count=request.min_charge_count,
        max_road_snap_distance_m=request.max_road_snap_distance_m,
        max_start_snap_distance_m=request.max_start_snap_distance_m,
    )
    results = recommend_charging_stations(
        request.lat,
        request.lng,
        algorithm=request.algorithm,
        constraints=constraints,
        top_k=request.top_k,
        graph=get_graph(),
        stations=get_stations(),
        landmark_heuristic=get_landmark_heuristic(),
    )
    results = _merge_poi_features(results)
    return RecommendationResponse(
        recommendations=[_row_to_item(row) for _, row in results.iterrows()],
    )


def _merge_poi_features(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty or "station_id" not in results.columns:
        return results
    poi_features = get_station_poi_features()
    if poi_features.empty:
        return results
    return results.merge(poi_features, on="station_id", how="left")


def _row_to_item(row: pd.Series) -> RecommendationItem:
    station_id = _optional_int(row.get("station_id"))
    return RecommendationItem(
        station_id=station_id,
        station_display_name=f"Charging Station {station_id}" if station_id is not None else None,
        station_latitude=_optional_float(row.get("station_latitude")),
        station_longitude=_optional_float(row.get("station_longitude")),
        station_road_latitude=_optional_float(row.get("station_road_latitude")),
        station_road_longitude=_optional_float(row.get("station_road_longitude")),
        start_node_latitude=_optional_float(row.get("start_node_latitude")),
        start_node_longitude=_optional_float(row.get("start_node_longitude")),
        start_snap_distance_m=_optional_float(row.get("start_snap_distance_m")),
        route_coordinates=[
            (_required_float(point[0]), _required_float(point[1]))
            for point in _safe_list(row.get("route_coordinates"))
        ],
        expanded_trace_coordinates=[
            (_required_float(point[0]), _required_float(point[1]))
            for point in _safe_list(row.get("expanded_trace_coordinates"))
        ],
        distance_km=_optional_float(row.get("distance_km")),
        drive_time_min=_optional_float(row.get("drive_time_min")),
        road_snap_distance_m=_optional_float(row.get("road_snap_distance_m")),
        expanded_nodes=_optional_int(row.get("expanded_nodes")) or 0,
        runtime_seconds=_optional_float(row.get("runtime_seconds")) or 0.0,
        charge_count=_optional_int(row.get("charge_count")),
        poi_total_count=_optional_int(row.get("poi_total_count")),
        poi_lifestyle_services_count=_optional_int(row.get("poi_lifestyle_services_count")),
        poi_business_residential_count=_optional_int(row.get("poi_business_residential_count")),
        poi_food_beverage_count=_optional_int(row.get("poi_food_beverage_count")),
        arrival_soc=_optional_float(row.get("arrival_soc")),
        passed_constraints=bool(row.get("passed_constraints")),
        reject_reason=str(row.get("reject_reason") or ""),
    )


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _required_float(value: Any) -> float:
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)
