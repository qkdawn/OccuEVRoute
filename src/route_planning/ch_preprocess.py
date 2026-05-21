"""Build a course-friendly contraction hierarchy index for the road graph."""

from __future__ import annotations

import argparse
import heapq
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from ch_index import CHEdge, CHIndex, DEFAULT_CH_INDEX_FILE
from graph_metrics import DEFAULT_SPEED_KPH, safe_float
from graph_loader import DEFAULT_GRAPH_FILE, _restore_graphml_edge_types


DEFAULT_WITNESS_SETTLED_LIMIT = 240
DEFAULT_PROGRESS_INTERVAL = 5000


@dataclass(frozen=True)
class WeightedEdge:
    edge_id: int
    weight_min: float


class CHBuilder:
    def __init__(
        self,
        graph,
        witness_settled_limit: int = DEFAULT_WITNESS_SETTLED_LIMIT,
        progress_interval: int = DEFAULT_PROGRESS_INTERVAL,
    ):
        self.graph = graph
        self.ranks: dict[str, int] = {}
        self.uncontracted = {str(node) for node in graph.nodes}
        self.edges: dict[int, CHEdge] = {}
        self.adjacency: dict[str, dict[str, WeightedEdge]] = {str(node): {} for node in graph.nodes}
        self.reverse: dict[str, dict[str, WeightedEdge]] = {str(node): {} for node in graph.nodes}
        self.next_edge_id = 0
        self.witness_settled_limit = witness_settled_limit
        self.progress_interval = progress_interval
        self._load_base_edges(graph)

    def build(self) -> CHIndex:
        total_nodes = len(self.uncontracted)
        heap = [(self._importance(node), self._tie_breaker(node), node) for node in self.uncontracted]
        heapq.heapify(heap)
        while self.uncontracted:
            importance, _, node = heapq.heappop(heap)
            if node not in self.uncontracted:
                continue
            current_importance = self._importance(node)
            if current_importance > importance and heap and current_importance > heap[0][0]:
                heapq.heappush(heap, (current_importance, self._tie_breaker(node), node))
                continue
            rank = len(self.ranks)
            self.ranks[node] = rank
            self._contract_node(node)
            self.uncontracted.remove(node)
            index = len(self.ranks)
            if self.progress_interval and index % self.progress_interval == 0:
                shortcut_count = sum(1 for edge in self.edges.values() if edge.is_shortcut)
                print(
                    f"contracted {index:,}/{total_nodes:,} nodes, "
                    f"edges={len(self.edges):,}, shortcuts={shortcut_count:,}",
                    flush=True,
                )
        upward: dict[str, list[int]] = {}
        reverse_upward: dict[str, list[int]] = {}
        for edge in self.edges.values():
            if self.ranks[edge.u] < self.ranks[edge.v]:
                upward.setdefault(edge.u, []).append(edge.id)
            elif self.ranks[edge.u] > self.ranks[edge.v]:
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

    def _contract_node(self, node: str) -> None:
        incoming = [
            (u, edge)
            for u, edge in list(self.reverse.get(node, {}).items())
            if u in self.uncontracted and u != node
        ]
        outgoing = [
            (w, edge)
            for w, edge in list(self.adjacency.get(node, {}).items())
            if w in self.uncontracted and w != node
        ]
        for u, in_edge in incoming:
            for w, out_edge in outgoing:
                if u == w:
                    continue
                shortcut_weight = in_edge.weight_min + out_edge.weight_min
                if self._has_witness_path(u, w, node, shortcut_weight):
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

    def _has_witness_path(self, start: str, goal: str, forbidden: str, max_cost: float) -> bool:
        heap = [(0.0, start)]
        best = {start: 0.0}
        settled = 0
        while heap and settled < self.witness_settled_limit:
            cost, node = heapq.heappop(heap)
            if cost > best.get(node, float("inf")):
                continue
            if cost > max_cost:
                return False
            if node == goal:
                return True
            settled += 1
            for neighbor, edge in self.adjacency.get(node, {}).items():
                if neighbor == forbidden or neighbor not in self.uncontracted:
                    continue
                new_cost = cost + edge.weight_min
                if new_cost <= max_cost and new_cost < best.get(neighbor, float("inf")):
                    best[neighbor] = new_cost
                    heapq.heappush(heap, (new_cost, neighbor))
        return False

    def _importance(self, node: str) -> tuple[int, int, int]:
        incoming = sum(1 for predecessor in self.reverse.get(node, {}) if predecessor in self.uncontracted)
        outgoing = sum(1 for successor in self.adjacency.get(node, {}) if successor in self.uncontracted)
        shortcut_upper_bound = incoming * outgoing
        edge_difference = shortcut_upper_bound - incoming - outgoing
        return edge_difference, shortcut_upper_bound, incoming + outgoing

    def _tie_breaker(self, node: str) -> tuple[float, float, str]:
        return _node_coordinate(self.graph, node, "x"), _node_coordinate(self.graph, node, "y"), node

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


def build_ch_index(
    graph,
    witness_settled_limit: int = DEFAULT_WITNESS_SETTLED_LIMIT,
    progress_interval: int = 0,
) -> CHIndex:
    return CHBuilder(graph, witness_settled_limit, progress_interval).build()


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
    length_m = _edge_length_m(attrs)
    travel_time_s = safe_float(
        attrs.get("travel_time"),
        length_m / 1000.0 / DEFAULT_SPEED_KPH * 3600.0,
    )
    return travel_time_s / 60.0


def _edge_length_m(attrs: dict) -> float:
    return safe_float(attrs.get("length"), 0.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a contraction hierarchy index for route planning.")
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_CH_INDEX_FILE)
    parser.add_argument("--witness-settled-limit", type=int, default=DEFAULT_WITNESS_SETTLED_LIMIT)
    parser.add_argument("--progress-interval", type=int, default=DEFAULT_PROGRESS_INTERVAL)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    graph = nx.read_graphml(args.graph, force_multigraph=True)
    _restore_graphml_edge_types(graph)
    index = build_ch_index(graph, args.witness_settled_limit, args.progress_interval)
    index.save(args.output)
    shortcut_count = sum(1 for edge in index.edges.values() if edge.is_shortcut)
    print(f"Saved CH index: {args.output}")
    print(f"Nodes: {len(index.ranks):,}")
    print(f"Edges: {len(index.edges):,}")
    print(f"Shortcuts: {shortcut_count:,}")


if __name__ == "__main__":
    main()
