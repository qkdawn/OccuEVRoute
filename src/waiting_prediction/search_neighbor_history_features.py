"""Search historical nearby-station features for occupancy XGBoost."""

from __future__ import annotations

import argparse
from itertools import combinations
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.neighbors import BallTree
from xgboost import XGBRegressor

from plot_shap_occupancy import DEFAULT_STATION_DIR
from plot_shap_occupancy import apply_station_profiles, fit_station_profiles
from run_occupancy_poi_experiment import (
    BASE_FEATURES,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_POI_FILE,
    DEFAULT_WEATHER_FILE,
    build_experiment_frame,
    time_split,
)


EARTH_RADIUS_M = 6_371_008.8
COMPACT_POI_FEATURES = [
    "poi_lifestyle_services_count",
    "poi_lifestyle_ratio",
    "poi_business_residential_ratio",
]
BASE_NON_NEIGHBOR_FEATURES = [
    feature for feature in BASE_FEATURES if feature != "humidity"
] + COMPACT_POI_FEATURES
NEIGHBOR_PROFILE_FEATURES = [
    "neighbor_count",
    "neighbor_avg_distance_m",
    "neighbor_avg_station_occupancy",
    "neighbor_max_station_occupancy",
    "neighbor_avg_peak_occupancy",
    "neighbor_avg_duration",
    "neighbor_avg_charge_count",
    "neighbor_avg_same_hour_occupancy",
    "neighbor_avg_same_weekday_hour_occupancy",
]
DEFAULT_RADII_M = [1000.0, 3000.0, 5000.0]
DEFAULT_K_VALUES = [3, 5, 10]


def make_model(random_seed: int) -> XGBRegressor:
    return XGBRegressor(
        objective="reg:squarederror",
        n_estimators=400,
        max_depth=5,
        learning_rate=0.04,
        subsample=0.85,
        colsample_bytree=0.85,
        random_state=random_seed,
        n_jobs=-1,
    )


def load_or_build_frame(args: argparse.Namespace) -> pd.DataFrame:
    if args.cache_file.exists() and not args.rebuild_cache:
        return pd.read_pickle(args.cache_file)
    df = build_experiment_frame(args)
    args.cache_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_pickle(args.cache_file)
    return df


def load_station_coordinates(station_dir: Path) -> pd.DataFrame:
    station_info = pd.read_csv(station_dir / "features" / "station_inf.csv")
    required = {"station_id", "latitude", "longitude"}
    missing = required - set(station_info.columns)
    if missing:
        raise ValueError(f"Station info file is missing columns: {sorted(missing)}")
    return (
        station_info[["station_id", "latitude", "longitude"]]
        .drop_duplicates("station_id")
        .sort_values("station_id")
        .reset_index(drop=True)
    )


def neighbor_map_by_radius(stations: pd.DataFrame, radius_m: float) -> dict[int, list[tuple[int, float]]]:
    coords = np.radians(stations[["latitude", "longitude"]].to_numpy(dtype=float))
    station_ids = stations["station_id"].astype(int).to_numpy()
    tree = BallTree(coords, metric="haversine")
    indices, distances = tree.query_radius(
        coords,
        r=radius_m / EARTH_RADIUS_M,
        return_distance=True,
        sort_results=True,
    )
    neighbors: dict[int, list[tuple[int, float]]] = {}
    for station_id, row_indices, row_distances in zip(station_ids, indices, distances):
        pairs = []
        for index, distance in zip(row_indices, row_distances):
            other_id = int(station_ids[index])
            if other_id == int(station_id):
                continue
            pairs.append((other_id, float(distance * EARTH_RADIUS_M)))
        neighbors[int(station_id)] = pairs
    return neighbors


def neighbor_map_by_k(stations: pd.DataFrame, k: int) -> dict[int, list[tuple[int, float]]]:
    coords = np.radians(stations[["latitude", "longitude"]].to_numpy(dtype=float))
    station_ids = stations["station_id"].astype(int).to_numpy()
    tree = BallTree(coords, metric="haversine")
    distances, indices = tree.query(coords, k=min(k + 1, len(stations)), sort_results=True)
    neighbors: dict[int, list[tuple[int, float]]] = {}
    for station_id, row_indices, row_distances in zip(station_ids, indices, distances):
        pairs = []
        for index, distance in zip(row_indices, row_distances):
            other_id = int(station_ids[index])
            if other_id == int(station_id):
                continue
            pairs.append((other_id, float(distance * EARTH_RADIUS_M)))
            if len(pairs) >= k:
                break
        neighbors[int(station_id)] = pairs
    return neighbors


def station_profiles(train_df: pd.DataFrame) -> dict[str, object]:
    peak_mask = (train_df["is_morning_peak"] == 1) | (train_df["is_evening_peak"] == 1)
    return {
        "global_occupancy": float(train_df["occupancy_rate"].mean()),
        "global_duration": float(train_df["duration"].mean()),
        "global_charge_count": float(train_df["charge_count"].mean()),
        "global_peak": float(train_df.loc[peak_mask, "occupancy_rate"].mean()),
        "global_hour": train_df.groupby("hour")["occupancy_rate"].mean(),
        "global_weekday_hour": train_df.groupby(["weekday", "hour"])["occupancy_rate"].mean(),
        "station_occupancy": train_df.groupby("station_id")["occupancy_rate"].mean(),
        "station_duration": train_df.groupby("station_id")["duration"].mean(),
        "station_charge_count": train_df.groupby("station_id")["charge_count"].mean(),
        "station_peak": train_df.loc[peak_mask].groupby("station_id")["occupancy_rate"].mean(),
        "station_hour": train_df.groupby(["station_id", "hour"])["occupancy_rate"].mean(),
        "station_weekday_hour": train_df.groupby(["station_id", "weekday", "hour"])[
            "occupancy_rate"
        ].mean(),
    }


def _profile_value(series: pd.Series, key: object, fallback: float) -> float:
    value = series.get(key, np.nan)
    if pd.isna(value):
        return fallback
    return float(value)


def _neighbor_mean(
    neighbors: list[tuple[int, float]],
    value_getter,
    fallback: float,
) -> float:
    if not neighbors:
        return fallback
    values = [value_getter(station_id) for station_id, _ in neighbors]
    values = [value for value in values if not pd.isna(value)]
    if not values:
        return fallback
    return float(np.mean(values))


def _neighbor_max(
    neighbors: list[tuple[int, float]],
    value_getter,
    fallback: float,
) -> float:
    if not neighbors:
        return fallback
    values = [value_getter(station_id) for station_id, _ in neighbors]
    values = [value for value in values if not pd.isna(value)]
    if not values:
        return fallback
    return float(np.max(values))


def add_neighbor_features(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    neighbors: dict[int, list[tuple[int, float]]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    profiles = station_profiles(train_df)

    static_rows = []
    for station_id in sorted(set(train_df["station_id"]).union(test_df["station_id"])):
        station_neighbors = neighbors.get(int(station_id), [])
        distances = [distance for _, distance in station_neighbors]
        row = {
            "station_id": int(station_id),
            "neighbor_count": len(station_neighbors),
            "neighbor_avg_distance_m": float(np.mean(distances)) if distances else 0.0,
            "neighbor_avg_station_occupancy": _neighbor_mean(
                station_neighbors,
                lambda other_id: _profile_value(
                    profiles["station_occupancy"], other_id, profiles["global_occupancy"]
                ),
                profiles["global_occupancy"],
            ),
            "neighbor_max_station_occupancy": _neighbor_max(
                station_neighbors,
                lambda other_id: _profile_value(
                    profiles["station_occupancy"], other_id, profiles["global_occupancy"]
                ),
                profiles["global_occupancy"],
            ),
            "neighbor_avg_peak_occupancy": _neighbor_mean(
                station_neighbors,
                lambda other_id: _profile_value(
                    profiles["station_peak"], other_id, profiles["global_peak"]
                ),
                profiles["global_peak"],
            ),
            "neighbor_avg_duration": _neighbor_mean(
                station_neighbors,
                lambda other_id: _profile_value(
                    profiles["station_duration"], other_id, profiles["global_duration"]
                ),
                profiles["global_duration"],
            ),
            "neighbor_avg_charge_count": _neighbor_mean(
                station_neighbors,
                lambda other_id: _profile_value(
                    profiles["station_charge_count"], other_id, profiles["global_charge_count"]
                ),
                profiles["global_charge_count"],
            ),
        }
        static_rows.append(row)
    static_features = pd.DataFrame(static_rows)

    def add_time_neighbor_features(df: pd.DataFrame) -> pd.DataFrame:
        out = df.merge(static_features, on="station_id", how="left")
        hour_cache: dict[tuple[int, int], float] = {}
        weekday_hour_cache: dict[tuple[int, int, int], float] = {}

        def same_hour(row: pd.Series) -> float:
            station_id = int(row["station_id"])
            hour = int(row["hour"])
            key = (station_id, hour)
            if key not in hour_cache:
                fallback = _profile_value(profiles["global_hour"], hour, profiles["global_occupancy"])
                hour_cache[key] = _neighbor_mean(
                    neighbors.get(station_id, []),
                    lambda other_id: _profile_value(
                        profiles["station_hour"], (other_id, hour), fallback
                    ),
                    fallback,
                )
            return hour_cache[key]

        def same_weekday_hour(row: pd.Series) -> float:
            station_id = int(row["station_id"])
            weekday = int(row["weekday"])
            hour = int(row["hour"])
            key = (station_id, weekday, hour)
            if key not in weekday_hour_cache:
                fallback = _profile_value(
                    profiles["global_weekday_hour"],
                    (weekday, hour),
                    profiles["global_occupancy"],
                )
                weekday_hour_cache[key] = _neighbor_mean(
                    neighbors.get(station_id, []),
                    lambda other_id: _profile_value(
                        profiles["station_weekday_hour"], (other_id, weekday, hour), fallback
                    ),
                    fallback,
                )
            return weekday_hour_cache[key]

        out["neighbor_avg_same_hour_occupancy"] = out.apply(same_hour, axis=1)
        out["neighbor_avg_same_weekday_hour_occupancy"] = out.apply(
            same_weekday_hour, axis=1
        )
        return out

    return add_time_neighbor_features(train_df), add_time_neighbor_features(test_df)


def evaluate(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    features: list[str],
    random_seed: int,
) -> dict[str, float]:
    start = time.perf_counter()
    profiles = fit_station_profiles(train_df)
    train_df = apply_station_profiles(train_df, profiles)
    test_df = apply_station_profiles(test_df, profiles)
    model = make_model(random_seed)
    model.fit(train_df[features], train_df["occupancy_rate"])
    pred = model.predict(test_df[features])
    return {
        "mae": float(mean_absolute_error(test_df["occupancy_rate"], pred)),
        "r2": float(r2_score(test_df["occupancy_rate"], pred)),
        "elapsed_seconds": time.perf_counter() - start,
    }


def feature_subsets(max_features: int) -> list[tuple[str, ...]]:
    subsets = []
    for size in range(max_features + 1):
        subsets.extend(combinations(NEIGHBOR_PROFILE_FEATURES, size))
    return subsets


def parse_float_list(value: str) -> list[float]:
    return [float(item) for item in value.split(",") if item.strip()]


def parse_int_list(value: str) -> list[int]:
    return [int(item) for item in value.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search historical neighbor station features.")
    parser.add_argument("--station-dir", type=Path, default=DEFAULT_STATION_DIR)
    parser.add_argument("--weather-file", type=Path, default=DEFAULT_WEATHER_FILE)
    parser.add_argument("--poi-file", type=Path, default=DEFAULT_POI_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--cache-file",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "occupancy_neighbor_training_frame.pkl",
    )
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--rows-per-station", type=int, default=250)
    parser.add_argument("--max-stations", type=int, default=None)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--radii-m", type=parse_float_list, default=DEFAULT_RADII_M)
    parser.add_argument("--k-values", type=parse_int_list, default=DEFAULT_K_VALUES)
    parser.add_argument("--max-neighbor-features", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = load_or_build_frame(args)
    train_df, test_df = time_split(df, args.test_size)
    stations = load_station_coordinates(args.station_dir)
    scenarios: list[tuple[str, dict[int, list[tuple[int, float]]]]] = []
    for radius_m in args.radii_m:
        scenarios.append((f"radius_{int(radius_m)}m", neighbor_map_by_radius(stations, radius_m)))
    for k in args.k_values:
        scenarios.append((f"nearest_{k}", neighbor_map_by_k(stations, k)))

    rows = []
    subsets = feature_subsets(args.max_neighbor_features)
    for scenario_name, neighbors in scenarios:
        scenario_train, scenario_test = add_neighbor_features(train_df, test_df, neighbors)
        for neighbor_features in subsets:
            features = [*BASE_NON_NEIGHBOR_FEATURES, *neighbor_features]
            result = evaluate(scenario_train, scenario_test, features, args.random_seed)
            row = {
                "neighbor_scenario": scenario_name,
                "neighbor_feature_count": len(neighbor_features),
                "neighbor_features": "|".join(neighbor_features),
                "features": len(features),
                "feature_list": "|".join(features),
                **result,
            }
            rows.append(row)
            print(
                f"{scenario_name} neighbor={len(neighbor_features)} "
                f"{row['neighbor_features'] or 'none'}: "
                f"R2={row['r2']:.6f}, MAE={row['mae']:.6f}",
                flush=True,
            )

    results = pd.DataFrame(rows).sort_values(["r2", "mae"], ascending=[False, True])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "occupancy_neighbor_history_search.csv"
    results.to_csv(output_path, index=False)
    best = results.iloc[0]
    print(f"Saved neighbor history search: {output_path}")
    print(
        f"Best R2={best['r2']:.6f}, MAE={best['mae']:.6f}, "
        f"neighbor_features={best['neighbor_feature_count']}, features={best['features']}"
    )
    print(best["feature_list"])


if __name__ == "__main__":
    main()
