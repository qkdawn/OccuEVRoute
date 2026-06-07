"""Analyze feature interactions for the trained occupancy horizon model."""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap

from train_lagged_occupancy_model import (
    DEFAULT_BASE_ROWS_PER_STATION,
    DEFAULT_CUTOFF_TIME,
    DEFAULT_HORIZONS_MIN,
    DEFAULT_MAX_ROWS_PER_HORIZON,
    DEFAULT_MAX_STATIONS,
    DEFAULT_MODEL_DIR,
    DEFAULT_NEIGHBOR_K,
    DEFAULT_OUTPUT_DIR,
    build_lagged_frame,
    parse_horizons,
    prepare_context_features,
    time_split,
)
from plot_shap_occupancy import DEFAULT_STATION_DIR, DEFAULT_WEATHER_FILE
from run_occupancy_poi_experiment import DEFAULT_POI_FILE


DEFAULT_MODEL_FILE = DEFAULT_MODEL_DIR / "occupancy_horizon_xgboost.pkl"
DEFAULT_FEATURE_FILE = DEFAULT_MODEL_DIR / "occupancy_horizon_features.json"


def load_model(path: Path) -> Any:
    with path.open("rb") as file:
        return pickle.load(file)


def load_features(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8") as file:
        metadata = json.load(file)
    features = metadata.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError(f"Feature metadata must contain a non-empty features list: {path}")
    return [str(feature) for feature in features]


def build_test_features(args: argparse.Namespace, features: list[str]) -> pd.DataFrame:
    df = build_lagged_frame(args)
    train_df, test_df = time_split(df, pd.Timestamp(args.cutoff_time))
    _, test_df = prepare_context_features(args, train_df, test_df)
    missing = [feature for feature in features if feature not in test_df.columns]
    if missing:
        raise ValueError(f"Test frame is missing model features: {missing}")
    return test_df


def summarize_interactions(
    interaction_values: np.ndarray,
    features: list[str],
    top_n: int,
) -> pd.DataFrame:
    mean_abs = np.abs(interaction_values).mean(axis=0)
    rows = []
    for i, feature_a in enumerate(features):
        for j in range(i + 1, len(features)):
            rows.append(
                {
                    "feature_a": feature_a,
                    "feature_b": features[j],
                    "mean_abs_interaction": float(mean_abs[i, j]),
                }
            )
    out = pd.DataFrame(rows).sort_values("mean_abs_interaction", ascending=False).reset_index(drop=True)
    total = float(out["mean_abs_interaction"].sum())
    out["share_of_pair_interactions"] = out["mean_abs_interaction"] / total if total > 0 else 0.0
    return out.head(top_n)


def save_interaction_bar(interactions: pd.DataFrame, output_file: Path) -> None:
    plot_df = interactions.head(20).iloc[::-1].copy()
    labels = plot_df["feature_a"] + " x " + plot_df["feature_b"]
    fig, ax = plt.subplots(figsize=(11, 8))
    ax.barh(labels, plot_df["mean_abs_interaction"], color="#2f6f73")
    ax.set_xlabel("Mean absolute SHAP interaction")
    ax.set_title("Top occupancy model feature interactions")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_file, dpi=180)
    plt.close(fig)


def compute_pdp_grid(
    model: Any,
    sample: pd.DataFrame,
    features: list[str],
    x_feature: str,
    y_feature: str,
    x_bins: int,
) -> pd.DataFrame:
    if x_feature not in features or y_feature not in features:
        raise ValueError(f"PDP features must be model features: {x_feature}, {y_feature}")
    x_values = np.quantile(sample[x_feature], np.linspace(0.05, 0.95, x_bins))
    y_values = np.sort(sample[y_feature].dropna().unique())
    rows = []
    for y_value in y_values:
        for x_value in x_values:
            frame = sample.copy()
            frame[x_feature] = float(x_value)
            frame[y_feature] = float(y_value)
            prediction = float(np.clip(model.predict(frame[features]).mean(), 0.0, 1.0))
            rows.append(
                {
                    x_feature: float(x_value),
                    y_feature: float(y_value),
                    "predicted_occupancy_rate": prediction,
                }
            )
    return pd.DataFrame(rows)


def save_pdp_heatmap(
    grid: pd.DataFrame,
    x_feature: str,
    y_feature: str,
    output_file: Path,
) -> None:
    pivot = grid.pivot_table(
        index=y_feature,
        columns=x_feature,
        values="predicted_occupancy_rate",
        aggfunc="mean",
    ).sort_index()
    fig, ax = plt.subplots(figsize=(10, 6))
    image = ax.imshow(pivot.to_numpy(), aspect="auto", origin="lower", cmap="viridis")
    ax.set_title(f"Partial dependence: {x_feature} x {y_feature}")
    ax.set_xlabel(x_feature)
    ax.set_ylabel(y_feature)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([f"{value:.2f}" for value in pivot.columns], rotation=45, ha="right")
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([f"{value:.0f}" for value in pivot.index])
    fig.colorbar(image, ax=ax, label="Predicted occupancy rate")
    fig.tight_layout()
    fig.savefig(output_file, dpi=180)
    plt.close(fig)


def run_analysis(args: argparse.Namespace) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    model = load_model(args.model_file)
    features = load_features(args.feature_file)
    test_df = build_test_features(args, features)
    sample = test_df.sample(min(args.shap_sample_size, len(test_df)), random_state=args.random_seed)
    x_sample = sample[features]

    explainer = shap.TreeExplainer(model)
    interaction_values = np.asarray(explainer.shap_interaction_values(x_sample))
    interactions = summarize_interactions(interaction_values, features, args.top_n)
    interactions.to_csv(args.output_dir / "occupancy_horizon_shap_interactions.csv", index=False)
    save_interaction_bar(interactions, args.output_dir / "occupancy_horizon_top_interactions.png")

    pdp_sample = test_df.sample(min(args.pdp_sample_size, len(test_df)), random_state=args.random_seed)
    pdp_grid = compute_pdp_grid(
        model,
        pdp_sample[features],
        features,
        args.pdp_x_feature,
        args.pdp_y_feature,
        args.pdp_x_bins,
    )
    pdp_grid.to_csv(args.output_dir / "occupancy_horizon_interaction_pdp_lag_horizon.csv", index=False)
    save_pdp_heatmap(
        pdp_grid,
        args.pdp_x_feature,
        args.pdp_y_feature,
        args.output_dir / "occupancy_horizon_interaction_pdp_lag_horizon.png",
    )

    print("Top interactions:")
    print(interactions.head(20).to_string(index=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze occupancy horizon model feature interactions.")
    parser.add_argument("--station-dir", type=Path, default=DEFAULT_STATION_DIR)
    parser.add_argument("--weather-file", type=Path, default=DEFAULT_WEATHER_FILE)
    parser.add_argument("--poi-file", type=Path, default=DEFAULT_POI_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-file", type=Path, default=DEFAULT_MODEL_FILE)
    parser.add_argument("--feature-file", type=Path, default=DEFAULT_FEATURE_FILE)
    parser.add_argument("--cutoff-time", type=str, default=DEFAULT_CUTOFF_TIME.isoformat())
    parser.add_argument("--tail-rows-per-station", type=int, default=0)
    parser.add_argument("--base-rows-per-station", type=int, default=DEFAULT_BASE_ROWS_PER_STATION)
    parser.add_argument("--max-stations", type=int, default=DEFAULT_MAX_STATIONS)
    parser.add_argument("--neighbor-k", type=int, default=DEFAULT_NEIGHBOR_K)
    parser.add_argument("--horizons-min", type=parse_horizons, default=DEFAULT_HORIZONS_MIN)
    parser.add_argument("--max-rows-per-horizon", type=int, default=DEFAULT_MAX_ROWS_PER_HORIZON)
    parser.add_argument("--shap-sample-size", type=int, default=1000)
    parser.add_argument("--pdp-sample-size", type=int, default=3000)
    parser.add_argument("--pdp-x-feature", type=str, default="occupancy_lag_1")
    parser.add_argument("--pdp-y-feature", type=str, default="prediction_horizon_min")
    parser.add_argument("--pdp-x-bins", type=int, default=12)
    parser.add_argument("--top-n", type=int, default=40)
    parser.add_argument("--random-seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    run_analysis(parse_args())


if __name__ == "__main__":
    main()
