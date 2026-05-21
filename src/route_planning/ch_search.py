"""Bidirectional Dijkstra query over a contraction hierarchy index."""

from __future__ import annotations

import heapq
import time

from ch_index import CHIndex
from graph_metrics import edge_metrics, path_metrics
from search_algorithms import SearchResult, SearchTrace, SearchTraceLayer


CH_ALGORITHM = "ch_bidirectional_dijkstra"


def ch_bidirectional_dijkstra_search(graph, start: str, goal: str, ch_index: CHIndex) -> SearchResult:
    started = time.perf_counter()
    if start == goal:
        return _result(graph, [start], True, 1, started, [start], [goal], start)
    if not ch_index.contains(goal):
        return _result(graph, [], False, 0, started, [], [], None)

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
    forward_settled: set[str] = set()
    backward_settled: set[str] = set()

    while forward_heap or backward_heap:
        if _frontiers_cannot_improve(forward_heap, backward_heap, best_total):
            break

        if _heap_min(forward_heap) <= _heap_min(backward_heap):
            cost, node = heapq.heappop(forward_heap)
            if cost > forward_best.get(node, float("inf")) or node in forward_settled:
                continue
            forward_settled.add(node)
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
                if edge.v in backward_best and new_cost + backward_best[edge.v] < best_total:
                    best_total = new_cost + backward_best[edge.v]
                    meeting_node = edge.v
        else:
            cost, node = heapq.heappop(backward_heap)
            if cost > backward_best.get(node, float("inf")) or node in backward_settled:
                continue
            backward_settled.add(node)
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
                if edge.u in forward_best and new_cost + forward_best[edge.u] < best_total:
                    best_total = new_cost + forward_best[edge.u]
                    meeting_node = edge.u

    if meeting_node is None:
        return _result(graph, [], False, expanded, started, forward_trace, backward_trace, None)

    path = _reconstruct_path(start, meeting_node, forward_parent, backward_parent, ch_index)
    return _result(graph, path, True, expanded, started, forward_trace, backward_trace, meeting_node)


def _frontiers_cannot_improve(
    forward_heap: list[tuple[float, str]],
    backward_heap: list[tuple[float, str]],
    best_total: float,
) -> bool:
    if best_total == float("inf"):
        return False
    return _heap_min(forward_heap) >= best_total and _heap_min(backward_heap) >= best_total


def _heap_min(heap: list[tuple[float, str]]) -> float:
    return heap[0][0] if heap else float("inf")


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
        _, travel_time_s = edge_metrics(graph, start, neighbor)
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
) -> SearchResult:
    if path_found:
        distance_km, drive_time_min = path_metrics(graph, path)
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
