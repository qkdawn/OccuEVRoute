"""Build a course-friendly contraction hierarchy index for the road graph."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from ch_index import CHEdge, CHIndex, DEFAULT_CH_INDEX_FILE
from graph_loader import DEFAULT_GRAPH_FILE, _restore_graphml_edge_types
from search_algorithms import DEFAULT_HEURISTIC_SPEED_KPH


MAX_SHORTCUT_PAIRS_PER_NODE = 48


@dataclass(frozen=True)
class WeightedEdge:
    edge_id: int
    weight_min: float


class CHBuilder:
    def __init__(self, graph):
        self.ranks = compute_node_ranks(graph)
        self.edges: dict[int, CHEdge] = {}
        self.adjacency: dict[str, dict[str, WeightedEdge]] = {str(node): {} for node in graph.nodes}
        self.reverse: dict[str, dict[str, WeightedEdge]] = {str(node): {} for node in graph.nodes}
        self.next_edge_id = 0
        self._load_base_edges(graph)

    def build(self) -> CHIndex:
        for node, rank in sorted(self.ranks.items(), key=lambda item: item[1]):
            self._contract_node(node, rank)
        upward: dict[str, list[int]] = {}
        reverse_upward: dict[str, list[int]] = {}
        for edge in self.edges.values():
            upward.setdefault(edge.u, []).append(edge.id)
            reverse_upward.setdefault(edge.v, []).append(edge.id)
        return CHIndex(
            ranks=self.ranks,
            upward={node: sorted(edges, key=lambda edge_id: self.edges[edge_id].v) for node, edges in upward.items()},
            reverse_upward={
                node: sorted(edges, key=lambda edge_id: self.edges[edge_id].u) for node, edges in reverse_upward.items()
            },
            edges=self.edges,
        )

    def _load_base_edges(self, graph) -> None:
        for u, v, attrs in graph.edges(data=True):
            u = str(u)
            v = str(v)
            weight_min = _edge_minutes(attrs)
            length_m = _edge_length_m(attrs)
            self._add_or_replace_edge(u, v, weight_min, length_m)

    def _contract_node(self, node: str, rank: int) -> None:
        incoming = [
            (u, edge)
            for u, edge in list(self.reverse.get(node, {}).items())
            if self.ranks[u] > rank
        ]
        outgoing = [
            (w, edge)
            for w, edge in list(self.adjacency.get(node, {}).items())
            if self.ranks[w] > rank
        ]
        if len(incoming) * len(outgoing) > MAX_SHORTCUT_PAIRS_PER_NODE:
            return
        for u, in_edge in incoming:
            for w, out_edge in outgoing:
                if u == w:
                    continue
                shortcut_weight = in_edge.weight_min + out_edge.weight_min
                current = self.adjacency.get(u, {}).get(w)
                if current is not None and current.weight_min <= shortcut_weight:
                    continue
                in_full = self.edges[in_edge.edge_id]
                out_full = self.edges[out_edge.edge_id]
                self._add_or_replace_edge(
                    u,
                    w,
                    shortcut_weight,
                    in_full.length_m + out_full.length_m,
                    via_node=node,
                    left_edge_id=in_edge.edge_id,
                    right_edge_id=out_edge.edge_id,
                )

    def _add_or_replace_edge(
        self,
        u: str,
        v: str,
        weight_min: float,
        length_m: float,
        via_node: str | None = None,
        left_edge_id: int | None = None,
        right_edge_id: int | None = None,
    ) -> int:
        current = self.adjacency.setdefault(u, {}).get(v)
        if current is not None and current.weight_min <= weight_min:
            return current.edge_id
        edge_id = self.next_edge_id
        self.next_edge_id += 1
        edge = CHEdge(edge_id, u, v, weight_min, length_m, via_node, left_edge_id, right_edge_id)
        self.edges[edge_id] = edge
        self.adjacency.setdefault(u, {})[v] = WeightedEdge(edge_id, weight_min)
        self.reverse.setdefault(v, {})[u] = WeightedEdge(edge_id, weight_min)
        return edge_id


def build_ch_index(graph) -> CHIndex:
    return CHBuilder(graph).build()


def compute_node_ranks(graph) -> dict[str, int]:
    nodes = [str(node) for node in graph.nodes]
    ordered = sorted(
        nodes,
        key=lambda node: (
            int(graph.in_degree(node)) + int(graph.out_degree(node)),
            int(graph.in_degree(node)) * int(graph.out_degree(node)),
            _node_coordinate(graph, node, "x"),
            _node_coordinate(graph, node, "y"),
            node,
        ),
    )
    return {node: rank for rank, node in enumerate(ordered)}


def _node_coordinate(graph, node: str, key: str) -> float:
    try:
        return float(graph.nodes[node].get(key, 0.0))
    except (TypeError, ValueError):
        return 0.0


def _edge_minutes(attrs: dict) -> float:
    try:
        return float(attrs["travel_time"]) / 60.0
    except (KeyError, TypeError, ValueError):
        length_m = _edge_length_m(attrs)
        return length_m / 1000.0 / DEFAULT_HEURISTIC_SPEED_KPH * 60.0


def _edge_length_m(attrs: dict) -> float:
    try:
        return float(attrs["length"])
    except (KeyError, TypeError, ValueError):
        return 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a contraction hierarchy index for route planning.")
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_CH_INDEX_FILE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    graph = nx.read_graphml(args.graph, force_multigraph=True)
    _restore_graphml_edge_types(graph)
    index = build_ch_index(graph)
    index.save(args.output)
    shortcut_count = sum(1 for edge in index.edges.values() if edge.is_shortcut)
    print(f"Saved CH index: {args.output}")
    print(f"Nodes: {len(index.ranks):,}")
    print(f"Edges: {len(index.edges):,}")
    print(f"Shortcuts: {shortcut_count:,}")


if __name__ == "__main__":
    main()
