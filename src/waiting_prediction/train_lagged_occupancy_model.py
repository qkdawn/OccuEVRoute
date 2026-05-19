"""Train a lagged historical occupancy model with a time-based split."""

from __future__ import annotations

import argparse
import json
import pickle
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from sklearn.metrics import mean_absolute_error, r2_score
from xgboost import XGBRegressor

from plot_shap_occupancy import (
    DEFAULT_STATION_DIR,
    DEFAULT_WEATHER_FILE,
    PROJECT_ROOT,
    add_time_features,
    apply_station_profiles,
    build_training_frame,
    fit_station_profiles,
    load_station_info,
    load_weather,
)


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "figures"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "models"
DEFAULT_CUTOFF_TIME = pd.Timestamp("2023-01-23 19:05:00")

BASE_FEATURES = [
    "station_id",
    "weekday",
    "hour",
    "minute",
    "is_holiday",
    "is_morning_peak",
    "is_evening_peak",
    "temperature",
    "humidity",
    "rain",
    "charge_count",
    "s_price",
    "e_price",
    "station_avg_occupancy",
    "station_avg_duration",
    "station_peak_avg_occupancy",
]

LAG_FEATURES = [
    "occupancy_lag_1",
    "occupancy_lag_3",
    "occupancy_lag_6",
    "occupancy_lag_12",
    "occupancy_rolling_mean_6",
    "occupancy_rolling_mean_12",
    "occupancy_rolling_std_12",
    "occupancy_trend_12",
]

FEATURE_LABELS = {
    "occupancy_lag_1": "Previous 5 min occupancy",
    "occupancy_lag_3": "Previous 15 min occupancy",
    "occupancy_lag_6": "Previous 30 min occupancy",
    "occupancy_lag_12": "Previous 60 min occupancy",
    "occupancy_rolling_mean_6": "30 min rolling mean",
    "occupancy_rolling_mean_12": "60 min rolling mean",
    "occupancy_rolling_std_12": "60 min volatility",
    "occupancy_trend_12": "60 min trend",
}

FEATURES = [*BASE_FEATURES, *LAG_FEATURES]

FEATURE_SETS = {
    "base": BASE_FEATURES,
    "lag_only": LAG_FEATURES,
    "base_lag": FEATURES,
    "compact_lag": [
        "station_id",
        "weekday",
        "hour",
        "minute",
        "is_holiday",
        "charge_count",
        "s_price",
        "e_price",
        "station_avg_occupancy",
        "station_avg_duration",
        "occupancy_lag_1",
        "occupancy_lag_3",
        "occupancy_lag_6",
        "occupancy_rolling_mean_6",
        "occupancy_rolling_mean_12",
        "occupancy_trend_12",
    ],
    "history_core": [
        "station_avg_occupancy",
        "occupancy_lag_1",
        "occupancy_lag_3",
        "occupancy_lag_6",
        "occupancy_rolling_mean_6",
        "occupancy_rolling_mean_12",
        "occupancy_trend_12",
    ],
}


def load_station_history(
    station_dir: Path,
    tail_rows_per_station: int,
    max_stations: int | None,
    random_seed: int,
) -> pd.DataFrame:
    files = sorted(p for p in station_dir.glob("*.csv") if p.stem.isdigit())
    if max_stations is not None:
        files = files[:max_stations]

    parts = []
    for path in files:
        station_id = int(path.stem)
        df = pd.read_csv(
            path,
            usecols=["time", "busy", "idle", "s_price", "e_price", "duration"],
        )
        df["time"] = pd.to_datetime(df["time"])
        df["duration"] = pd.to_numeric(df["duration"], errors="coerce").fillna(0.0)
        denominator = df["busy"] + df["idle"]
        df = df[denominator > 0].copy()
        df["occupancy_rate"] = df["busy"] / (df["busy"] + df["idle"])
        df = add_time_features(df)
        if tail_rows_per_station > 0 and len(df) > tail_rows_per_station:
            df = df.sort_values("time").tail(tail_rows_per_station)
        df["station_id"] = station_id
        parts.append(df)

    if not parts:
        raise ValueError(f"No station CSV files found in {station_dir}")
    return pd.concat(parts, ignore_index=True)


def add_lagged_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["station_id", "time"]).copy()
    grouped = df.groupby("station_id", group_keys=False)["occupancy_rate"]
    shifted = grouped.shift(1)

    df["occupancy_lag_1"] = grouped.shift(1)
    df["occupancy_lag_3"] = grouped.shift(3)
    df["occupancy_lag_6"] = grouped.shift(6)
    df["occupancy_lag_12"] = grouped.shift(12)
    df["occupancy_rolling_mean_6"] = shifted.groupby(df["station_id"]).rolling(6).mean().reset_index(level=0, drop=True)
    df["occupancy_rolling_mean_12"] = shifted.groupby(df["station_id"]).rolling(12).mean().reset_index(level=0, drop=True)
    df["occupancy_rolling_std_12"] = shifted.groupby(df["station_id"]).rolling(12).std().reset_index(level=0, drop=True)
    df["occupancy_trend_12"] = df["occupancy_lag_1"] - df["occupancy_lag_12"]
    return df.dropna(subset=LAG_FEATURES).reset_index(drop=True)


def build_lagged_frame(args: argparse.Namespace) -> pd.DataFrame:
    weather = load_weather(args.weather_file)
    station_data = load_station_history(
        args.station_dir,
        args.tail_rows_per_station,
        args.max_stations,
        args.random_seed,
    )
    station_info = load_station_info(args.station_dir)
    station_data = station_data.merge(station_info, on="station_id", how="left")
    df = build_training_frame(station_data, weather)
    return add_lagged_features(df)


def time_split(df: pd.DataFrame, cutoff_time: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_df = df[df["time"] < cutoff_time].copy()
    test_df = df[df["time"] >= cutoff_time].copy()
    if train_df.empty or test_df.empty:
        raise ValueError("Time split produced an empty train or test set.")
    return train_df, test_df


def make_model(random_seed: int) -> XGBRegressor:
    return XGBRegressor(
        objective="reg:squarederror",
        n_estimators=500,
        max_depth=5,
        learning_rate=0.04,
        subsample=0.85,
        colsample_bytree=0.85,
        random_state=random_seed,
        n_jobs=-1,
    )


def evaluate_feature_set(
    name: str,
    features: list[str],
    df: pd.DataFrame,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    random_seed: int,
) -> tuple[XGBRegressor, dict[str, object], pd.DataFrame]:
    started = time.perf_counter()
    model = make_model(random_seed)
    model.fit(train_df[features], train_df["occupancy_rate"])
    predictions = model.predict(test_df[features])

    metrics = {
        "feature_set": name,
        "target": "occupancy_rate",
        "features": len(features),
        "rows": len(df),
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "stations": int(df["station_id"].nunique()),
        "mae": float(mean_absolute_error(test_df["occupancy_rate"], predictions)),
        "r2": float(r2_score(test_df["occupancy_rate"], predictions)),
        "elapsed_seconds": time.perf_counter() - started,
    }

    importance = pd.DataFrame(
        {
            "feature_set": name,
            "feature": features,
            "importance": model.feature_importances_,
        }
    ).sort_values(["feature_set", "importance"], ascending=[True, False])
    return model, metrics, importance


def train_and_evaluate(
    args: argparse.Namespace,
) -> tuple[
    XGBRegressor,
    dict[str, object],
    pd.DataFrame,
    dict[str, object],
    pd.DataFrame,
    pd.DataFrame,
]:
    started = time.perf_counter()
    df = build_lagged_frame(args)
    train_df, test_df = time_split(df, pd.Timestamp(args.cutoff_time))

    profiles = fit_station_profiles(train_df)
    train_df = apply_station_profiles(train_df, profiles)
    test_df = apply_station_profiles(test_df, profiles)

    rows = []
    importance_parts = []
    models = {}
    for name, features in FEATURE_SETS.items():
        model, row, importance = evaluate_feature_set(name, features, df, train_df, test_df, args.random_seed)
        row.update(
            {
                "split": "fixed_time_holdout",
                "cutoff_time": pd.Timestamp(args.cutoff_time).isoformat(),
                "train_start": train_df["time"].min().isoformat(),
                "train_end": train_df["time"].max().isoformat(),
                "test_start": test_df["time"].min().isoformat(),
                "test_end": test_df["time"].max().isoformat(),
            }
        )
        rows.append(row)
        importance_parts.append(importance)
        models[name] = model

    metrics_table = pd.DataFrame(rows).sort_values("r2", ascending=False)
    best_feature_set = str(metrics_table.iloc[0]["feature_set"])
    model = models[best_feature_set]
    metrics = metrics_table.iloc[0].to_dict()
    metadata = {
        "selected_feature_set": best_feature_set,
        "features": FEATURE_SETS[best_feature_set],
        "feature_sets": FEATURE_SETS,
        "lag_rule": "All lag and rolling occupancy features use shift(1), so each row uses only prior station records.",
        "cutoff_time": pd.Timestamp(args.cutoff_time).isoformat(),
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "model": "XGBRegressor",
        "model_params": model.get_params(),
        "station_dir": str(args.station_dir),
        "weather_file": str(args.weather_file),
        "total_elapsed_seconds": time.perf_counter() - started,
    }
    return model, metrics, pd.concat(importance_parts, ignore_index=True), metadata, metrics_table, test_df


def compute_shap_summary(
    model: XGBRegressor,
    test_df: pd.DataFrame,
    features: list[str],
    sample_size: int,
    random_seed: int,
) -> tuple[pd.DataFrame, np.ndarray, pd.DataFrame]:
    x_test = test_df[features]
    sample = x_test.sample(min(sample_size, len(x_test)), random_state=random_seed)
    explainer = shap.TreeExplainer(model)
    shap_values = np.asarray(explainer.shap_values(sample))
    importance = (
        pd.DataFrame(
            {
                "feature": features,
                "display_feature": [FEATURE_LABELS.get(feature, feature) for feature in features],
                "mean_abs_shap": np.abs(shap_values).mean(axis=0),
            }
        )
        .sort_values("mean_abs_shap", ascending=False)
        .reset_index(drop=True)
    )
    return sample, shap_values, importance


def save_shap_plots(
    sample: pd.DataFrame,
    shap_values: np.ndarray,
    shap_importance: pd.DataFrame,
    metrics: dict[str, object],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    shap_importance.to_csv(output_dir / "occupancy_lagged_shap_importance.csv", index=False)

    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#d8dee8",
            "axes.labelcolor": "#172033",
            "xtick.color": "#475569",
            "ytick.color": "#475569",
            "font.size": 11,
        }
    )

    order = shap_importance.sort_values("mean_abs_shap", ascending=True)
    fig, ax = plt.subplots(figsize=(9.5, 5.6))
    colors = plt.cm.viridis(np.linspace(0.3, 0.82, len(order)))
    ax.barh(order["display_feature"], order["mean_abs_shap"], color=colors, edgecolor="none")
    ax.set_xlabel("Mean absolute SHAP value")
    ax.set_title("Lagged Occupancy Model: Feature Impact", fontsize=16, fontweight="bold", color="#172033", pad=14)
    ax.text(
        0,
        1.02,
        f"Fixed time holdout | R2={float(metrics['r2']):.3f} | MAE={float(metrics['mae']):.3f}",
        transform=ax.transAxes,
        color="#64748b",
        fontsize=11,
    )
    ax.grid(axis="x", color="#e5eaf0", linewidth=0.9)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(output_dir / "occupancy_lagged_shap_bar.png", dpi=240)
    plt.close(fig)

    display_sample = sample.rename(columns=FEATURE_LABELS)
    fig = plt.figure(figsize=(10, 5.8))
    shap.summary_plot(
        shap_values,
        display_sample,
        show=False,
        max_display=len(display_sample.columns),
        color_bar_label="Feature value",
    )
    plt.title("Lagged Occupancy Model: SHAP Summary", fontsize=16, fontweight="bold", color="#172033", pad=12)
    plt.tight_layout()
    fig.savefig(output_dir / "occupancy_lagged_shap_summary.png", dpi=240, bbox_inches="tight")
    plt.close(fig)


def save_outputs(
    model: XGBRegressor,
    metrics: dict[str, object],
    importance: pd.DataFrame,
    metadata: dict[str, object],
    metrics_table: pd.DataFrame,
    test_df: pd.DataFrame,
    output_dir: Path,
    model_dir: Path,
    shap_sample_size: int,
    random_seed: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)

    with (model_dir / "occupancy_lagged_xgboost.pkl").open("wb") as file:
        pickle.dump(model, file)
    with (model_dir / "occupancy_lagged_features.json").open("w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=2)

    pd.DataFrame([metrics]).to_csv(output_dir / "occupancy_lagged_model_metrics.csv", index=False)
    metrics_table.to_csv(output_dir / "occupancy_lagged_feature_set_metrics.csv", index=False)
    importance.to_csv(output_dir / "occupancy_lagged_feature_importance.csv", index=False)
    shap_sample, shap_values, shap_importance = compute_shap_summary(
        model,
        test_df,
        metadata["features"],
        shap_sample_size,
        random_seed,
    )
    save_shap_plots(shap_sample, shap_values, shap_importance, metrics, output_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train lagged historical occupancy model.")
    parser.add_argument("--station-dir", type=Path, default=DEFAULT_STATION_DIR)
    parser.add_argument("--weather-file", type=Path, default=DEFAULT_WEATHER_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--cutoff-time", type=str, default=DEFAULT_CUTOFF_TIME.isoformat())
    parser.add_argument("--tail-rows-per-station", type=int, default=0)
    parser.add_argument("--max-stations", type=int, default=None)
    parser.add_argument("--shap-sample-size", type=int, default=5000)
    parser.add_argument("--random-seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model, metrics, importance, metadata, metrics_table, test_df = train_and_evaluate(args)
    save_outputs(
        model,
        metrics,
        importance,
        metadata,
        metrics_table,
        test_df,
        args.output_dir,
        args.model_dir,
        args.shap_sample_size,
        args.random_seed,
    )
    print(metrics_table.to_string(index=False))
    print("\nSelected feature set:", metadata["selected_feature_set"])
    print(importance.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
