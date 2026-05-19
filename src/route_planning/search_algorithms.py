"""BFS, UCS, and A* search over the road graph."""

from __future__ import annotations

import heapq
import math
import time
from collections import deque
from dataclasses import dataclass

from landmark_heuristic import LandmarkHeuristic


DEFAULT_HEURISTIC_SPEED_KPH = 40.0


@dataclass
class SearchResult:
    algorithm: str
    path: list[str]
    path_found: bool
    distance_km: float | None
    drive_time_min: float | None
    expanded_nodes: int
    runtime_seconds: float
    expanded_trace: list[str]


def _node_xy(graph, node: str) -> tuple[float, float]:
    data = graph.nodes[node]
    return float(data["x"]), float(data["y"])


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(a))


def _straight_line_heuristic_minutes(graph, node: str, goal: str) -> float:
    node_lon, node_lat = _node_xy(graph, node)
    goal_lon, goal_lat = _node_xy(graph, goal)
    distance_km = _haversine_km(node_lat, node_lon, goal_lat, goal_lon)
    return distance_km / DEFAULT_HEURISTIC_SPEED_KPH * 60


def _heuristic_minutes(graph, node: str, goal: str, landmark_heuristic: LandmarkHeuristic | None = None) -> float:
    if landmark_heuristic is None:
        return _straight_line_heuristic_minutes(graph, node, goal)

    if node == "__start_access__":
        start_estimate = _start_access_landmark_heuristic(graph, goal, landmark_heuristic)
        if start_estimate is not None:
            return start_estimate
        raise ValueError("ALT landmark table cannot estimate the temporary start access node.")

    estimate = landmark_heuristic.estimate_minutes(node, goal)
    if estimate is None:
        raise ValueError(f"ALT landmark table is missing node data for {node!r} or goal {goal!r}.")
    return estimate


def _start_access_landmark_heuristic(graph, goal: str, landmark_heuristic: LandmarkHeuristic) -> float | None:
    estimates = []
    for neighbor in graph.successors("__start_access__"):
        neighbor_estimate = landmark_heuristic.estimate_minutes(neighbor, goal)
        if neighbor_estimate is None:
            continue
        _, travel_time_s = _edge_metrics(graph, "__start_access__", neighbor)
        estimates.append(travel_time_s / 60 + neighbor_estimate)
    return min(estimates) if estimates else None


def _best_edge_metric(edge_data: dict, key: str, default: float = 0.0) -> float:
    values = []
    for attrs in edge_data.values():
        value = attrs.get(key, default)
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    return min(values) if values else default


def _edge_metrics(graph, u: str, v: str) -> tuple[float, float]:
    edge_data = graph.get_edge_data(u, v, default={})
    length_m = _best_edge_metric(edge_data, "length", 0.0)
    travel_time_s = _best_edge_metric(edge_data, "travel_time", length_m / 1000 / DEFAULT_HEURISTIC_SPEED_KPH * 3600)
    return length_m, travel_time_s


def _path_metrics(graph, path: list[str]) -> tuple[float, float]:
    total_length_m = 0.0
    total_time_s = 0.0
    for u, v in zip(path, path[1:]):
        length_m, travel_time_s = _edge_metrics(graph, u, v)
        total_length_m += length_m
        total_time_s += travel_time_s
    return total_length_m / 1000, total_time_s / 60


def _reconstruct_path(parent: dict[str, str | None], goal: str) -> list[str]:
    path = []
    node: str | None = goal
    while node is not None:
        path.append(node)
        node = parent[node]
    path.reverse()
    return path


def _not_found(algorithm: str, start_time: float, expanded_nodes: int, expanded_trace: list[str]) -> SearchResult:
    return SearchResult(
        algorithm=algorithm,
        path=[],
        path_found=False,
        distance_km=None,
        drive_time_min=None,
        expanded_nodes=expanded_nodes,
        runtime_seconds=time.perf_counter() - start_time,
        expanded_trace=expanded_trace,
    )


def _success(
    algorithm: str,
    graph,
    path: list[str],
    start_time: float,
    expanded_nodes: int,
    expanded_trace: list[str],
) -> SearchResult:
    distance_km, drive_time_min = _path_metrics(graph, path)
    return SearchResult(
        algorithm=algorithm,
        path=path,
        path_found=True,
        distance_km=distance_km,
        drive_time_min=drive_time_min,
        expanded_nodes=expanded_nodes,
        runtime_seconds=time.perf_counter() - start_time,
        expanded_trace=expanded_trace,
    )


def bfs_search(graph, start: str, goal: str) -> SearchResult:
    started = time.perf_counter()
    queue = deque([start])
    parent: dict[str, str | None] = {start: None}
    visited = {start}
    expanded = 0
    expanded_trace = []

    while queue:
        node = queue.popleft()
        expanded += 1
        expanded_trace.append(node)
        if node == goal:
            path = _reconstruct_path(parent, goal)
            return _success("bfs", graph, path, started, expanded, expanded_trace)
        for neighbor in graph.successors(node):
            if neighbor not in visited:
                visited.add(neighbor)
                parent[neighbor] = node
                queue.append(neighbor)
    return _not_found("bfs", started, expanded, expanded_trace)


def ucs_search(graph, start: str, goal: str) -> SearchResult:
    started = time.perf_counter()
    heap = [(0.0, start)]
    best_cost = {start: 0.0}
    parent: dict[str, str | None] = {start: None}
    expanded = 0
    expanded_trace = []

    while heap:
        cost, node = heapq.heappop(heap)
        if cost > best_cost.get(node, float("inf")):
            continue
        expanded += 1
        expanded_trace.append(node)
        if node == goal:
            path = _reconstruct_path(parent, goal)
            return _success("ucs", graph, path, started, expanded, expanded_trace)
        for neighbor in graph.successors(node):
            _, travel_time_s = _edge_metrics(graph, node, neighbor)
            new_cost = cost + travel_time_s / 60
            if new_cost < best_cost.get(neighbor, float("inf")):
                best_cost[neighbor] = new_cost
                parent[neighbor] = node
                heapq.heappush(heap, (new_cost, neighbor))
    return _not_found("ucs", started, expanded, expanded_trace)


def astar_search(
    graph,
    start: str,
    goal: str,
    landmark_heuristic: LandmarkHeuristic | None = None,
) -> SearchResult:
    started = time.perf_counter()
    heap = [(_heuristic_minutes(graph, start, goal, landmark_heuristic), 0.0, start)]
    best_cost = {start: 0.0}
    parent: dict[str, str | None] = {start: None}
    expanded = 0
    expanded_trace = []

    while heap:
        _, cost, node = heapq.heappop(heap)
        if cost > best_cost.get(node, float("inf")):
            continue
        expanded += 1
        expanded_trace.append(node)
        if node == goal:
            path = _reconstruct_path(parent, goal)
            return _success("astar", graph, path, started, expanded, expanded_trace)
        for neighbor in graph.successors(node):
            _, travel_time_s = _edge_metrics(graph, node, neighbor)
            new_cost = cost + travel_time_s / 60
            if new_cost < best_cost.get(neighbor, float("inf")):
                best_cost[neighbor] = new_cost
                parent[neighbor] = node
                priority = new_cost + _heuristic_minutes(graph, neighbor, goal, landmark_heuristic)
                heapq.heappush(heap, (priority, new_cost, neighbor))
    return _not_found("astar", started, expanded, expanded_trace)


def run_search(
    graph,
    start: str,
    goal: str,
    algorithm: str,
    landmark_heuristic: LandmarkHeuristic | None = None,
) -> SearchResult:
    algorithm = algorithm.lower()
    if algorithm == "bfs":
        return bfs_search(graph, start, goal)
    if algorithm == "ucs":
        return ucs_search(graph, start, goal)
    if algorithm in {"astar", "a*"}:
        return astar_search(graph, start, goal, landmark_heuristic)
    raise ValueError(f"Unsupported algorithm: {algorithm}")
