"""Precompute directed landmark distances for ALT A* search."""

from __future__ import annotations

import argparse
from pathlib import Path

import networkx as nx
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GRAPH_FILE = PROJECT_ROOT / "data" / "processed" / "shenzhen_drive_with_station_access.graphml"
DEFAULT_OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "landmark_distances.npz"
DEFAULT_LANDMARK_COUNT = 16


def build_weighted_digraph(graph: nx.MultiDiGraph) -> nx.DiGraph:
    weighted = nx.DiGraph()
    for node, attrs in graph.nodes(data=True):
        weighted.add_node(str(node), x=float(attrs["x"]), y=float(attrs["y"]))
    for u, v, attrs in graph.edges(data=True):
        weight = _edge_minutes(attrs)
        u = str(u)
        v = str(v)
        current = weighted.get_edge_data(u, v, default={}).get("weight")
        if current is None or weight < current:
            weighted.add_edge(u, v, weight=weight)
    return weighted


def build_landmark_selection_graph(graph: nx.DiGraph) -> nx.Graph:
    undirected = nx.Graph()
    for node, attrs in graph.nodes(data=True):
        undirected.add_node(node, **attrs)
    for u, v, attrs in graph.edges(data=True):
        weight = float(attrs.get("weight", 0.0))
        current = undirected.get_edge_data(u, v, default={}).get("weight")
        if current is None or weight < current:
            undirected.add_edge(u, v, weight=weight)
    largest_component = max(nx.connected_components(undirected), key=len)
    return undirected.subgraph(largest_component).copy()


def choose_landmarks(graph: nx.DiGraph, count: int = DEFAULT_LANDMARK_COUNT) -> list[str]:
    if count <= 0:
        raise ValueError("Landmark count must be positive.")
    selection_graph = build_landmark_selection_graph(graph)
    nodes = list(selection_graph.nodes)
    if count > len(nodes):
        raise ValueError(f"Landmark count {count} exceeds graph node count {len(nodes)}.")

    start = _node_closest_to_center(selection_graph)
    landmarks = [start]
    nearest_distances = _distances_from(selection_graph, start)

    while len(landmarks) < count:
        candidate = max(
            (node for node in nodes if node not in landmarks),
            key=lambda node: nearest_distances.get(node, float("inf")),
        )
        landmarks.append(candidate)
        candidate_distances = _distances_from(selection_graph, candidate)
        for node, distance in candidate_distances.items():
            if distance < nearest_distances.get(node, float("inf")):
                nearest_distances[node] = distance
    return landmarks


def _node_closest_to_center(graph: nx.Graph) -> str:
    nodes = list(graph.nodes)
    center_x = sum(float(graph.nodes[node]["x"]) for node in nodes) / len(nodes)
    center_y = sum(float(graph.nodes[node]["y"]) for node in nodes) / len(nodes)
    return min(
        nodes,
        key=lambda node: (float(graph.nodes[node]["x"]) - center_x) ** 2
        + (float(graph.nodes[node]["y"]) - center_y) ** 2,
    )


def _distances_from(graph: nx.Graph, source: str) -> dict[str, float]:
    return nx.single_source_dijkstra_path_length(graph, source, weight="weight")


def compute_landmark_distances(
    graph: nx.DiGraph,
    landmarks: list[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    nodes = np.array([str(node) for node in graph.nodes], dtype=np.str_)
    node_index = {node: index for index, node in enumerate(nodes)}
    forward_distances = np.full((len(landmarks), len(nodes)), np.inf, dtype=np.float32)
    reverse_distances = np.full((len(landmarks), len(nodes)), np.inf, dtype=np.float32)
    undirected_distances = np.full((len(landmarks), len(nodes)), np.inf, dtype=np.float32)
    reverse_graph = graph.reverse(copy=True)
    undirected_graph = build_landmark_selection_graph(graph)
    for landmark_index, landmark in enumerate(landmarks):
        lengths = nx.single_source_dijkstra_path_length(graph, landmark, weight="weight")
        for node, distance in lengths.items():
            forward_distances[landmark_index, node_index[node]] = float(distance)

        reverse_lengths = nx.single_source_dijkstra_path_length(reverse_graph, landmark, weight="weight")
        for node, distance in reverse_lengths.items():
            reverse_distances[landmark_index, node_index[node]] = float(distance)

        undirected_lengths = nx.single_source_dijkstra_path_length(undirected_graph, landmark, weight="weight")
        for node, distance in undirected_lengths.items():
            undirected_distances[landmark_index, node_index[node]] = float(distance)
    return nodes, forward_distances, reverse_distances, undirected_distances


def _edge_minutes(attrs: dict) -> float:
    try:
        return float(attrs["travel_time"]) / 60.0
    except (KeyError, TypeError, ValueError):
        length_m = float(attrs.get("length", 0.0))
        speed_kph = float(attrs.get("speed_kph", 40.0))
        return length_m / 1000.0 / max(speed_kph, 1.0) * 60.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build ALT landmark distance table.")
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_FILE)
    parser.add_argument("--landmark-count", type=int, default=DEFAULT_LANDMARK_COUNT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    graph = nx.read_graphml(args.graph, force_multigraph=True)
    weighted = build_weighted_digraph(graph)
    landmarks = choose_landmarks(weighted, args.landmark_count)
    nodes, forward_distances, reverse_distances, undirected_distances = compute_landmark_distances(weighted, landmarks)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        nodes=nodes,
        landmarks=np.array(landmarks, dtype=np.str_),
        forward_distances=forward_distances,
        reverse_distances=reverse_distances,
        undirected_distances=undirected_distances,
    )
    print(f"Saved landmark distances: {args.output}")
    print(f"Nodes: {len(nodes):,}")
    print(f"Landmarks: {', '.join(landmarks)}")


if __name__ == "__main__":
    main()
