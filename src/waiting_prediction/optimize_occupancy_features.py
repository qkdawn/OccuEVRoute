"""Greedy feature reduction for occupancy XGBoost models."""

from __future__ import annotations

import argparse
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


ALL_FEATURES = [
    *BASE_FEATURES,
    *PEAK_FEATURES,
    *POI_COUNT_FEATURES,
    *POI_RATIO_FEATURES,
]


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


def evaluate_features(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    features: list[str],
    random_seed: int,
) -> dict[str, object]:
    start = time.perf_counter()
    profiles = fit_station_profiles(train_df)
    train_with_profiles = apply_station_profiles(train_df, profiles)
    test_with_profiles = apply_station_profiles(test_df, profiles)

    model = make_model(random_seed)
    model.fit(train_with_profiles[features], train_with_profiles["occupancy_rate"])
    pred = model.predict(test_with_profiles[features])
    return {
        "features": len(features),
        "feature_list": "|".join(features),
        "removed_feature": "",
        "mae": float(mean_absolute_error(test_with_profiles["occupancy_rate"], pred)),
        "r2": float(r2_score(test_with_profiles["occupancy_rate"], pred)),
        "elapsed_seconds": time.perf_counter() - start,
    }


def greedy_backward_search(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    initial_features: list[str],
    random_seed: int,
    min_delta: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    current_features = list(initial_features)
    current = evaluate_features(train_df, test_df, current_features, random_seed)
    current["step"] = 0
    current["accepted"] = True
    current["removed_feature"] = ""

    accepted_rows = [current.copy()]
    candidate_rows = [current.copy()]
    best_r2 = float(current["r2"])

    step = 1
    while len(current_features) > 1:
        step_candidates = []
        for feature in current_features:
            candidate_features = [item for item in current_features if item != feature]
            result = evaluate_features(train_df, test_df, candidate_features, random_seed)
            result["step"] = step
            result["removed_feature"] = feature
            result["accepted"] = False
            step_candidates.append(result)
            print(
                f"step={step} try_remove={feature}: "
                f"R2={result['r2']:.6f}, MAE={result['mae']:.6f}, "
                f"features={result['features']}",
                flush=True,
            )

        best_candidate = max(step_candidates, key=lambda row: float(row["r2"]))
        candidate_rows.extend(step_candidates)
        improvement = float(best_candidate["r2"]) - best_r2
        if improvement <= min_delta:
            print(
                f"stop: best removal {best_candidate['removed_feature']} "
                f"improves R2 by {improvement:.8f}",
                flush=True,
            )
            break

        best_candidate["accepted"] = True
        accepted_rows.append(best_candidate.copy())
        best_r2 = float(best_candidate["r2"])
        current_features = best_candidate["feature_list"].split("|")
        print(
            f"accept step={step}: removed={best_candidate['removed_feature']}, "
            f"R2={best_r2:.6f}, MAE={best_candidate['mae']:.6f}, "
            f"features={len(current_features)}",
            flush=True,
        )
        step += 1

    return pd.DataFrame(accepted_rows), pd.DataFrame(candidate_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize occupancy features by greedy removal.")
    parser.add_argument("--station-dir", type=Path, default=DEFAULT_STATION_DIR)
    parser.add_argument("--weather-file", type=Path, default=DEFAULT_WEATHER_FILE)
    parser.add_argument("--poi-file", type=Path, default=DEFAULT_POI_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--cache-file",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "occupancy_poi_training_frame.pkl",
    )
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--rows-per-station", type=int, default=250)
    parser.add_argument("--max-stations", type=int, default=None)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--min-delta", type=float, default=0.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = load_or_build_frame(args)
    train_df, test_df = time_split(df, args.test_size)
    accepted, candidates = greedy_backward_search(
        train_df,
        test_df,
        ALL_FEATURES,
        args.random_seed,
        args.min_delta,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    accepted_path = args.output_dir / "occupancy_feature_backward_selected.csv"
    candidates_path = args.output_dir / "occupancy_feature_backward_candidates.csv"
    accepted.to_csv(accepted_path, index=False)
    candidates.to_csv(candidates_path, index=False)

    best = accepted.sort_values("r2", ascending=False).iloc[0]
    print(f"Saved accepted path: {accepted_path}")
    print(f"Saved candidate trials: {candidates_path}")
    print(
        f"Best R2={best['r2']:.6f}, MAE={best['mae']:.6f}, "
        f"features={best['features']}"
    )
    print(best["feature_list"])


if __name__ == "__main__":
    main()
