"""BFS, UCS, and A* search over the road graph."""

from __future__ import annotations

import heapq
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

from graph_metrics import DEFAULT_SPEED_KPH, edge_metrics, path_metrics
from landmark_heuristic import LandmarkHeuristic


DEFAULT_HEURISTIC_SPEED_KPH = DEFAULT_SPEED_KPH

SearchTraceKind = Literal["single", "bidirectional"]
SearchTraceRole = Literal["single", "forward", "backward"]


@dataclass(frozen=True)
class SearchTraceLayer:
    role: SearchTraceRole
    nodes: list[str]
    edges: list[list[str]]


@dataclass(frozen=True)
class CandidatePathEvent:
    step: int
    path: list[str]


@dataclass(frozen=True)
class SearchTrace:
    kind: SearchTraceKind
    layers: list[SearchTraceLayer]
    meeting_node: str | None = None
    candidate_path_events: list[CandidatePathEvent] = field(default_factory=list)


@dataclass
class SearchResult:
    algorithm: str
    path: list[str]
    path_found: bool
    distance_km: float | None
    drive_time_min: float | None
    expanded_nodes: int
    runtime_seconds: float
    search_trace: SearchTrace
    route_trace_path: list[str] | None = None


@dataclass(frozen=True)
class SearchContext:
    landmark_heuristic: LandmarkHeuristic | None = None
    ch_index: object | None = None

    def require_landmark_heuristic(self) -> LandmarkHeuristic:
        if self.landmark_heuristic is None:
            raise ValueError("ALT landmark table is required for alt_astar.")
        return self.landmark_heuristic

    def require_ch_index(self):
        if self.ch_index is None:
            raise ValueError("CH index is required for ch_bidirectional_dijkstra.")
        return self.ch_index


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
        _, travel_time_s = edge_metrics(graph, "__start_access__", neighbor)
        estimates.append(travel_time_s / 60 + neighbor_estimate)
    return min(estimates) if estimates else None


def _reconstruct_path(parent: dict[str, str | None], goal: str) -> list[str]:
    path = []
    node: str | None = goal
    while node is not None:
        path.append(node)
        node = parent[node]
    path.reverse()
    return path


def _append_candidate_path_event(candidate_path_events: list[CandidatePathEvent], step: int, path: list[str]) -> None:
    if path and (not candidate_path_events or candidate_path_events[-1].path != path):
        candidate_path_events.append(CandidatePathEvent(step=step, path=path))


def _queue_candidate_path(parent: dict[str, str | None], queue: deque[str]) -> list[str]:
    return _reconstruct_path(parent, queue[0]) if queue else []


def _cost_heap_candidate_path(
    parent: dict[str, str | None],
    heap: list[tuple[float, str]],
    best_cost: dict[str, float],
) -> list[str]:
    for cost, node in sorted(heap):
        if math.isclose(cost, best_cost.get(node, float("inf"))):
            return _reconstruct_path(parent, node)
    return []


def _priority_heap_candidate_path(
    parent: dict[str, str | None],
    heap: list[tuple[float, float, str]],
    best_cost: dict[str, float],
) -> list[str]:
    for _, cost, node in sorted(heap):
        if math.isclose(cost, best_cost.get(node, float("inf"))):
            return _reconstruct_path(parent, node)
    return []


def _reconstruct_bidirectional_path(
    forward_parent: dict[str, str | None],
    backward_parent: dict[str, str | None],
    meeting_node: str,
) -> list[str]:
    forward_path = _reconstruct_path(forward_parent, meeting_node)
    backward_path = []
    node = backward_parent[meeting_node]
    while node is not None:
        backward_path.append(node)
        node = backward_parent[node]
    return forward_path + backward_path


def _not_found(
    algorithm: str,
    start_time: float,
    expanded_nodes: int,
    search_trace: SearchTrace,
) -> SearchResult:
    return SearchResult(
        algorithm=algorithm,
        path=[],
        path_found=False,
        distance_km=None,
        drive_time_min=None,
        expanded_nodes=expanded_nodes,
        runtime_seconds=time.perf_counter() - start_time,
        search_trace=search_trace,
    )


def _success(
    algorithm: str,
    graph,
    path: list[str],
    start_time: float,
    expanded_nodes: int,
    search_trace: SearchTrace,
) -> SearchResult:
    distance_km, drive_time_min = path_metrics(graph, path)
    return SearchResult(
        algorithm=algorithm,
        path=path,
        path_found=True,
        distance_km=distance_km,
        drive_time_min=drive_time_min,
        expanded_nodes=expanded_nodes,
        runtime_seconds=time.perf_counter() - start_time,
        search_trace=search_trace,
        route_trace_path=path,
    )


def _single_trace(
    nodes: list[str],
    edges: list[list[str]],
    candidate_path_events: list[CandidatePathEvent] | None = None,
) -> SearchTrace:
    return SearchTrace(
        kind="single",
        layers=[SearchTraceLayer(role="single", nodes=nodes, edges=edges)],
        candidate_path_events=candidate_path_events or [],
    )


def _bidirectional_trace(
    forward_nodes: list[str],
    backward_nodes: list[str],
    forward_edges: list[list[str]],
    backward_edges: list[list[str]],
    meeting_node: str | None = None,
    candidate_path_events: list[CandidatePathEvent] | None = None,
) -> SearchTrace:
    return SearchTrace(
        kind="bidirectional",
        layers=[
            SearchTraceLayer(role="forward", nodes=forward_nodes, edges=forward_edges),
            SearchTraceLayer(role="backward", nodes=backward_nodes, edges=backward_edges),
        ],
        meeting_node=meeting_node,
        candidate_path_events=candidate_path_events or [],
    )


def bfs_search(graph, start: str, goal: str) -> SearchResult:
    """Run baseline BFS over directed road edges."""
    started = time.perf_counter()
    queue = deque([start])
    parent: dict[str, str | None] = {start: None}
    visited = {start}
    expanded = 0
    expanded_trace = []
    trace_edges = []
    candidate_path_events = []

    while queue:
        node = queue.popleft()
        expanded += 1
        expanded_trace.append(node)
        if node == goal:
            path = _reconstruct_path(parent, goal)
            _append_candidate_path_event(candidate_path_events, len(expanded_trace), path)
            return _success("bfs", graph, path, started, expanded, _single_trace(expanded_trace, trace_edges, candidate_path_events))
        for neighbor in graph.successors(node):
            if neighbor not in visited:
                visited.add(neighbor)
                parent[neighbor] = node
                trace_edges.append([node, neighbor])
                queue.append(neighbor)
        _append_candidate_path_event(candidate_path_events, len(expanded_trace), _queue_candidate_path(parent, queue))
    return _not_found("bfs", started, expanded, _single_trace(expanded_trace, trace_edges, candidate_path_events))


def bidirectional_bfs_search(graph, start: str, goal: str) -> SearchResult:
    """Run bidirectional BFS over directed road edges.

    The trace records nodes after they are popped for expansion; the meeting
    node records the first intersection between the two visited frontiers.
    """
    started = time.perf_counter()
    if start == goal:
        return _success(
            "bidirectional_bfs",
            graph,
            [start],
            started,
            1,
            _bidirectional_trace([start], [goal], [], [], start),
        )

    forward_queue = deque([start])
    backward_queue = deque([goal])
    forward_parent: dict[str, str | None] = {start: None}
    backward_parent: dict[str, str | None] = {goal: None}
    forward_visited = {start}
    backward_visited = {goal}
    expanded = 0
    forward_trace_nodes = []
    backward_trace_nodes = []
    forward_trace_edges = []
    backward_trace_edges = []
    candidate_path_events = []

    def expand_forward_layer() -> str | None:
        nonlocal expanded
        for _ in range(len(forward_queue)):
            node = forward_queue.popleft()
            expanded += 1
            forward_trace_nodes.append(node)
            for neighbor in graph.successors(node):
                if neighbor in forward_visited:
                    continue
                forward_visited.add(neighbor)
                forward_parent[neighbor] = node
                forward_trace_edges.append([node, neighbor])
                if neighbor in backward_visited:
                    return neighbor
                forward_queue.append(neighbor)
        return None

    def expand_backward_layer() -> str | None:
        nonlocal expanded
        for _ in range(len(backward_queue)):
            node = backward_queue.popleft()
            expanded += 1
            backward_trace_nodes.append(node)
            for predecessor in graph.predecessors(node):
                if predecessor in backward_visited:
                    continue
                backward_visited.add(predecessor)
                backward_parent[predecessor] = node
                backward_trace_edges.append([predecessor, node])
                if predecessor in forward_visited:
                    return predecessor
                backward_queue.append(predecessor)
        return None

    while forward_queue and backward_queue:
        meeting_node = expand_forward_layer()
        if meeting_node is None:
            meeting_node = expand_backward_layer()
        if meeting_node is not None:
            path = _reconstruct_bidirectional_path(forward_parent, backward_parent, meeting_node)
            _append_candidate_path_event(candidate_path_events, len(forward_trace_nodes) + len(backward_trace_nodes), path)
            return _success(
                "bidirectional_bfs",
                graph,
                path,
                started,
                expanded,
                _bidirectional_trace(
                    forward_trace_nodes,
                    backward_trace_nodes,
                    forward_trace_edges,
                    backward_trace_edges,
                    meeting_node,
                    candidate_path_events,
                ),
            )

    return _not_found(
        "bidirectional_bfs",
        started,
        expanded,
        _bidirectional_trace(
            forward_trace_nodes,
            backward_trace_nodes,
            forward_trace_edges,
            backward_trace_edges,
            candidate_path_events=candidate_path_events,
        ),
    )


def ucs_search(graph, start: str, goal: str) -> SearchResult:
    started = time.perf_counter()
    heap = [(0.0, start)]
    best_cost = {start: 0.0}
    parent: dict[str, str | None] = {start: None}
    expanded = 0
    expanded_trace = []
    trace_edges = []
    candidate_path_events = []

    while heap:
        cost, node = heapq.heappop(heap)
        if cost > best_cost.get(node, float("inf")):
            continue
        expanded += 1
        expanded_trace.append(node)
        if node == goal:
            path = _reconstruct_path(parent, goal)
            _append_candidate_path_event(candidate_path_events, len(expanded_trace), path)
            return _success("ucs", graph, path, started, expanded, _single_trace(expanded_trace, trace_edges, candidate_path_events))
        for neighbor in graph.successors(node):
            _, travel_time_s = edge_metrics(graph, node, neighbor)
            new_cost = cost + travel_time_s / 60
            if new_cost < best_cost.get(neighbor, float("inf")):
                best_cost[neighbor] = new_cost
                parent[neighbor] = node
                trace_edges.append([node, neighbor])
                heapq.heappush(heap, (new_cost, neighbor))
        _append_candidate_path_event(candidate_path_events, len(expanded_trace), _cost_heap_candidate_path(parent, heap, best_cost))
    return _not_found("ucs", started, expanded, _single_trace(expanded_trace, trace_edges, candidate_path_events))


def astar_search(
    graph,
    start: str,
    goal: str,
    landmark_heuristic: LandmarkHeuristic | None = None,
    algorithm: str = "astar",
) -> SearchResult:
    started = time.perf_counter()
    heap = [(_heuristic_minutes(graph, start, goal, landmark_heuristic), 0.0, start)]
    best_cost = {start: 0.0}
    parent: dict[str, str | None] = {start: None}
    expanded = 0
    expanded_trace = []
    trace_edges = []
    candidate_path_events = []

    while heap:
        _, cost, node = heapq.heappop(heap)
        if cost > best_cost.get(node, float("inf")):
            continue
        expanded += 1
        expanded_trace.append(node)
        if node == goal:
            path = _reconstruct_path(parent, goal)
            _append_candidate_path_event(candidate_path_events, len(expanded_trace), path)
            return _success(algorithm, graph, path, started, expanded, _single_trace(expanded_trace, trace_edges, candidate_path_events))
        for neighbor in graph.successors(node):
            _, travel_time_s = edge_metrics(graph, node, neighbor)
            new_cost = cost + travel_time_s / 60
            if new_cost < best_cost.get(neighbor, float("inf")):
                best_cost[neighbor] = new_cost
                parent[neighbor] = node
                trace_edges.append([node, neighbor])
                priority = new_cost + _heuristic_minutes(graph, neighbor, goal, landmark_heuristic)
                heapq.heappush(heap, (priority, new_cost, neighbor))
        _append_candidate_path_event(candidate_path_events, len(expanded_trace), _priority_heap_candidate_path(parent, heap, best_cost))
    return _not_found(algorithm, started, expanded, _single_trace(expanded_trace, trace_edges, candidate_path_events))


def alt_astar_search(
    graph,
    start: str,
    goal: str,
    landmark_heuristic: LandmarkHeuristic,
) -> SearchResult:
    return astar_search(graph, start, goal, landmark_heuristic, algorithm="alt_astar")


def run_search(
    graph,
    start: str,
    goal: str,
    algorithm: str,
    context: SearchContext | None = None,
) -> SearchResult:
    context = context or SearchContext()
    algorithm = algorithm.lower()
    if algorithm == "bfs":
        return bfs_search(graph, start, goal)
    if algorithm == "bidirectional_bfs":
        return bidirectional_bfs_search(graph, start, goal)
    if algorithm == "ucs":
        return ucs_search(graph, start, goal)
    if algorithm == "astar":
        return astar_search(graph, start, goal)
    if algorithm == "alt_astar":
        return alt_astar_search(graph, start, goal, context.require_landmark_heuristic())
    if algorithm == "ch_bidirectional_dijkstra":
        from ch_search import ch_bidirectional_dijkstra_search

        return ch_bidirectional_dijkstra_search(graph, start, goal, context.require_ch_index())
    raise ValueError(f"Unsupported algorithm: {algorithm}")
