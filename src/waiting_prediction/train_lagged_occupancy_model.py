"""Train a lagged historical occupancy model with a time-based split."""

from __future__ import annotations

import argparse
import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd
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


def train_and_evaluate(args: argparse.Namespace) -> tuple[XGBRegressor, dict[str, object], pd.DataFrame, dict[str, object], pd.DataFrame]:
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
    return model, metrics, pd.concat(importance_parts, ignore_index=True), metadata, metrics_table


def save_outputs(
    model: XGBRegressor,
    metrics: dict[str, object],
    importance: pd.DataFrame,
    metadata: dict[str, object],
    metrics_table: pd.DataFrame,
    output_dir: Path,
    model_dir: Path,
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train lagged historical occupancy model.")
    parser.add_argument("--station-dir", type=Path, default=DEFAULT_STATION_DIR)
    parser.add_argument("--weather-file", type=Path, default=DEFAULT_WEATHER_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--cutoff-time", type=str, default=DEFAULT_CUTOFF_TIME.isoformat())
    parser.add_argument("--tail-rows-per-station", type=int, default=0)
    parser.add_argument("--max-stations", type=int, default=None)
    parser.add_argument("--random-seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model, metrics, importance, metadata, metrics_table = train_and_evaluate(args)
    save_outputs(model, metrics, importance, metadata, metrics_table, args.output_dir, args.model_dir)
    print(metrics_table.to_string(index=False))
    print("\nSelected feature set:", metadata["selected_feature_set"])
    print(importance.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
