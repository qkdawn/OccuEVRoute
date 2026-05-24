"""Recommendation service wrapping the route-planning package."""

from __future__ import annotations

import math
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, get_args

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROUTE_PLANNING_DIR = PROJECT_ROOT / "src" / "route_planning"
WAITING_PREDICTION_DIR = PROJECT_ROOT / "src" / "waiting_prediction"
if str(ROUTE_PLANNING_DIR) not in sys.path:
    sys.path.insert(0, str(ROUTE_PLANNING_DIR))
if str(WAITING_PREDICTION_DIR) not in sys.path:
    sys.path.insert(0, str(WAITING_PREDICTION_DIR))

from ch_index import CHIndex
from constraints import UserConstraints
from graph_loader import load_road_graph, load_station_access, nearest_road_edge_snap
from landmark_heuristic import LandmarkHeuristic
from occupancy_predictor import get_historical_occupancy_predictor, historical_now
from recommender import recommend_charging_stations
from search_algorithms import SearchContext

from backend.schemas import RecommendationItem, RecommendationRequest, RecommendationResponse, SearchTrace
from backend.services.geo_data import contains_shenzhen, load_station_poi_features

RANKING_METRICS = get_args(RecommendationRequest.model_fields["ranking_metric"].annotation)
BALANCED_OCCUPANCY_RISK_WEIGHT = 1.0


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
def get_landmark_heuristic() -> LandmarkHeuristic:
    landmark_heuristic = LandmarkHeuristic.load()
    if landmark_heuristic is None:
        raise ValueError("ALT landmark table is required. Run src/data_processing/build_landmark_distances.py.")
    return landmark_heuristic


@lru_cache(maxsize=1)
def get_ch_index() -> CHIndex:
    try:
        return CHIndex.load()
    except FileNotFoundError as exc:
        raise ValueError(str(exc)) from exc


@lru_cache(maxsize=1)
def get_occupancy_predictor():
    return get_historical_occupancy_predictor()


def warmup_data() -> None:
    graph = get_graph()
    nearest_road_edge_snap(graph, 22.65, 114.05)
    get_stations()
    get_station_poi_features()
    get_landmark_heuristic()
    get_ch_index()
    _warmup_default_recommendation(graph)


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
        top_k=request.max_candidates,
        graph=get_graph(),
        stations=get_stations(),
        search_context=SearchContext(
            landmark_heuristic=get_landmark_heuristic(),
            ch_index=get_ch_index() if request.algorithm == "ch_bidirectional_dijkstra" else None,
        ),
    )
    results = _merge_poi_features(results)
    results = _merge_occupancy_predictions(results, request)
    ranking_orders = _build_ranking_orders(results, request.top_k)
    ordered_results = _sort_recommendations(results, request.ranking_metric).head(request.top_k).reset_index(drop=True)
    return RecommendationResponse(
        recommendations=[_row_to_item(row) for _, row in ordered_results.iterrows()],
        ranking_orders=ranking_orders,
    )


def _warmup_default_recommendation(graph) -> None:
    constraints = UserConstraints()
    results = recommend_charging_stations(
        22.65,
        114.05,
        algorithm="astar",
        constraints=constraints,
        top_k=constraints.max_candidates,
        graph=graph,
        stations=get_stations(),
        search_context=SearchContext(landmark_heuristic=get_landmark_heuristic()),
    )
    if results.empty or "station_id" not in results.columns:
        get_occupancy_predictor().warmup([], [])
        return
    prediction_input = results[results["station_id"].notna()]
    get_occupancy_predictor().warmup(
        [int(station_id) for station_id in prediction_input["station_id"]],
        [_optional_float(value) for value in prediction_input["drive_time_min"]],
    )


def _merge_poi_features(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty or "station_id" not in results.columns:
        return results
    poi_features = get_station_poi_features()
    if poi_features.empty:
        return results
    return results.merge(poi_features, on="station_id", how="left")


def _merge_occupancy_predictions(results: pd.DataFrame, request: RecommendationRequest) -> pd.DataFrame:
    if results.empty or "station_id" not in results.columns:
        return results
    out = results.copy()
    predictor = get_occupancy_predictor()
    simulated_now = _parse_simulated_now(request.simulated_now)
    prediction_input = out[out["station_id"].notna()].copy()
    station_ids = [int(station_id) for station_id in prediction_input["station_id"]]
    drive_times = [_optional_float(value) for value in prediction_input["drive_time_min"]]
    predictions = predictor.predict(station_ids, drive_times, simulated_now=simulated_now)

    out["predicted_occupancy_rate"] = out["station_id"].map(
        lambda value: predictions[int(value)].predicted_occupancy_rate if pd.notna(value) else None
    )
    out["prediction_horizon_min"] = out["station_id"].map(
        lambda value: predictions[int(value)].prediction_horizon_min if pd.notna(value) else None
    )
    out["prediction_time"] = out["station_id"].map(
        lambda value: predictions[int(value)].prediction_time if pd.notna(value) else None
    )
    out["prediction_source"] = out["station_id"].map(
        lambda value: predictions[int(value)].prediction_source if pd.notna(value) else ""
    )
    out["ml_rank_score"] = out.apply(
        lambda row: _balanced_rank_score(row, request.max_drive_time_min),
        axis=1,
    )
    feasible = out[out["passed_constraints"]].copy()
    if feasible.empty:
        return out
    return feasible.reset_index(drop=True)


def _build_ranking_orders(results: pd.DataFrame, top_k: int) -> dict[str, list[int]]:
    if results.empty or "station_id" not in results.columns:
        return {metric: [] for metric in RANKING_METRICS}
    return {
        metric: [
            int(station_id)
            for station_id in _sort_recommendations(results, metric)["station_id"].head(top_k)
            if pd.notna(station_id)
        ]
        for metric in RANKING_METRICS
    }


def _sort_recommendations(results: pd.DataFrame, ranking_metric: str) -> pd.DataFrame:
    sort_columns = {
        "balanced": ["ml_rank_score", "drive_time_min", "distance_km"],
        "drive_time": ["drive_time_min", "distance_km", "predicted_occupancy_rate"],
        "distance": ["distance_km", "drive_time_min", "predicted_occupancy_rate"],
        "occupancy": ["predicted_occupancy_rate", "drive_time_min", "distance_km"],
        "arrival_soc": ["arrival_soc", "drive_time_min", "distance_km"],
    }[ranking_metric]
    ascending = [False if column == "arrival_soc" else True for column in sort_columns]
    return results.sort_values(sort_columns, ascending=ascending, na_position="last")


def _parse_simulated_now(value: str | None):
    if not value:
        return historical_now()
    try:
        return pd.Timestamp(value)
    except ValueError as exc:
        raise ValueError("simulated_now must be a valid datetime, for example 2023-02-01T08:00:00.") from exc


def _balanced_rank_score(row: pd.Series, max_drive_time_min: float) -> float | None:
    drive_time = _optional_float(row.get("drive_time_min"))
    occupancy = _optional_float(row.get("predicted_occupancy_rate"))
    if drive_time is None or occupancy is None:
        return None
    return drive_time / max_drive_time_min + BALANCED_OCCUPANCY_RISK_WEIGHT * occupancy


def _row_to_item(row: pd.Series) -> RecommendationItem:
    station_id = _optional_int(row.get("station_id"))
    return RecommendationItem(
        station_id=station_id,
        station_display_name=f"Charging Station {station_id}" if station_id is not None else None,
        algorithm=row.get("algorithm"),
        station_latitude=_optional_float(row.get("station_latitude")),
        station_longitude=_optional_float(row.get("station_longitude")),
        station_road_latitude=_optional_float(row.get("station_road_latitude")),
        station_road_longitude=_optional_float(row.get("station_road_longitude")),
        start_node_latitude=_optional_float(row.get("start_node_latitude")),
        start_node_longitude=_optional_float(row.get("start_node_longitude")),
        start_snap_distance_m=_optional_float(row.get("start_snap_distance_m")),
        route_coordinates=[
            (_required_float(point[0]), _required_float(point[1]))
            for point in row.get("route_coordinates")
        ],
        search_trace=_row_search_trace(row.get("search_trace")),
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
        predicted_occupancy_rate=_optional_float(row.get("predicted_occupancy_rate")),
        prediction_horizon_min=_optional_float(row.get("prediction_horizon_min")),
        prediction_time=str(row.get("prediction_time")) if row.get("prediction_time") else None,
        prediction_source=str(row.get("prediction_source") or ""),
        ml_rank_score=_optional_float(row.get("ml_rank_score")),
        passed_constraints=bool(row.get("passed_constraints")),
        reject_reason=str(row.get("reject_reason") or ""),
    )


def _row_search_trace(value: Any) -> SearchTrace:
    return SearchTrace.model_validate(value)


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
