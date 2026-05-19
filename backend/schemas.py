"""API request and response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Algorithm = Literal["astar", "ucs", "bfs"]


class RecommendationRequest(BaseModel):
    lat: float
    lng: float
    algorithm: Algorithm = "astar"
    max_candidates: int = Field(default=20, ge=1, le=100)
    max_search_radius_km: float = Field(default=10.0, gt=0)
    max_drive_time_min: float = Field(default=30.0, gt=0)
    current_soc: float = Field(default=0.5, ge=0, le=1)
    battery_capacity_kwh: float = Field(default=60.0, gt=0)
    consumption_kwh_per_km: float = Field(default=0.188, gt=0)
    min_arrival_soc: float = Field(default=0.1, ge=0, le=1)
    min_charge_count: int = Field(default=1, ge=1)
    max_road_snap_distance_m: float = Field(default=150.0, gt=0)
    max_start_snap_distance_m: float = Field(default=300.0, gt=0)
    top_k: int = Field(default=20, ge=1, le=100)


class RecommendationItem(BaseModel):
    station_id: int | None
    station_display_name: str | None
    station_latitude: float | None
    station_longitude: float | None
    station_road_latitude: float | None
    station_road_longitude: float | None
    start_node_latitude: float | None
    start_node_longitude: float | None
    start_snap_distance_m: float | None
    route_coordinates: list[tuple[float, float]]
    distance_km: float | None
    drive_time_min: float | None
    road_snap_distance_m: float | None
    expanded_nodes: int
    runtime_seconds: float
    charge_count: int | None
    poi_total_count: int | None
    poi_lifestyle_services_count: int | None
    poi_business_residential_count: int | None
    poi_food_beverage_count: int | None
    arrival_soc: float | None
    passed_constraints: bool
    reject_reason: str


class RecommendationResponse(BaseModel):
    recommendations: list[RecommendationItem]


class HealthResponse(BaseModel):
    status: str
