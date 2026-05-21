"""Contraction hierarchy index for travel-time shortest-path queries."""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CH_INDEX_FILE = PROJECT_ROOT / "data" / "processed" / "ch_index.pkl"


@dataclass(frozen=True)
class CHEdge:
    id: int
    u: str
    v: str
    weight_min: float
    length_m: float
    via_node: str | None = None
    left_edge_id: int | None = None
    right_edge_id: int | None = None

    @property
    def is_shortcut(self) -> bool:
        return self.via_node is not None


@dataclass
class CHIndex:
    ranks: dict[str, int]
    upward: dict[str, list[int]]
    reverse_upward: dict[str, list[int]]
    edges: dict[int, CHEdge]

    def save(self, path: Path = DEFAULT_CH_INDEX_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            pickle.dump(self, handle, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path: Path = DEFAULT_CH_INDEX_FILE) -> "CHIndex":
        if not path.exists():
            raise FileNotFoundError(
                f"CH index not found: {path}. Run src/route_planning/ch_preprocess.py before using "
                "ch_bidirectional_dijkstra."
            )
        with path.open("rb") as handle:
            value = pickle.load(handle)
        if not isinstance(value, cls):
            raise ValueError(f"Invalid CH index file: {path}")
        return value

    def contains(self, node: str) -> bool:
        return node in self.ranks

    def edge(self, edge_id: int) -> CHEdge:
        return self.edges[edge_id]

    def unpack_edge_nodes(self, edge_id: int) -> list[str]:
        edge = self.edge(edge_id)
        if not edge.is_shortcut:
            return [edge.u, edge.v]
        if edge.left_edge_id is None or edge.right_edge_id is None:
            raise ValueError(f"Shortcut edge {edge_id} is missing child edges.")
        left = self.unpack_edge_nodes(edge.left_edge_id)
        right = self.unpack_edge_nodes(edge.right_edge_id)
        return left + right[1:]

    def unpack_edge_metrics(self, edge_id: int) -> tuple[float, float]:
        edge = self.edge(edge_id)
        if not edge.is_shortcut:
            return edge.length_m, edge.weight_min
        if edge.left_edge_id is None or edge.right_edge_id is None:
            raise ValueError(f"Shortcut edge {edge_id} is missing child edges.")
        left_length, left_minutes = self.unpack_edge_metrics(edge.left_edge_id)
        right_length, right_minutes = self.unpack_edge_metrics(edge.right_edge_id)
        return left_length + right_length, left_minutes + right_minutes
