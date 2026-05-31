"""Tune the multi-horizon occupancy XGBoost model with time-based validation."""

from __future__ import annotations

import argparse
from itertools import product
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score
from xgboost import XGBRegressor

from train_lagged_occupancy_model import (
    DEFAULT_BASE_ROWS_PER_STATION,
    DEFAULT_CUTOFF_TIME,
    DEFAULT_HORIZONS_MIN,
    DEFAULT_MAX_ROWS_PER_HORIZON,
    DEFAULT_MAX_STATIONS,
    DEFAULT_MODEL_DIR,
    DEFAULT_NEIGHBOR_K,
    DEFAULT_OUTPUT_DIR,
    FEATURE_SETS,
    PREFERRED_FEATURE_SET,
    build_lagged_frame,
    evaluate_by_horizon,
    parse_horizons,
    prepare_context_features,
)
from plot_shap_occupancy import DEFAULT_STATION_DIR, DEFAULT_WEATHER_FILE
from run_occupancy_poi_experiment import DEFAULT_POI_FILE


DEFAULT_VALIDATION_CUTOFF = pd.Timestamp("2023-01-01 00:00:00")
BASELINE_PARAMS = {
    "n_estimators": 500,
    "max_depth": 5,
    "learning_rate": 0.04,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "min_child_weight": 1,
    "reg_alpha": 0.0,
    "reg_lambda": 1.0,
}
STAGE1_SPACE = {
    "n_estimators": [300, 500, 800, 1200],
    "max_depth": [3, 4, 5, 6, 8],
    "learning_rate": [0.01, 0.02, 0.04, 0.06, 0.08],
    "subsample": [0.70, 0.85, 1.00],
    "colsample_bytree": [0.70, 0.85, 1.00],
    "min_child_weight": [1, 3, 5, 10],
    "reg_alpha": [0.0, 0.01, 0.1, 1.0],
    "reg_lambda": [1.0, 3.0, 5.0, 10.0],
}


def split_train_valid_test(
    df: pd.DataFrame,
    validation_cutoff: pd.Timestamp,
    test_cutoff: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if validation_cutoff >= test_cutoff:
        raise ValueError("validation-cutoff must be earlier than test-cutoff.")
    train_df = df[df["time"] < validation_cutoff].copy()
    valid_df = df[(df["time"] >= validation_cutoff) & (df["time"] < test_cutoff)].copy()
    test_df = df[df["time"] >= test_cutoff].copy()
    if train_df.empty or valid_df.empty or test_df.empty:
        raise ValueError(
            "Time split produced an empty train, validation, or test set. "
            f"Rows: train={len(train_df)}, valid={len(valid_df)}, test={len(test_df)}."
        )
    return train_df, valid_df, test_df


def make_model(params: dict[str, Any], random_seed: int) -> XGBRegressor:
    return XGBRegressor(
        objective="reg:squarederror",
        random_state=random_seed,
        n_jobs=-1,
        **normalize_params(params),
    )


def params_key(params: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    return tuple(sorted(normalize_params(params).items()))


def normalize_params(params: dict[str, Any]) -> dict[str, Any]:
    out = dict(params)
    for key in ["n_estimators", "max_depth", "min_child_weight"]:
        out[key] = int(out[key])
    for key in ["learning_rate", "subsample", "colsample_bytree", "reg_alpha", "reg_lambda"]:
        out[key] = float(out[key])
    return out


def sample_from_space(
    space: dict[str, list[Any]],
    trials: int,
    random_seed: int,
    exclude: set[tuple[tuple[str, Any], ...]] | None = None,
) -> list[dict[str, Any]]:
    exclude = exclude or set()
    keys = list(space)
    candidates = [dict(zip(keys, values, strict=True)) for values in product(*(space[key] for key in keys))]
    candidates = [candidate for candidate in candidates if params_key(candidate) not in exclude]
    if not candidates:
        return []
    rng = np.random.default_rng(random_seed)
    count = min(trials, len(candidates))
    chosen = rng.choice(len(candidates), size=count, replace=False)
    return [candidates[int(index)] for index in chosen]


def neighboring_values(value: Any, domain: list[Any], radius: int = 1) -> list[Any]:
    ordered = sorted(domain)
    if value not in ordered:
        ordered.append(value)
        ordered = sorted(ordered)
    index = ordered.index(value)
    start = max(0, index - radius)
    end = min(len(ordered), index + radius + 1)
    return ordered[start:end]


def build_stage2_candidates(
    top_params: list[dict[str, Any]],
    trials: int,
    random_seed: int,
    exclude: set[tuple[tuple[str, Any], ...]],
) -> list[dict[str, Any]]:
    local_candidates: list[dict[str, Any]] = []
    for params in top_params:
        local_space = {
            "n_estimators": neighboring_values(params["n_estimators"], [200, 300, 500, 800, 1000, 1200, 1400]),
            "max_depth": neighboring_values(params["max_depth"], [2, 3, 4, 5, 6, 7, 8, 9]),
            "learning_rate": sorted(
                {
                    round(float(np.clip(params["learning_rate"] * scale, 0.005, 0.12)), 4)
                    for scale in [0.75, 1.0, 1.25]
                }
            ),
            "subsample": sorted(
                {
                    round(float(np.clip(params["subsample"] + delta, 0.60, 1.00)), 2)
                    for delta in [-0.10, 0.0, 0.10]
                }
            ),
            "colsample_bytree": sorted(
                {
                    round(float(np.clip(params["colsample_bytree"] + delta, 0.60, 1.00)), 2)
                    for delta in [-0.10, 0.0, 0.10]
                }
            ),
            "min_child_weight": neighboring_values(params["min_child_weight"], [1, 2, 3, 5, 7, 10, 12]),
            "reg_alpha": neighboring_values(params["reg_alpha"], [0.0, 0.001, 0.01, 0.05, 0.1, 0.5, 1.0]),
            "reg_lambda": neighboring_values(params["reg_lambda"], [0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 10.0, 15.0]),
        }
        local_candidates.extend(sample_from_space(local_space, trials, random_seed + len(local_candidates), exclude))

    unique: list[dict[str, Any]] = []
    seen = set(exclude)
    for candidate in local_candidates:
        key = params_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)

    rng = np.random.default_rng(random_seed)
    if len(unique) <= trials:
        return unique
    chosen = rng.choice(len(unique), size=trials, replace=False)
    return [unique[int(index)] for index in chosen]


def evaluate_params(
    params: dict[str, Any],
    train_df: pd.DataFrame,
    eval_df: pd.DataFrame,
    features: list[str],
    random_seed: int,
    stage: str,
    trial: int,
    metric_scope: str,
) -> tuple[XGBRegressor, dict[str, Any], pd.DataFrame]:
    started = time.perf_counter()
    model = make_model(params, random_seed)
    model.fit(train_df[features], train_df["target_occupancy_rate"])
    predictions = np.clip(model.predict(eval_df[features]), 0.0, 1.0)
    metrics: dict[str, Any] = {
        "stage": stage,
        "trial": trial,
        "metric_scope": metric_scope,
        "features": len(features),
        "train_rows": len(train_df),
        "eval_rows": len(eval_df),
        "mae": float(mean_absolute_error(eval_df["target_occupancy_rate"], predictions)),
        "r2": float(r2_score(eval_df["target_occupancy_rate"], predictions)),
        "elapsed_seconds": time.perf_counter() - started,
    }
    metrics.update(params)
    by_horizon = evaluate_by_horizon(model, eval_df, features)
    by_horizon.insert(0, "metric_scope", metric_scope)
    by_horizon.insert(0, "trial", trial)
    by_horizon.insert(0, "stage", stage)
    for key, value in params.items():
        by_horizon[key] = value
    return model, metrics, by_horizon


def compact_metrics(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row[key]
        for key in [
            "stage",
            "trial",
            "metric_scope",
            "features",
            "train_rows",
            "eval_rows",
            "mae",
            "r2",
            "elapsed_seconds",
        ]
        if key in row
    }


def save_partial_outputs(
    results: list[dict[str, Any]],
    by_horizon_parts: list[pd.DataFrame],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(output_dir / "occupancy_horizon_tuning_results.partial.csv", index=False)
    if by_horizon_parts:
        pd.concat(by_horizon_parts, ignore_index=True).to_csv(
            output_dir / "occupancy_horizon_tuning_by_horizon.partial.csv",
            index=False,
        )


def run_tuning(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    raw_df = build_lagged_frame(args)
    validation_cutoff = pd.Timestamp(args.validation_cutoff)
    test_cutoff = pd.Timestamp(args.test_cutoff)
    raw_train, raw_valid, raw_test = split_train_valid_test(raw_df, validation_cutoff, test_cutoff)

    train_df, valid_df = prepare_context_features(args, raw_train, raw_valid)
    features = FEATURE_SETS[args.feature_set]
    results: list[dict[str, Any]] = []
    by_horizon_parts: list[pd.DataFrame] = []

    _, baseline_valid, baseline_valid_horizon = evaluate_params(
        BASELINE_PARAMS,
        train_df,
        valid_df,
        features,
        args.random_seed,
        "baseline",
        0,
        "validation",
    )
    results.append(baseline_valid)
    by_horizon_parts.append(baseline_valid_horizon)

    seen = {params_key(BASELINE_PARAMS)}
    stage1_candidates = sample_from_space(STAGE1_SPACE, args.stage1_trials, args.random_seed, seen)
    seen.update(params_key(candidate) for candidate in stage1_candidates)
    for index, params in enumerate(stage1_candidates, start=1):
        _, metrics, by_horizon = evaluate_params(
            params,
            train_df,
            valid_df,
            features,
            args.random_seed,
            "stage1",
            index,
            "validation",
        )
        results.append(metrics)
        by_horizon_parts.append(by_horizon)
        print(
            f"stage1 {index}/{len(stage1_candidates)} "
            f"mae={metrics['mae']:.6f} r2={metrics['r2']:.6f}",
            flush=True,
        )
        if args.checkpoint_every > 0 and index % args.checkpoint_every == 0:
            save_partial_outputs(results, by_horizon_parts, args.output_dir)

    stage1_frame = pd.DataFrame(results)
    top_params = (
        stage1_frame[stage1_frame["stage"] == "stage1"]
        .sort_values("mae")
        .head(5)[list(BASELINE_PARAMS)]
        .to_dict("records")
    )
    stage2_candidates = build_stage2_candidates(top_params, args.stage2_trials, args.random_seed + 1000, seen)
    for index, params in enumerate(stage2_candidates, start=1):
        _, metrics, by_horizon = evaluate_params(
            params,
            train_df,
            valid_df,
            features,
            args.random_seed,
            "stage2",
            index,
            "validation",
        )
        results.append(metrics)
        by_horizon_parts.append(by_horizon)
        print(
            f"stage2 {index}/{len(stage2_candidates)} "
            f"mae={metrics['mae']:.6f} r2={metrics['r2']:.6f}",
            flush=True,
        )
        if args.checkpoint_every > 0 and index % args.checkpoint_every == 0:
            save_partial_outputs(results, by_horizon_parts, args.output_dir)

    results_frame = pd.DataFrame(results).sort_values(["mae", "r2"], ascending=[True, False]).reset_index(drop=True)
    best_row = results_frame[results_frame["stage"] != "baseline"].iloc[0].to_dict()
    best_params = normalize_params({key: best_row[key] for key in BASELINE_PARAMS})

    raw_train_valid = pd.concat([raw_train, raw_valid], ignore_index=True)
    train_valid_df, test_df = prepare_context_features(args, raw_train_valid, raw_test)
    _, baseline_test, baseline_test_horizon = evaluate_params(
        BASELINE_PARAMS,
        train_valid_df,
        test_df,
        features,
        args.random_seed,
        "baseline",
        0,
        "test",
    )
    _, best_test, best_test_horizon = evaluate_params(
        best_params,
        train_valid_df,
        test_df,
        features,
        args.random_seed,
        "best",
        int(best_row["trial"]),
        "test",
    )
    by_horizon_parts.extend([baseline_test_horizon, best_test_horizon])

    comparison = pd.DataFrame(
        [
            {"model": "baseline_validation", **baseline_valid},
            {"model": "best_validation", **best_row},
            {"model": "baseline_test", **baseline_test},
            {"model": "best_test", **best_test},
        ]
    )
    by_horizon_frame = pd.concat(by_horizon_parts, ignore_index=True)
    metadata = {
        "feature_set": args.feature_set,
        "selection_metric": "validation_mae",
        "validation_cutoff": validation_cutoff.isoformat(),
        "test_cutoff": test_cutoff.isoformat(),
        "random_seed": args.random_seed,
        "best_params": best_params,
        "validation_metrics": compact_metrics(best_row),
        "test_metrics": compact_metrics(best_test),
        "baseline_validation_metrics": compact_metrics(baseline_valid),
        "baseline_test_metrics": compact_metrics(baseline_test),
    }
    return results_frame, by_horizon_frame, comparison, metadata


def save_outputs(
    results: pd.DataFrame,
    by_horizon: pd.DataFrame,
    comparison: pd.DataFrame,
    metadata: dict[str, Any],
    output_dir: Path,
    model_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    results.to_csv(output_dir / "occupancy_horizon_tuning_results.csv", index=False)
    by_horizon.to_csv(output_dir / "occupancy_horizon_tuning_by_horizon.csv", index=False)
    comparison.to_csv(output_dir / "occupancy_horizon_tuning_comparison.csv", index=False)
    with (model_dir / "occupancy_horizon_best_params.json").open("w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tune multi-horizon occupancy XGBoost parameters.")
    parser.add_argument("--station-dir", type=Path, default=DEFAULT_STATION_DIR)
    parser.add_argument("--weather-file", type=Path, default=DEFAULT_WEATHER_FILE)
    parser.add_argument("--poi-file", type=Path, default=DEFAULT_POI_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--validation-cutoff", type=str, default=DEFAULT_VALIDATION_CUTOFF.isoformat())
    parser.add_argument("--test-cutoff", type=str, default=DEFAULT_CUTOFF_TIME.isoformat())
    parser.add_argument("--tail-rows-per-station", type=int, default=0)
    parser.add_argument("--base-rows-per-station", type=int, default=DEFAULT_BASE_ROWS_PER_STATION)
    parser.add_argument("--max-stations", type=int, default=DEFAULT_MAX_STATIONS)
    parser.add_argument("--neighbor-k", type=int, default=DEFAULT_NEIGHBOR_K)
    parser.add_argument("--feature-set", type=str, default=PREFERRED_FEATURE_SET, choices=sorted(FEATURE_SETS))
    parser.add_argument("--horizons-min", type=parse_horizons, default=DEFAULT_HORIZONS_MIN)
    parser.add_argument("--max-rows-per-horizon", type=int, default=DEFAULT_MAX_ROWS_PER_HORIZON)
    parser.add_argument("--stage1-trials", type=int, default=80)
    parser.add_argument("--stage2-trials", type=int, default=40)
    parser.add_argument("--checkpoint-every", type=int, default=10)
    parser.add_argument("--random-seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    results, by_horizon, comparison, metadata = run_tuning(args)
    metadata["total_elapsed_seconds"] = time.perf_counter() - started
    save_outputs(results, by_horizon, comparison, metadata, args.output_dir, args.model_dir)
    print("\nTop validation results:")
    print(results.head(10).to_string(index=False))
    print("\nComparison:")
    print(comparison.to_string(index=False))
    print("\nBest params:")
    print(json.dumps(metadata["best_params"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
