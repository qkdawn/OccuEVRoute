"""Recommend charging stations from a user location."""

from __future__ import annotations

import argparse
from dataclasses import asdict

import pandas as pd

from candidate_selector import select_nearby_stations
from constraints import UserConstraints, post_csp_check, pre_csp_check
from graph_loader import build_graph_with_start_access, load_road_graph, load_station_access
from landmark_heuristic import LandmarkHeuristic
from search_algorithms import run_search


def recommend_charging_stations(
    user_latitude: float,
    user_longitude: float,
    algorithm: str = "astar",
    constraints: UserConstraints | None = None,
    top_k: int = 3,
    graph=None,
    stations: pd.DataFrame | None = None,
    landmark_heuristic: LandmarkHeuristic | None = None,
) -> pd.DataFrame:
    """Recommend top charging stations using search + CSP checks."""
    constraints = constraints or UserConstraints()
    graph = graph if graph is not None else load_road_graph()
    stations = stations if stations is not None else load_station_access()
    search_graph, start_node, start_snap = build_graph_with_start_access(graph, user_latitude, user_longitude)
    start_node_latitude = float(start_snap["latitude"])
    start_node_longitude = float(start_snap["longitude"])
    start_snap_distance_m = float(start_snap["distance_m"])
    if start_snap_distance_m > constraints.max_start_snap_distance_m:
        raise ValueError(
            f"The selected location is about {start_snap_distance_m:.1f}m from the nearest drivable road, "
            f"which exceeds the current limit of {constraints.max_start_snap_distance_m:.1f}m. "
            "Choose a point closer to a road or increase the max start snap distance."
        )

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

        access_node = str(station["access_node"])
        search = run_search(search_graph, start_node, access_node, algorithm, landmark_heuristic)
        post_ok, post_reason, arrival_soc = post_csp_check(
            search.path_found,
            search.distance_km,
            search.drive_time_min,
            constraints,
        )
        route_coordinates = _path_to_route_coordinates(search_graph, search.path)
        expanded_trace_coordinates = _nodes_to_coordinates(search_graph, search.expanded_trace)
        results.append(
            {
                "station_id": int(station["station_id"]),
                "access_node": access_node,
                "algorithm": search.algorithm,
                "path": search.path,
                "route_coordinates": route_coordinates,
                "expanded_trace_coordinates": expanded_trace_coordinates,
                "start_node": str(start_node),
                "start_node_latitude": start_node_latitude,
                "start_node_longitude": start_node_longitude,
                "start_snap_distance_m": start_snap_distance_m,
                "station_road_latitude": float(station["road_projection_latitude"]),
                "station_road_longitude": float(station["road_projection_longitude"]),
                "station_latitude": float(station["latitude"]),
                "station_longitude": float(station["longitude"]),
                "distance_km": search.distance_km,
                "drive_time_min": search.drive_time_min,
                "road_snap_distance_m": float(station["road_snap_distance_m"]),
                "road_edge": f"{station['road_edge_u']}-{station['road_edge_v']}-{int(station['road_edge_key'])}",
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


def _node_coordinates(graph, node: str) -> tuple[float, float]:
    """Return a graph node as a latitude/longitude pair."""
    node_data = graph.nodes[node]
    return float(node_data["y"]), float(node_data["x"])


def _path_to_route_coordinates(graph, path: list[str]) -> list[tuple[float, float]]:
    """Convert a graph path to route coordinates using edge geometry when available."""
    if len(path) <= 1:
        return [_node_coordinates(graph, node) for node in path]

    coordinates = []
    for u, v in zip(path, path[1:]):
        segment = _edge_route_coordinates(graph, u, v)
        if coordinates and segment and coordinates[-1] == segment[0]:
            coordinates.extend(segment[1:])
        else:
            coordinates.extend(segment)
    return coordinates


def _nodes_to_coordinates(graph, nodes: list[str]) -> list[tuple[float, float]]:
    coordinates = []
    for node in nodes:
        try:
            coordinates.append(_node_coordinates(graph, node))
        except KeyError:
            continue
    return coordinates


def _edge_route_coordinates(graph, u: str, v: str) -> list[tuple[float, float]]:
    edge_data = graph.get_edge_data(u, v, default={})
    if not edge_data:
        return [_node_coordinates(graph, u), _node_coordinates(graph, v)]

    best_attrs = min(edge_data.values(), key=lambda attrs: _safe_float(attrs.get("travel_time"), float("inf")))
    geometry = best_attrs.get("geometry")
    if geometry is None:
        return [_node_coordinates(graph, u), _node_coordinates(graph, v)]

    return [(float(lat), float(lon)) for lon, lat in geometry.coords]


def _safe_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rejected_result(station: pd.Series, algorithm: str, reason: str) -> dict:
    return {
        "station_id": int(station["station_id"]) if pd.notna(station.get("station_id")) else None,
        "access_node": None,
        "algorithm": algorithm,
        "path": [],
        "route_coordinates": [],
        "expanded_trace_coordinates": [],
        "start_node": None,
        "start_node_latitude": None,
        "start_node_longitude": None,
        "start_snap_distance_m": None,
        "station_road_latitude": None,
        "station_road_longitude": None,
        "station_latitude": float(station["latitude"]) if pd.notna(station.get("latitude")) else None,
        "station_longitude": float(station["longitude"]) if pd.notna(station.get("longitude")) else None,
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
    parser.add_argument("--consumption-kwh-per-km", type=float, default=0.188)
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
        consumption_kwh_per_km=args.consumption_kwh_per_km,
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
