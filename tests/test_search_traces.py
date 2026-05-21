from __future__ import annotations

import sys
from pathlib import Path

import networkx as nx
import pytest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PLANNING_DIR = PROJECT_ROOT / "src" / "route_planning"
if str(ROUTE_PLANNING_DIR) not in sys.path:
    sys.path.insert(0, str(ROUTE_PLANNING_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.schemas import RecommendationRequest, SearchTrace
from ch_index import CHEdge, CHIndex
from ch_preprocess import build_ch_index
from ch_search import _frontiers_cannot_improve, ch_bidirectional_dijkstra_search
from graph_loader import _StartAccessGraph
from search_algorithms import SearchContext, astar_search, bfs_search, bidirectional_bfs_search, run_search, ucs_search


def _graph(edges: list[tuple[str, str]]) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    nodes = sorted({node for edge in edges for node in edge})
    for index, node in enumerate(nodes):
        graph.add_node(node, x=float(index), y=0.0)
    for u, v in edges:
        graph.add_edge(u, v, length=1000.0, travel_time=60.0)
    return graph


def _weighted_graph(edges: list[tuple[str, str, float]]) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    nodes = sorted({node for edge in edges for node in edge[:2]})
    for index, node in enumerate(nodes):
        graph.add_node(node, x=float(index), y=0.0)
    for u, v, minutes in edges:
        graph.add_edge(u, v, length=minutes * 1000.0, travel_time=minutes * 60.0)
    return graph


def _layer_nodes(result, role: str) -> list[str]:
    layer = next(layer for layer in result.search_trace.layers if layer.role == role)
    return layer.nodes


def test_bfs_returns_single_trace_on_directed_graph() -> None:
    graph = _graph([("A", "B"), ("B", "C"), ("C", "D")])

    result = bfs_search(graph, "A", "D")

    assert result.algorithm == "bfs"
    assert result.path == ["A", "B", "C", "D"]
    assert result.search_trace.kind == "single"
    assert _layer_nodes(result, "single") == ["A", "B", "C", "D"]
    assert result.search_trace.meeting_node is None


def test_bidirectional_bfs_uses_two_frontier_trace_on_directed_graph() -> None:
    graph = _graph([("A", "B"), ("B", "C"), ("C", "D")])

    result = bidirectional_bfs_search(graph, "A", "D")

    assert result.algorithm == "bidirectional_bfs"
    assert result.path == ["A", "B", "C", "D"]
    assert result.search_trace.kind == "bidirectional"
    assert _layer_nodes(result, "forward") == ["A", "B"]
    assert _layer_nodes(result, "backward") == ["D"]
    assert result.search_trace.meeting_node == "C"


def test_bfs_supports_start_access_graph_predecessors() -> None:
    graph = _graph([("B", "C"), ("C", "D")])
    start_graph = _StartAccessGraph(
        graph,
        "__start_access__",
        {"x": -1.0, "y": 0.0},
        {"B": {"length": 250.0, "travel_time": 15.0}},
    )

    result = bidirectional_bfs_search(start_graph, "__start_access__", "D")

    assert result.path == ["__start_access__", "B", "C", "D"]
    assert result.search_trace.kind == "bidirectional"
    assert result.search_trace.meeting_node == "C"


def test_bfs_start_equals_goal_returns_single_trace() -> None:
    graph = _graph([("A", "B")])

    result = bfs_search(graph, "A", "A")

    assert result.path == ["A"]
    assert result.search_trace.kind == "single"
    assert _layer_nodes(result, "single") == ["A"]
    assert result.search_trace.meeting_node is None


def test_bidirectional_bfs_start_equals_goal_returns_two_frontier_trace() -> None:
    graph = _graph([("A", "B")])

    result = bidirectional_bfs_search(graph, "A", "A")

    assert result.path == ["A"]
    assert result.search_trace.kind == "bidirectional"
    assert _layer_nodes(result, "forward") == ["A"]
    assert _layer_nodes(result, "backward") == ["A"]
    assert result.search_trace.meeting_node == "A"


def test_bfs_no_path_returns_empty_path_with_single_trace() -> None:
    graph = _graph([("A", "B"), ("C", "D")])

    result = bfs_search(graph, "A", "D")

    assert result.path == []
    assert not result.path_found
    assert result.search_trace.kind == "single"
    assert _layer_nodes(result, "single") == ["A", "B"]
    assert result.search_trace.meeting_node is None


def test_bidirectional_bfs_no_path_returns_empty_path_with_partial_bidirectional_trace() -> None:
    graph = _graph([("A", "B"), ("C", "D")])

    result = bidirectional_bfs_search(graph, "A", "D")

    assert result.path == []
    assert not result.path_found
    assert result.search_trace.kind == "bidirectional"
    assert _layer_nodes(result, "forward") == ["A", "B"]
    assert _layer_nodes(result, "backward") == ["D", "C"]
    assert result.search_trace.meeting_node is None


@pytest.mark.parametrize("search", [ucs_search, astar_search])
def test_single_frontier_algorithms_return_single_trace(search) -> None:
    graph = _graph([("A", "B"), ("B", "C")])

    result = search(graph, "A", "C")

    assert result.path == ["A", "B", "C"]
    assert result.search_trace.kind == "single"
    assert _layer_nodes(result, "single") == ["A", "B", "C"]
    assert result.search_trace.meeting_node is None


def test_search_trace_schema_rejects_non_single_layer_for_single_trace() -> None:
    with pytest.raises(ValidationError):
        SearchTrace.model_validate(
            {
                "kind": "single",
                "layers": [{"role": "forward", "coordinates": [(1.0, 2.0)]}],
            }
        )


def test_search_trace_schema_rejects_meeting_node_for_single_trace() -> None:
    with pytest.raises(ValidationError):
        SearchTrace.model_validate(
            {
                "kind": "single",
                "layers": [{"role": "single", "coordinates": [(1.0, 2.0)]}],
                "meeting_node_coordinate": (3.0, 4.0),
            }
        )


def test_search_trace_schema_requires_bidirectional_layers() -> None:
    with pytest.raises(ValidationError):
        SearchTrace.model_validate(
            {
                "kind": "bidirectional",
                "layers": [{"role": "forward", "coordinates": [(1.0, 2.0)]}],
            }
        )


def test_schema_accepts_ch_dijkstra_algorithm() -> None:
    request = RecommendationRequest(lat=22.65, lng=114.05, algorithm="ch_bidirectional_dijkstra")

    assert request.algorithm == "ch_bidirectional_dijkstra"


class _ExplodingLandmark:
    def estimate_minutes(self, node: str, goal: str) -> float | None:
        raise AssertionError("baseline A* should not call landmark heuristic")


class _CountingLandmark:
    def __init__(self) -> None:
        self.calls = 0

    def estimate_minutes(self, node: str, goal: str) -> float | None:
        self.calls += 1
        return 0.0


def test_run_search_astar_ignores_landmark_heuristic() -> None:
    graph = _graph([("A", "B"), ("B", "C")])

    result = run_search(graph, "A", "C", "astar", SearchContext(landmark_heuristic=_ExplodingLandmark()))

    assert result.algorithm == "astar"
    assert result.path == ["A", "B", "C"]


def test_run_search_alt_astar_uses_landmark_heuristic() -> None:
    graph = _graph([("A", "B"), ("B", "C")])
    landmark = _CountingLandmark()

    result = run_search(graph, "A", "C", "alt_astar", SearchContext(landmark_heuristic=landmark))

    assert result.algorithm == "alt_astar"
    assert result.path == ["A", "B", "C"]
    assert landmark.calls > 0


def test_run_search_alt_astar_requires_landmark_heuristic() -> None:
    graph = _graph([("A", "B"), ("B", "C")])

    with pytest.raises(ValueError, match="ALT landmark table is required"):
        run_search(graph, "A", "C", "alt_astar", SearchContext())


def test_ch_dijkstra_matches_ucs_cost_on_directed_graph() -> None:
    graph = _weighted_graph(
        [
            ("A", "B", 1.0),
            ("B", "D", 1.0),
            ("A", "C", 4.0),
            ("C", "D", 1.0),
            ("B", "C", 1.0),
        ]
    )
    index = build_ch_index(graph)

    ch_result = ch_bidirectional_dijkstra_search(graph, "A", "D", index)
    ucs_result = ucs_search(graph, "A", "D")

    assert ch_result.algorithm == "ch_bidirectional_dijkstra"
    assert ch_result.path_found
    assert ch_result.drive_time_min == pytest.approx(ucs_result.drive_time_min)
    assert ch_result.search_trace.kind == "bidirectional"
    assert _layer_nodes(ch_result, "forward")
    assert _layer_nodes(ch_result, "backward")
    assert ch_result.search_trace.meeting_node is not None


def test_ch_index_excludes_replaced_edges_from_query_graph() -> None:
    graph = nx.MultiDiGraph()
    graph.add_node("A", x=0.0, y=0.0)
    graph.add_node("B", x=1.0, y=0.0)
    graph.add_edge("A", "B", length=5000.0, travel_time=300.0)
    graph.add_edge("A", "B", length=1000.0, travel_time=60.0)

    index = build_ch_index(graph)
    query_edge_ids = {edge_id for edges in index.upward.values() for edge_id in edges}
    query_edge_ids.update(edge_id for edges in index.reverse_upward.values() for edge_id in edges)
    query_edges = [index.edge(edge_id) for edge_id in query_edge_ids]

    assert len(query_edges) == 1
    assert query_edges[0].u == "A"
    assert query_edges[0].v == "B"
    assert query_edges[0].weight_min == pytest.approx(1.0)


def test_ch_frontier_stop_waits_until_each_settled_frontier_cannot_improve() -> None:
    assert _frontiers_cannot_improve([(10.0, "F")], [(12.0, "B")], 10.0)
    assert not _frontiers_cannot_improve([(4.0, "F")], [(12.0, "B")], 10.0)


def test_ch_dijkstra_updates_best_from_unsettled_opposite_frontier() -> None:
    graph = _weighted_graph(
        [
            ("S", "X", 5.0),
            ("X", "T", 5.0),
            ("S", "M", 6.0),
            ("M", "T", 3.0),
        ]
    )
    index = CHIndex(
        ranks={"S": 0, "T": 1, "X": 2, "M": 3},
        upward={"S": [0, 1]},
        reverse_upward={"T": [2, 3]},
        edges={
            0: CHEdge(0, "S", "X", 5.0, 5000.0),
            1: CHEdge(1, "S", "M", 6.0, 6000.0),
            2: CHEdge(2, "X", "T", 5.0, 5000.0),
            3: CHEdge(3, "M", "T", 3.0, 3000.0),
        },
    )

    result = ch_bidirectional_dijkstra_search(graph, "S", "T", index)

    assert result.path == ["S", "M", "T"]
    assert result.drive_time_min == pytest.approx(9.0)


def test_ch_shortcut_unpacks_to_original_nodes() -> None:
    index = CHIndex(
        ranks={"A": 2, "B": 1, "C": 3},
        upward={"A": [2]},
        reverse_upward={},
        edges={
            0: CHEdge(0, "A", "B", 1.0, 1000.0),
            1: CHEdge(1, "B", "C", 1.0, 1000.0),
            2: CHEdge(2, "A", "C", 2.0, 2000.0, "B", 0, 1),
        },
    )

    assert index.unpack_edge_nodes(2) == ["A", "B", "C"]
    assert index.unpack_edge_metrics(2) == (2000.0, 2.0)


def test_ch_dijkstra_respects_edge_direction() -> None:
    graph = _weighted_graph([("A", "B", 1.0), ("B", "C", 1.0)])
    index = build_ch_index(graph)

    result = ch_bidirectional_dijkstra_search(graph, "C", "A", index)

    assert result.path == []
    assert not result.path_found
    assert result.search_trace.kind == "bidirectional"


def test_ch_dijkstra_start_equals_goal_returns_bidirectional_trace() -> None:
    graph = _weighted_graph([("A", "B", 1.0)])
    index = build_ch_index(graph)

    result = ch_bidirectional_dijkstra_search(graph, "A", "A", index)

    assert result.path == ["A"]
    assert result.path_found
    assert result.search_trace.kind == "bidirectional"
    assert _layer_nodes(result, "forward") == ["A"]
    assert _layer_nodes(result, "backward") == ["A"]
    assert result.search_trace.meeting_node == "A"


def test_ch_dijkstra_no_path_returns_empty_path() -> None:
    graph = _weighted_graph([("A", "B", 1.0), ("C", "D", 1.0)])
    index = build_ch_index(graph)

    result = ch_bidirectional_dijkstra_search(graph, "A", "D", index)

    assert result.path == []
    assert not result.path_found
    assert result.search_trace.kind == "bidirectional"


def test_ch_dijkstra_supports_start_access_overlay() -> None:
    graph = _weighted_graph([("B", "C", 1.0), ("C", "D", 1.0)])
    index = build_ch_index(graph)
    start_graph = _StartAccessGraph(
        graph,
        "__start_access__",
        {"x": -1.0, "y": 0.0},
        {"B": {"length": 250.0, "travel_time": 15.0}},
    )

    result = ch_bidirectional_dijkstra_search(start_graph, "__start_access__", "D", index)

    assert result.path == ["__start_access__", "B", "C", "D"]
    assert result.path_found
    assert result.drive_time_min == pytest.approx(2.25)
    assert result.search_trace.kind == "bidirectional"


def test_run_search_dispatches_ch_dijkstra() -> None:
    graph = _weighted_graph([("A", "B", 1.0), ("B", "C", 1.0)])
    index = build_ch_index(graph)

    result = run_search(graph, "A", "C", "ch_bidirectional_dijkstra", SearchContext(ch_index=index))

    assert result.algorithm == "ch_bidirectional_dijkstra"
    assert result.path_found
    assert result.search_trace.kind == "bidirectional"
