"""Bidirectional Dijkstra query over a contraction hierarchy index."""

from __future__ import annotations

import heapq
import time

from ch_index import CHIndex
from search_algorithms import SearchResult, SearchTrace, SearchTraceLayer


CH_ALGORITHM = "ch_bidirectional_dijkstra"


def ch_bidirectional_dijkstra_search(graph, start: str, goal: str, ch_index: CHIndex) -> SearchResult:
    started = time.perf_counter()
    if start == goal:
        return _result(graph, [start], True, 1, started, [start], [goal], start, ch_index)
    if not ch_index.contains(goal):
        return _result(graph, [], False, 0, started, [], [], None, ch_index)

    forward_heap: list[tuple[float, str]] = []
    forward_best: dict[str, float] = {}
    forward_parent: dict[str, tuple[str | None, int | None]] = {}
    _seed_forward_frontier(graph, start, ch_index, forward_heap, forward_best, forward_parent)

    backward_heap: list[tuple[float, str]] = [(0.0, goal)]
    backward_best = {goal: 0.0}
    backward_parent: dict[str, tuple[str | None, int | None]] = {goal: (None, None)}

    best_total = float("inf")
    meeting_node: str | None = None
    expanded = 0
    forward_trace: list[str] = []
    backward_trace: list[str] = []

    while forward_heap or backward_heap:
        forward_min = forward_heap[0][0] if forward_heap else float("inf")
        backward_min = backward_heap[0][0] if backward_heap else float("inf")

        if forward_min <= backward_min:
            cost, node = heapq.heappop(forward_heap)
            if cost > forward_best.get(node, float("inf")):
                continue
            expanded += 1
            forward_trace.append(node)
            if node in backward_best and cost + backward_best[node] < best_total:
                best_total = cost + backward_best[node]
                meeting_node = node
            for edge_id in ch_index.upward.get(node, []):
                edge = ch_index.edge(edge_id)
                new_cost = cost + edge.weight_min
                if new_cost < forward_best.get(edge.v, float("inf")):
                    forward_best[edge.v] = new_cost
                    forward_parent[edge.v] = (node, edge_id)
                    heapq.heappush(forward_heap, (new_cost, edge.v))
        else:
            cost, node = heapq.heappop(backward_heap)
            if cost > backward_best.get(node, float("inf")):
                continue
            expanded += 1
            backward_trace.append(node)
            if node in forward_best and cost + forward_best[node] < best_total:
                best_total = cost + forward_best[node]
                meeting_node = node
            for edge_id in ch_index.reverse_upward.get(node, []):
                edge = ch_index.edge(edge_id)
                new_cost = cost + edge.weight_min
                if new_cost < backward_best.get(edge.u, float("inf")):
                    backward_best[edge.u] = new_cost
                    backward_parent[edge.u] = (node, edge_id)
                    heapq.heappush(backward_heap, (new_cost, edge.u))

    if meeting_node is None:
        return _result(graph, [], False, expanded, started, forward_trace, backward_trace, None, ch_index)

    path = _reconstruct_path(start, meeting_node, forward_parent, backward_parent, ch_index)
    return _result(graph, path, True, expanded, started, forward_trace, backward_trace, meeting_node, ch_index)


def _seed_forward_frontier(
    graph,
    start: str,
    ch_index: CHIndex,
    heap: list[tuple[float, str]],
    best: dict[str, float],
    parent: dict[str, tuple[str | None, int | None]],
) -> None:
    if ch_index.contains(start):
        best[start] = 0.0
        parent[start] = (None, None)
        heapq.heappush(heap, (0.0, start))
        return

    parent[start] = (None, None)
    for neighbor in graph.successors(start):
        neighbor = str(neighbor)
        if not ch_index.contains(neighbor):
            continue
        _, travel_time_s = _edge_metrics(graph, start, neighbor)
        cost = travel_time_s / 60.0
        if cost < best.get(neighbor, float("inf")):
            best[neighbor] = cost
            parent[neighbor] = (start, None)
            heapq.heappush(heap, (cost, neighbor))


def _reconstruct_path(
    start: str,
    meeting_node: str,
    forward_parent: dict[str, tuple[str | None, int | None]],
    backward_parent: dict[str, tuple[str | None, int | None]],
    ch_index: CHIndex,
) -> list[str]:
    forward_segments: list[list[str]] = []
    node = meeting_node
    while True:
        previous, edge_id = forward_parent[node]
        if previous is None:
            break
        if edge_id is None:
            segment = [previous, node]
        else:
            segment = ch_index.unpack_edge_nodes(edge_id)
        forward_segments.append(segment)
        node = previous
    path = _join_segments(list(reversed(forward_segments)))
    if not path:
        path = [start]
    if path[-1] != meeting_node:
        path.append(meeting_node)

    node = meeting_node
    backward_segments: list[list[str]] = []
    while True:
        next_node, edge_id = backward_parent[node]
        if next_node is None:
            break
        if edge_id is None:
            segment = [node, next_node]
        else:
            segment = ch_index.unpack_edge_nodes(edge_id)
        backward_segments.append(segment)
        node = next_node
    return _join_segments([path, *backward_segments])


def _join_segments(segments: list[list[str]]) -> list[str]:
    path: list[str] = []
    for segment in segments:
        if not segment:
            continue
        if path and path[-1] == segment[0]:
            path.extend(segment[1:])
        else:
            path.extend(segment)
    return path


def _result(
    graph,
    path: list[str],
    path_found: bool,
    expanded: int,
    started: float,
    forward_trace: list[str],
    backward_trace: list[str],
    meeting_node: str | None,
    ch_index: CHIndex,
) -> SearchResult:
    if path_found:
        distance_km, drive_time_min = _path_metrics(graph, path, ch_index)
    else:
        distance_km = None
        drive_time_min = None
    return SearchResult(
        algorithm=CH_ALGORITHM,
        path=path,
        path_found=path_found,
        distance_km=distance_km,
        drive_time_min=drive_time_min,
        expanded_nodes=expanded,
        runtime_seconds=time.perf_counter() - started,
        search_trace=SearchTrace(
            kind="bidirectional",
            layers=[
                SearchTraceLayer(role="forward", nodes=forward_trace),
                SearchTraceLayer(role="backward", nodes=backward_trace),
            ],
            meeting_node=meeting_node,
        ),
    )


def _path_metrics(graph, path: list[str], ch_index: CHIndex) -> tuple[float, float]:
    total_length_m = 0.0
    total_minutes = 0.0
    for u, v in zip(path, path[1:]):
        length_m, travel_time_s = _edge_metrics(graph, u, v)
        if travel_time_s == 0.0 and ch_index.contains(u) and ch_index.contains(v):
            edge_id = _base_ch_edge_id(ch_index, u, v)
            if edge_id is not None:
                length_m, total_edge_minutes = ch_index.unpack_edge_metrics(edge_id)
                total_length_m += length_m
                total_minutes += total_edge_minutes
                continue
        total_length_m += length_m
        total_minutes += travel_time_s / 60.0
    return total_length_m / 1000.0, total_minutes


def _base_ch_edge_id(ch_index: CHIndex, u: str, v: str) -> int | None:
    for edge_id in ch_index.upward.get(u, []):
        edge = ch_index.edge(edge_id)
        if edge.v == v:
            return edge_id
    for edge_id in ch_index.reverse_upward.get(u, []):
        edge = ch_index.edge(edge_id)
        if edge.u == v:
            return edge_id
    return None


def _edge_metrics(graph, u: str, v: str) -> tuple[float, float]:
    edge_data = graph.get_edge_data(u, v, default={})
    values = list(edge_data.values()) if isinstance(edge_data, dict) else []
    if not values:
        return 0.0, 0.0
    best = min(values, key=lambda attrs: _safe_float(attrs.get("travel_time"), float("inf")))
    length_m = _safe_float(best.get("length"), 0.0)
    travel_time_s = _safe_float(best.get("travel_time"), 0.0)
    return length_m, travel_time_s


def _safe_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
