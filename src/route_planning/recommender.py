"""Recommend charging stations from a user location."""

from __future__ import annotations

import argparse
from dataclasses import asdict

import pandas as pd

from candidate_selector import select_nearby_stations
from constraints import UserConstraints, post_csp_check, pre_csp_check
from graph_loader import load_road_graph, load_station_nodes, nearest_road_node
from search_algorithms import run_search


def recommend_charging_stations(
    user_latitude: float,
    user_longitude: float,
    algorithm: str = "astar",
    constraints: UserConstraints | None = None,
    top_k: int = 3,
) -> pd.DataFrame:
    """Recommend top charging stations using search + CSP checks."""
    constraints = constraints or UserConstraints()
    graph = load_road_graph()
    stations = load_station_nodes()
    start_node = nearest_road_node(graph, user_latitude, user_longitude)

    candidates = select_nearby_stations(
        stations,
        user_latitude,
        user_longitude,
        max_search_radius_km=constraints.max_search_radius_km,
        max_candidates=constraints.max_candidates,
    )

    results = []
    for _, station in candidates.iterrows():
        pre_ok, pre_reason = pre_csp_check(station, constraints)
        if not pre_ok:
            results.append(_rejected_result(station, algorithm, pre_reason))
            continue

        search = run_search(graph, start_node, station["road_node"], algorithm)
        post_ok, post_reason, arrival_soc = post_csp_check(
            search.path_found,
            search.distance_km,
            search.drive_time_min,
            constraints,
        )
        results.append(
            {
                "station_id": int(station["station_id"]),
                "road_node": str(station["road_node"]),
                "algorithm": search.algorithm,
                "path": search.path,
                "distance_km": search.distance_km,
                "drive_time_min": search.drive_time_min,
                "expanded_nodes": search.expanded_nodes,
                "runtime_seconds": search.runtime_seconds,
                "charge_count": int(station["charge_count"]),
                "arrival_soc": arrival_soc,
                "straight_line_distance_km": float(station["straight_line_distance_km"]),
                "passed_constraints": post_ok,
                "reject_reason": post_reason,
            }
        )

    result_df = pd.DataFrame(results)
    if result_df.empty:
        return result_df
    feasible = result_df[result_df["passed_constraints"]].copy()
    if feasible.empty:
        return result_df.sort_values(["straight_line_distance_km"]).head(top_k).reset_index(drop=True)
    return feasible.sort_values(["drive_time_min", "distance_km"]).head(top_k).reset_index(drop=True)


def _rejected_result(station: pd.Series, algorithm: str, reason: str) -> dict:
    return {
        "station_id": int(station["station_id"]) if pd.notna(station.get("station_id")) else None,
        "road_node": str(station["road_node"]) if pd.notna(station.get("road_node")) else None,
        "algorithm": algorithm,
        "path": [],
        "distance_km": None,
        "drive_time_min": None,
        "expanded_nodes": 0,
        "runtime_seconds": 0.0,
        "charge_count": int(station["charge_count"]) if pd.notna(station.get("charge_count")) else None,
        "arrival_soc": None,
        "straight_line_distance_km": float(station["straight_line_distance_km"])
        if pd.notna(station.get("straight_line_distance_km"))
        else None,
        "passed_constraints": False,
        "reject_reason": reason,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recommend charging stations from a location.")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--algorithm", choices=["bfs", "ucs", "astar"], default="astar")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--max-candidates", type=int, default=20)
    parser.add_argument("--max-search-radius-km", type=float, default=10.0)
    parser.add_argument("--max-drive-time-min", type=float, default=30.0)
    parser.add_argument("--current-soc", type=float, default=0.5)
    parser.add_argument("--battery-capacity-kwh", type=float, default=60.0)
    parser.add_argument("--min-arrival-soc", type=float, default=0.1)
    parser.add_argument("--min-charge-count", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    user_constraints = UserConstraints(
        max_candidates=args.max_candidates,
        max_search_radius_km=args.max_search_radius_km,
        max_drive_time_min=args.max_drive_time_min,
        current_soc=args.current_soc,
        battery_capacity_kwh=args.battery_capacity_kwh,
        min_arrival_soc=args.min_arrival_soc,
        min_charge_count=args.min_charge_count,
    )
    result = recommend_charging_stations(
        args.lat,
        args.lon,
        algorithm=args.algorithm,
        constraints=user_constraints,
        top_k=args.top_k,
    )
    print("constraints:", asdict(user_constraints))
    if result.empty:
        print("No candidates found.")
    else:
        display_columns = [
            "station_id",
            "algorithm",
            "distance_km",
            "drive_time_min",
            "expanded_nodes",
            "runtime_seconds",
            "charge_count",
            "arrival_soc",
            "passed_constraints",
            "reject_reason",
        ]
        print(result[display_columns].to_string(index=False))


if __name__ == "__main__":
    main()
