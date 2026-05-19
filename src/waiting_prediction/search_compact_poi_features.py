"""Search compact POI feature subsets for occupancy XGBoost."""

from __future__ import annotations

import argparse
from itertools import combinations
import time
from pathlib import Path

import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score
from xgboost import XGBRegressor

from plot_shap_occupancy import apply_station_profiles, fit_station_profiles
from run_occupancy_poi_experiment import (
    BASE_FEATURES,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_POI_FILE,
    DEFAULT_STATION_DIR,
    DEFAULT_WEATHER_FILE,
    PEAK_FEATURES,
    POI_COUNT_FEATURES,
    POI_RATIO_FEATURES,
    build_experiment_frame,
    time_split,
)


POI_FEATURES = [*POI_COUNT_FEATURES, *POI_RATIO_FEATURES]
NON_POI_REMOVAL_SETS = {
    "all_non_poi": set(),
    "no_humidity": {"humidity"},
    "no_evening_peak": {"is_evening_peak"},
    "no_humidity_evening_peak": {"humidity", "is_evening_peak"},
}


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


def poi_subsets(max_poi_features: int) -> list[tuple[str, ...]]:
    subsets: list[tuple[str, ...]] = []
    for size in range(max_poi_features + 1):
        subsets.extend(combinations(POI_FEATURES, size))
    return subsets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search compact POI feature subsets.")
    parser.add_argument("--station-dir", type=Path, default=DEFAULT_STATION_DIR)
    parser.add_argument("--weather-file", type=Path, default=DEFAULT_WEATHER_FILE)
    parser.add_argument("--poi-file", type=Path, default=DEFAULT_POI_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--cache-file",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "occupancy_compact_poi_training_frame.pkl",
    )
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--rows-per-station", type=int, default=250)
    parser.add_argument("--max-stations", type=int, default=None)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--max-poi-features", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = load_or_build_frame(args)
    train_df, test_df = time_split(df, args.test_size)

    rows = []
    base_non_poi_features = [*BASE_FEATURES, *PEAK_FEATURES]
    for removal_name, removed in NON_POI_REMOVAL_SETS.items():
        non_poi_features = [feature for feature in base_non_poi_features if feature not in removed]
        for poi_features in poi_subsets(args.max_poi_features):
            features = [*non_poi_features, *poi_features]
            result = evaluate(train_df, test_df, features, args.random_seed)
            row = {
                "non_poi_variant": removal_name,
                "removed_non_poi": "|".join(sorted(removed)),
                "poi_feature_count": len(poi_features),
                "poi_features": "|".join(poi_features),
                "features": len(features),
                "feature_list": "|".join(features),
                **result,
            }
            rows.append(row)
            print(
                f"{removal_name} poi={len(poi_features)} "
                f"{row['poi_features'] or 'none'}: "
                f"R2={row['r2']:.6f}, MAE={row['mae']:.6f}",
                flush=True,
            )

    results = pd.DataFrame(rows).sort_values(
        ["r2", "mae"], ascending=[False, True]
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "occupancy_compact_poi_search.csv"
    results.to_csv(output_path, index=False)
    best = results.iloc[0]
    print(f"Saved compact POI search: {output_path}")
    print(
        f"Best R2={best['r2']:.6f}, MAE={best['mae']:.6f}, "
        f"POI={best['poi_feature_count']}, features={best['features']}"
    )
    print(best["feature_list"])


if __name__ == "__main__":
    main()
