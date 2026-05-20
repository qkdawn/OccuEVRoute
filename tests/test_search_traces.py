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

from backend.schemas import SearchTrace
from graph_loader import _StartAccessGraph
from search_algorithms import astar_search, bfs_search, ucs_search


def _graph(edges: list[tuple[str, str]]) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    nodes = sorted({node for edge in edges for node in edge})
    for index, node in enumerate(nodes):
        graph.add_node(node, x=float(index), y=0.0)
    for u, v in edges:
        graph.add_edge(u, v, length=1000.0, travel_time=60.0)
    return graph


def _layer_nodes(result, role: str) -> list[str]:
    layer = next(layer for layer in result.search_trace.layers if layer.role == role)
    return layer.nodes


def test_bfs_uses_bidirectional_trace_on_directed_graph() -> None:
    graph = _graph([("A", "B"), ("B", "C"), ("C", "D")])

    result = bfs_search(graph, "A", "D")

    assert result.algorithm == "bfs"
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

    result = bfs_search(start_graph, "__start_access__", "D")

    assert result.path == ["__start_access__", "B", "C", "D"]
    assert result.search_trace.kind == "bidirectional"
    assert result.search_trace.meeting_node == "C"


def test_bfs_start_equals_goal_returns_bidirectional_single_point_trace() -> None:
    graph = _graph([("A", "B")])

    result = bfs_search(graph, "A", "A")

    assert result.path == ["A"]
    assert result.search_trace.kind == "bidirectional"
    assert _layer_nodes(result, "forward") == ["A"]
    assert _layer_nodes(result, "backward") == ["A"]
    assert result.search_trace.meeting_node == "A"


def test_bfs_no_path_returns_empty_path_with_partial_bidirectional_trace() -> None:
    graph = _graph([("A", "B"), ("C", "D")])

    result = bfs_search(graph, "A", "D")

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


def test_search_trace_schema_normalizes_single_trace_layers() -> None:
    trace = SearchTrace.model_validate(
        {
            "kind": "single",
            "layers": [
                {"role": "forward", "coordinates": [(1.0, 2.0)]},
                {"role": "single", "coordinates": [(3.0, 4.0)]},
            ],
            "meeting_node_coordinate": (5.0, 6.0),
        }
    )

    assert [layer.role for layer in trace.layers] == ["single"]
    assert trace.layers[0].coordinates == [(3.0, 4.0)]
    assert trace.meeting_node_coordinate is None


def test_search_trace_schema_requires_bidirectional_layers() -> None:
    with pytest.raises(ValidationError):
        SearchTrace.model_validate(
            {
                "kind": "bidirectional",
                "layers": [{"role": "forward", "coordinates": [(1.0, 2.0)]}],
            }
        )
