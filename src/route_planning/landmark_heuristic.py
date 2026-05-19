"""Load and evaluate ALT landmark heuristics."""

from __future__ import annotations

from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LANDMARK_FILE = PROJECT_ROOT / "data" / "processed" / "landmark_distances.npz"


class LandmarkHeuristic:
    def __init__(
        self,
        nodes: np.ndarray,
        landmarks: np.ndarray,
        forward_distances: np.ndarray,
        reverse_distances: np.ndarray | None = None,
        undirected_distances: np.ndarray | None = None,
    ):
        self.landmarks = [str(node) for node in landmarks.tolist()]
        self.forward_distances = forward_distances
        self.reverse_distances = reverse_distances
        self.undirected_distances = undirected_distances
        self.node_index = {str(node): index for index, node in enumerate(nodes.tolist())}

    @classmethod
    def load(cls, path: Path = DEFAULT_LANDMARK_FILE) -> "LandmarkHeuristic | None":
        if not path.exists():
            return None
        data = np.load(path, allow_pickle=True)
        if "forward_distances" in data and "reverse_distances" in data:
            undirected_distances = data["undirected_distances"] if "undirected_distances" in data else None
            return cls(
                data["nodes"],
                data["landmarks"],
                data["forward_distances"],
                data["reverse_distances"],
                undirected_distances,
            )
        return cls(data["nodes"], data["landmarks"], data["distances"])

    def estimate_minutes(self, node: str, goal: str) -> float | None:
        node_index = self.node_index.get(str(node))
        goal_index = self.node_index.get(str(goal))
        if node_index is None or goal_index is None:
            return None

        forward_node = self.forward_distances[:, node_index]
        forward_goal = self.forward_distances[:, goal_index]
        estimates = []

        forward_valid = np.isfinite(forward_node) & np.isfinite(forward_goal)
        if np.any(forward_valid):
            estimates.append(forward_goal[forward_valid] - forward_node[forward_valid])

        if self.reverse_distances is not None:
            reverse_node = self.reverse_distances[:, node_index]
            reverse_goal = self.reverse_distances[:, goal_index]
            reverse_valid = np.isfinite(reverse_node) & np.isfinite(reverse_goal)
            if np.any(reverse_valid):
                estimates.append(reverse_node[reverse_valid] - reverse_goal[reverse_valid])
        elif np.any(forward_valid):
            estimates.append(forward_node[forward_valid] - forward_goal[forward_valid])

        if not estimates:
            return self._undirected_estimate_minutes(node_index, goal_index)
        return max(0.0, float(np.max(np.concatenate(estimates))))

    def _undirected_estimate_minutes(self, node_index: int, goal_index: int) -> float | None:
        if self.undirected_distances is None:
            return None
        node_distances = self.undirected_distances[:, node_index]
        goal_distances = self.undirected_distances[:, goal_index]
        valid = np.isfinite(node_distances) & np.isfinite(goal_distances)
        if not np.any(valid):
            return None
        return float(np.max(np.abs(goal_distances[valid] - node_distances[valid])))
