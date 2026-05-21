"""Shared graph edge and path metrics for route planning algorithms."""

from __future__ import annotations


DEFAULT_SPEED_KPH = 40.0


def safe_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def best_edge_attrs(graph, u: str, v: str) -> dict:
    edge_data = graph.get_edge_data(u, v, default={})
    values = list(edge_data.values()) if isinstance(edge_data, dict) else []
    if not values:
        return {}
    return min(values, key=lambda attrs: safe_float(attrs.get("travel_time"), float("inf")))


def edge_metrics(graph, u: str, v: str, default_speed_kph: float = DEFAULT_SPEED_KPH) -> tuple[float, float]:
    attrs = best_edge_attrs(graph, u, v)
    if not attrs:
        return 0.0, 0.0
    length_m = safe_float(attrs.get("length"), 0.0)
    travel_time_s = safe_float(
        attrs.get("travel_time"),
        length_m / 1000.0 / default_speed_kph * 3600.0,
    )
    return length_m, travel_time_s


def path_metrics(graph, path: list[str], default_speed_kph: float = DEFAULT_SPEED_KPH) -> tuple[float, float]:
    total_length_m = 0.0
    total_time_s = 0.0
    for u, v in zip(path, path[1:]):
        length_m, travel_time_s = edge_metrics(graph, u, v, default_speed_kph)
        total_length_m += length_m
        total_time_s += travel_time_s
    return total_length_m / 1000.0, total_time_s / 60.0
