"""Tune the multi-horizon occupancy XGBoost model with Optuna."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import optuna
import pandas as pd

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
    parse_horizons,
    prepare_context_features,
)
from tune_horizon_xgboost import (
    BASELINE_PARAMS,
    DEFAULT_VALIDATION_CUTOFF,
    compact_metrics,
    evaluate_params,
    normalize_params,
    split_train_valid_test,
)
from plot_shap_occupancy import DEFAULT_STATION_DIR, DEFAULT_WEATHER_FILE
from run_occupancy_poi_experiment import DEFAULT_POI_FILE


def suggest_params(trial: optuna.Trial) -> dict[str, Any]:
    return normalize_params(
        {
            "n_estimators": trial.suggest_categorical("n_estimators", [300, 500, 800, 1200]),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.08, log=True),
            "subsample": trial.suggest_float("subsample", 0.60, 1.00, step=0.05),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.60, 1.00, step=0.05),
            "min_child_weight": trial.suggest_categorical("min_child_weight", [1, 2, 3, 5, 7, 10, 12]),
            "reg_alpha": trial.suggest_categorical("reg_alpha", [0.0, 0.001, 0.01, 0.05, 0.1, 0.5, 1.0]),
            "reg_lambda": trial.suggest_categorical("reg_lambda", [0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 10.0, 15.0, 20.0]),
        }
    )


def save_partial_outputs(
    results: list[dict[str, Any]],
    by_horizon_parts: list[pd.DataFrame],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(output_dir / "occupancy_horizon_optuna_trials.partial.csv", index=False)
    if by_horizon_parts:
        pd.concat(by_horizon_parts, ignore_index=True).to_csv(
            output_dir / "occupancy_horizon_optuna_by_horizon.partial.csv",
            index=False,
        )


def run_optuna(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
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

    def objective(trial: optuna.Trial) -> float:
        params = suggest_params(trial)
        _, metrics, by_horizon = evaluate_params(
            params,
            train_df,
            valid_df,
            features,
            args.random_seed,
            "optuna",
            trial.number + 1,
            "validation",
        )
        results.append(metrics)
        by_horizon_parts.append(by_horizon)
        for key, value in metrics.items():
            if key not in params:
                trial.set_user_attr(key, value)
        print(
            f"optuna {trial.number + 1}/{args.trials} "
            f"mae={metrics['mae']:.6f} r2={metrics['r2']:.6f}",
            flush=True,
        )
        if args.checkpoint_every > 0 and (trial.number + 1) % args.checkpoint_every == 0:
            save_partial_outputs(results, by_horizon_parts, args.output_dir)
        return float(metrics["mae"])

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=args.random_seed)
    study = optuna.create_study(direction="minimize", sampler=sampler, study_name=args.study_name)
    study.optimize(objective, n_trials=args.trials, show_progress_bar=False)

    results_frame = pd.DataFrame(results).sort_values(["mae", "r2"], ascending=[True, False]).reset_index(drop=True)
    best_row = results_frame[results_frame["stage"] == "optuna"].iloc[0].to_dict()
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
        "optuna_best",
        int(best_row["trial"]),
        "test",
    )
    by_horizon_parts.extend([baseline_test_horizon, best_test_horizon])

    comparison = pd.DataFrame(
        [
            {"model": "baseline_validation", **baseline_valid},
            {"model": "optuna_best_validation", **best_row},
            {"model": "baseline_test", **baseline_test},
            {"model": "optuna_best_test", **best_test},
        ]
    )
    by_horizon_frame = pd.concat(by_horizon_parts, ignore_index=True)
    metadata = {
        "feature_set": args.feature_set,
        "selection_metric": "validation_mae",
        "validation_cutoff": validation_cutoff.isoformat(),
        "test_cutoff": test_cutoff.isoformat(),
        "random_seed": args.random_seed,
        "study_name": args.study_name,
        "trials": args.trials,
        "best_trial": int(best_row["trial"]),
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
    results.to_csv(output_dir / "occupancy_horizon_optuna_trials.csv", index=False)
    by_horizon.to_csv(output_dir / "occupancy_horizon_optuna_by_horizon.csv", index=False)
    comparison.to_csv(output_dir / "occupancy_horizon_optuna_comparison.csv", index=False)
    with (model_dir / "occupancy_horizon_optuna_best_params.json").open("w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tune multi-horizon occupancy XGBoost parameters with Optuna.")
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
    parser.add_argument("--trials", type=int, default=60)
    parser.add_argument("--checkpoint-every", type=int, default=10)
    parser.add_argument("--study-name", type=str, default="occupancy_horizon_xgboost_optuna")
    parser.add_argument("--random-seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    results, by_horizon, comparison, metadata = run_optuna(args)
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
