"""Run a small route-planning demo for BFS, UCS, and A*."""

from __future__ import annotations

from constraints import UserConstraints
from recommender import recommend_charging_stations


DEMO_LATITUDE = 22.714121
DEMO_LONGITUDE = 113.784724


def main() -> None:
    constraints = UserConstraints(
        max_candidates=5,
        max_search_radius_km=5,
        max_drive_time_min=30,
        current_soc=0.5,
        battery_capacity_kwh=60,
        min_arrival_soc=0.1,
    )
    for algorithm in ["bfs", "ucs", "astar"]:
        print(f"\n=== {algorithm.upper()} ===")
        result = recommend_charging_stations(
            DEMO_LATITUDE,
            DEMO_LONGITUDE,
            algorithm=algorithm,
            constraints=constraints,
            top_k=3,
        )
        print(
            result[
                [
                    "station_id",
                    "algorithm",
                    "distance_km",
                    "drive_time_min",
                    "expanded_nodes",
                    "runtime_seconds",
                    "arrival_soc",
                    "passed_constraints",
                    "reject_reason",
                ]
            ].to_string(index=False)
        )


if __name__ == "__main__":
    main()
