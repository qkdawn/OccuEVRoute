from __future__ import annotations

import sys
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PLANNING_DIR = PROJECT_ROOT / "src" / "route_planning"
WAITING_PREDICTION_DIR = PROJECT_ROOT / "src" / "waiting_prediction"
if str(ROUTE_PLANNING_DIR) not in sys.path:
    sys.path.insert(0, str(ROUTE_PLANNING_DIR))
if str(WAITING_PREDICTION_DIR) not in sys.path:
    sys.path.insert(0, str(WAITING_PREDICTION_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.schemas import RecommendationItem, RecommendationResponse, RecommendationRequest, SearchTrace
from backend.services.recommendations import _balanced_rank_score, _build_ranking_orders, _sort_recommendations
from ch_index import CHEdge, CHIndex
from ch_preprocess import build_ch_index
from ch_search import _frontiers_cannot_improve, ch_bidirectional_dijkstra_search
from graph_loader import _StartAccessGraph
from search_algorithms import SearchContext, astar_search, bfs_search, bidirectional_bfs_search, run_search, ucs_search
from occupancy_predictor import DEFAULT_SIMULATION_WEEK_END, DEFAULT_SIMULATION_WEEK_START, historical_now


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


def _layer_edges(result, role: str) -> list[list[str]]:
    layer = next(layer for layer in result.search_trace.layers if layer.role == role)
    return layer.edges


def test_bfs_returns_single_trace_on_directed_graph() -> None:
    graph = _graph([("A", "B"), ("B", "C"), ("C", "D")])

    result = bfs_search(graph, "A", "D")

    assert result.algorithm == "bfs"
    assert result.path == ["A", "B", "C", "D"]
    assert result.search_trace.kind == "single"
    assert _layer_nodes(result, "single") == ["A", "B", "C", "D"]
    assert result.route_trace_path == ["A", "B", "C", "D"]
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
    assert result.search_trace.candidate_path_events[0].step == 3
    assert result.search_trace.candidate_path_events[0].path == ["A", "B", "C", "D"]


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
    assert result.route_trace_path == ["A", "B", "C"]
    assert result.search_trace.meeting_node is None


@pytest.mark.parametrize("search", [ucs_search, astar_search])
def test_single_frontier_candidate_path_uses_heap_top_not_latest_update(search) -> None:
    graph = _weighted_graph(
        [
            ("A", "C", 1.0),
            ("A", "B", 10.0),
            ("C", "D", 1.0),
            ("B", "D", 1.0),
        ]
    )

    result = search(graph, "A", "D")

    assert result.search_trace.candidate_path_events[0].step == 1
    assert result.search_trace.candidate_path_events[0].path == ["A", "C"]
    assert result.route_trace_path == ["A", "C", "D"]


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


def test_recommendation_request_accepts_ranking_metric() -> None:
    request = RecommendationRequest(lat=22.65, lng=114.05, ranking_metric="occupancy")

    assert request.ranking_metric == "occupancy"


def test_sort_recommendations_uses_selected_metric() -> None:
    results = pd.DataFrame(
        [
            {
                "station_id": 1,
                "drive_time_min": 8.0,
                "distance_km": 6.0,
                "predicted_occupancy_rate": 0.9,
                "arrival_soc": 0.8,
                "ml_rank_score": 17.0,
            },
            {
                "station_id": 2,
                "drive_time_min": 12.0,
                "distance_km": 4.0,
                "predicted_occupancy_rate": 0.1,
                "arrival_soc": 0.7,
                "ml_rank_score": 13.0,
            },
        ]
    )

    assert _sort_recommendations(results, "drive_time")["station_id"].tolist() == [1, 2]
    assert _sort_recommendations(results, "distance")["station_id"].tolist() == [2, 1]
    assert _sort_recommendations(results, "occupancy")["station_id"].tolist() == [2, 1]
    assert _sort_recommendations(results, "arrival_soc")["station_id"].tolist() == [1, 2]
    assert _sort_recommendations(results, "balanced")["station_id"].tolist() == [2, 1]


def test_build_ranking_orders_returns_all_metrics() -> None:
    results = pd.DataFrame(
        [
            {
                "station_id": 1,
                "drive_time_min": 8.0,
                "distance_km": 6.0,
                "predicted_occupancy_rate": 0.9,
                "arrival_soc": 0.8,
                "ml_rank_score": 17.0,
            },
            {
                "station_id": 2,
                "drive_time_min": 12.0,
                "distance_km": 4.0,
                "predicted_occupancy_rate": 0.1,
                "arrival_soc": 0.7,
                "ml_rank_score": 13.0,
            },
        ]
    )

    assert _build_ranking_orders(results, top_k=2) == {
        "balanced": [2, 1],
        "drive_time": [1, 2],
        "distance": [2, 1],
        "occupancy": [2, 1],
        "arrival_soc": [1, 2],
    }


def test_balanced_rank_score_normalizes_drive_time_and_penalizes_occupancy() -> None:
    row = pd.Series({"drive_time_min": 15.0, "predicted_occupancy_rate": 0.25})

    assert _balanced_rank_score(row, max_drive_time_min=30.0) == pytest.approx(0.75)


def test_recommendation_response_includes_ranking_orders() -> None:
    item = RecommendationItem(
        station_id=1,
        station_display_name="Charging Station 1",
        algorithm="astar",
        station_latitude=22.6,
        station_longitude=114.0,
        station_road_latitude=22.6,
        station_road_longitude=114.0,
        start_node_latitude=22.65,
        start_node_longitude=114.05,
        start_snap_distance_m=10.0,
        route_coordinates=[],
        search_trace={"kind": "single", "layers": [{"role": "single", "coordinates": [], "edges": []}]},
        distance_km=1.0,
        drive_time_min=2.0,
        road_snap_distance_m=3.0,
        expanded_nodes=4,
        runtime_seconds=0.01,
        charge_count=5,
        poi_total_count=6,
        poi_lifestyle_services_count=2,
        poi_business_residential_count=3,
        poi_food_beverage_count=1,
        arrival_soc=0.7,
        predicted_occupancy_rate=0.2,
        prediction_horizon_min=5.0,
        prediction_time="2023-02-06T08:05:00",
        prediction_source="historical_urbanev",
        ml_rank_score=4.0,
        passed_constraints=True,
        reject_reason="",
    )

    response = RecommendationResponse(
        recommendations=[item],
        ranking_orders={
            "balanced": [1],
            "drive_time": [1],
            "distance": [1],
            "occupancy": [1],
            "arrival_soc": [1],
        },
    )

    assert response.ranking_orders["balanced"] == [1]


def test_historical_now_preserves_weekday_and_time_inside_demo_week() -> None:
    simulated = historical_now("2026-05-24T14:37:12")

    assert DEFAULT_SIMULATION_WEEK_START <= simulated <= DEFAULT_SIMULATION_WEEK_END
    assert simulated == pd.Timestamp("2023-02-12 14:35:00")
    assert simulated.dayofweek == pd.Timestamp("2026-05-24").dayofweek
    assert simulated.hour == 14
    assert simulated.minute == 35


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


def test_ch_trace_edges_hide_shortcuts_but_route_still_unpacks_them() -> None:
    graph = _weighted_graph([("A", "B", 1.0), ("B", "C", 1.0)])
    index = CHIndex(
        ranks={"A": 1, "B": 0, "C": 2},
        upward={"A": [2]},
        reverse_upward={},
        edges={
            0: CHEdge(0, "A", "B", 1.0, 1000.0),
            1: CHEdge(1, "B", "C", 1.0, 1000.0),
            2: CHEdge(2, "A", "C", 2.0, 2000.0, "B", 0, 1),
        },
    )

    result = ch_bidirectional_dijkstra_search(graph, "A", "C", index)

    assert result.path == ["A", "B", "C"]
    assert result.route_trace_path == ["A", "C"]
    assert result.search_trace.candidate_path_events[0].step > 0
    assert result.search_trace.candidate_path_events[0].path == ["A", "C"]
    assert ["A", "B", "C"] not in _layer_edges(result, "forward")
    assert _layer_edges(result, "forward") == []


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
