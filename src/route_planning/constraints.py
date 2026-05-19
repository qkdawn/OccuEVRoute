"""Pre-search and post-search feasibility checks."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class UserConstraints:
    max_candidates: int = 20
    max_search_radius_km: float = 10.0
    max_drive_time_min: float = 30.0
    current_soc: float = 0.5
    battery_capacity_kwh: float = 60.0
    min_arrival_soc: float = 0.1
    min_charge_count: int = 1
    consumption_kwh_per_km: float = 0.188
    max_road_snap_distance_m: float = 150.0
    max_start_snap_distance_m: float = 300.0


def pre_csp_check(station: pd.Series, constraints: UserConstraints) -> tuple[bool, str]:
    """Check station-only constraints before graph search."""
    required = [
        "station_id",
        "latitude",
        "longitude",
        "charge_count",
        "road_edge_u",
        "road_edge_v",
        "road_edge_key",
        "road_projection_latitude",
        "road_projection_longitude",
        "road_snap_distance_m",
        "access_node",
    ]
    for field in required:
        if field not in station or pd.isna(station[field]):
            return False, f"missing_{field}"
    if float(station["straight_line_distance_km"]) > constraints.max_search_radius_km:
        return False, "outside_search_radius"
    if int(station["charge_count"]) < constraints.min_charge_count:
        return False, "too_few_chargers"
    if float(station["road_snap_distance_m"]) > constraints.max_road_snap_distance_m:
        return False, "road_snap_distance_too_far"
    return True, ""


def post_csp_check(
    path_found: bool,
    distance_km: float | None,
    drive_time_min: float | None,
    constraints: UserConstraints,
) -> tuple[bool, str, float | None]:
    """Check route-dependent constraints after graph search."""
    if not path_found:
        return False, "path_not_found", None
    if distance_km is None or drive_time_min is None:
        return False, "missing_route_metrics", None
    if drive_time_min > constraints.max_drive_time_min:
        return False, "drive_time_exceeds_limit", None

    available_energy_kwh = constraints.battery_capacity_kwh * constraints.current_soc
    energy_needed_kwh = distance_km * constraints.consumption_kwh_per_km
    if energy_needed_kwh > available_energy_kwh:
        return False, "insufficient_energy", None

    arrival_energy_kwh = available_energy_kwh - energy_needed_kwh
    arrival_soc = arrival_energy_kwh / constraints.battery_capacity_kwh
    if arrival_soc < constraints.min_arrival_soc:
        return False, "arrival_soc_below_safety_threshold", arrival_soc

    return True, "", arrival_soc
