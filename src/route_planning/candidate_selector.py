"""Candidate charging station selection before running graph search."""

from __future__ import annotations

import numpy as np
import pandas as pd


EARTH_RADIUS_KM = 6371.0088


def haversine_km(
    lat1: float,
    lon1: float,
    lat2,
    lon2,
):
    """Compute great-circle distance in kilometers."""
    lat1_rad = np.radians(lat1)
    lon1_rad = np.radians(lon1)
    lat2_rad = np.radians(lat2)
    lon2_rad = np.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def select_nearby_stations(
    stations: pd.DataFrame,
    user_latitude: float,
    user_longitude: float,
    max_search_radius_km: float = 10.0,
    max_candidates: int = 20,
) -> pd.DataFrame:
    """Return nearby station candidates sorted by straight-line distance."""
    candidates = stations.copy()
    candidates["straight_line_distance_km"] = haversine_km(
        user_latitude,
        user_longitude,
        candidates["latitude"],
        candidates["longitude"],
    )
    candidates = candidates[candidates["straight_line_distance_km"] <= max_search_radius_km]
    return candidates.sort_values("straight_line_distance_km").head(max_candidates).reset_index(drop=True)
