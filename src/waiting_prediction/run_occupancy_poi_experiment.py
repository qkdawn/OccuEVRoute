"""Run occupancy XGBoost ablations with station POI features."""

from __future__ import annotations

import argparse
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
    apply_station_profiles,
    build_training_frame,
    fit_station_profiles,
    load_station_info,
    load_station_sample,
    load_weather,
)


DEFAULT_POI_FILE = PROJECT_ROOT / "data" / "processed" / "station_poi_features.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "figures"

BASE_FEATURES = [
    "station_id",
    "weekday",
    "hour",
    "is_holiday",
    "temperature",
    "humidity",
    "rain",
    "charge_count",
    "s_price",
    "e_price",
    "station_avg_occupancy",
    "station_avg_duration",
]
PEAK_FEATURES = ["is_morning_peak", "is_evening_peak"]
POI_COUNT_FEATURES = [
    "poi_total_count",
    "poi_lifestyle_services_count",
    "poi_business_residential_count",
    "poi_food_beverage_count",
]
POI_RATIO_FEATURES = [
    "poi_lifestyle_ratio",
    "poi_business_residential_ratio",
    "poi_food_beverage_ratio",
]


def load_poi_features(path: Path) -> pd.DataFrame:
    poi = pd.read_csv(path)
    required = {"station_id", *POI_COUNT_FEATURES}
    missing = required - set(poi.columns)
    if missing:
        raise ValueError(f"POI feature file is missing columns: {sorted(missing)}")
    poi = poi[["station_id", *POI_COUNT_FEATURES]].copy()
    total = poi["poi_total_count"].replace(0, np.nan)
    poi["poi_lifestyle_ratio"] = poi["poi_lifestyle_services_count"] / total
    poi["poi_business_residential_ratio"] = poi["poi_business_residential_count"] / total
    poi["poi_food_beverage_ratio"] = poi["poi_food_beverage_count"] / total
    return poi.fillna(0.0)


def add_poi_features(df: pd.DataFrame, poi: pd.DataFrame) -> pd.DataFrame:
    df = df.merge(poi, on="station_id", how="left")
    for column in [*POI_COUNT_FEATURES, *POI_RATIO_FEATURES]:
        df[column] = df[column].fillna(0.0)
    return df


def time_split(df: pd.DataFrame, test_size: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    unique_times = np.sort(df["time"].dropna().unique())
    cutoff_index = int(len(unique_times) * (1.0 - test_size))
    cutoff_time = pd.Timestamp(unique_times[cutoff_index])
    train_df = df[df["time"] < cutoff_time].copy()
    test_df = df[df["time"] >= cutoff_time].copy()
    return train_df, test_df


def station_holdout_split(
    df: pd.DataFrame, test_size: float, random_seed: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    stations = pd.Series(df["station_id"].unique()).sample(frac=1, random_state=random_seed)
    test_count = max(1, int(round(len(stations) * test_size)))
    test_stations = set(stations.iloc[:test_count])
    train_df = df[~df["station_id"].isin(test_stations)].copy()
    test_df = df[df["station_id"].isin(test_stations)].copy()
    return train_df, test_df


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


def evaluate(
    name: str,
    split_name: str,
    df: pd.DataFrame,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    features: list[str],
    random_seed: int,
) -> tuple[dict[str, object], pd.DataFrame]:
    start = time.perf_counter()
    profiles = fit_station_profiles(train_df)
    train_df = apply_station_profiles(train_df, profiles)
    test_df = apply_station_profiles(test_df, profiles)

    model = make_model(random_seed)
    x_train = train_df[features]
    y_train = train_df["occupancy_rate"]
    x_test = test_df[features]
    y_test = test_df["occupancy_rate"]
    model.fit(x_train, y_train)
    pred = model.predict(x_test)
    elapsed = time.perf_counter() - start

    row = {
        "split": split_name,
        "model": name,
        "features": len(features),
        "rows": len(df),
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "train_stations": int(train_df["station_id"].nunique()),
        "test_stations": int(test_df["station_id"].nunique()),
        "mae": float(mean_absolute_error(y_test, pred)),
        "r2": float(r2_score(y_test, pred)),
        "elapsed_seconds": elapsed,
        "train_start": train_df["time"].min().isoformat(),
        "train_end": train_df["time"].max().isoformat(),
        "test_start": test_df["time"].min().isoformat(),
        "test_end": test_df["time"].max().isoformat(),
    }
    importances = pd.DataFrame(
        {
            "split": split_name,
            "model": name,
            "feature": features,
            "importance": model.feature_importances_,
        }
    ).sort_values(["split", "model", "importance"], ascending=[True, True, False])
    return row, importances


def build_experiment_frame(args: argparse.Namespace) -> pd.DataFrame:
    weather = load_weather(args.weather_file)
    station_data = load_station_sample(
        args.station_dir,
        args.rows_per_station,
        args.max_stations,
        args.random_seed,
    )
    station_info = load_station_info(args.station_dir)
    station_data = station_data.merge(station_info, on="station_id", how="left")
    df = build_training_frame(station_data, weather)
    return add_poi_features(df, load_poi_features(args.poi_file))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run occupancy POI ablation experiments.")
    parser.add_argument("--station-dir", type=Path, default=DEFAULT_STATION_DIR)
    parser.add_argument("--weather-file", type=Path, default=DEFAULT_WEATHER_FILE)
    parser.add_argument("--poi-file", type=Path, default=DEFAULT_POI_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--rows-per-station", type=int, default=250)
    parser.add_argument("--max-stations", type=int, default=None)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--test-size", type=float, default=0.2)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = build_experiment_frame(args)

    model_features = {
        "baseline": BASE_FEATURES,
        "baseline_peak": [*BASE_FEATURES, *PEAK_FEATURES],
        "baseline_poi_counts": [*BASE_FEATURES, *POI_COUNT_FEATURES],
        "baseline_poi_counts_ratios": [
            *BASE_FEATURES,
            *POI_COUNT_FEATURES,
            *POI_RATIO_FEATURES,
        ],
        "weak_no_station_history": [
            feature
            for feature in BASE_FEATURES
            if feature not in {"station_id", "station_avg_occupancy", "station_avg_duration"}
        ],
        "weak_no_station_history_poi": [
            *[
                feature
                for feature in BASE_FEATURES
                if feature
                not in {"station_id", "station_avg_occupancy", "station_avg_duration"}
            ],
            *POI_COUNT_FEATURES,
            *POI_RATIO_FEATURES,
        ],
    }

    splits = {
        "time_unique_80_20": time_split(df, args.test_size),
        "station_holdout_80_20": station_holdout_split(df, args.test_size, args.random_seed),
    }

    rows = []
    importance_parts = []
    for split_name, (train_df, test_df) in splits.items():
        for model_name, features in model_features.items():
            row, importances = evaluate(
                model_name,
                split_name,
                df,
                train_df,
                test_df,
                features,
                args.random_seed,
            )
            rows.append(row)
            importance_parts.append(importances)
            print(
                f"{split_name} {model_name}: "
                f"MAE={row['mae']:.6f}, R2={row['r2']:.6f}, features={row['features']}",
                flush=True,
            )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    metrics = pd.DataFrame(rows)
    importances = pd.concat(importance_parts, ignore_index=True)
    metrics.to_csv(args.output_dir / "occupancy_poi_ablation_metrics.csv", index=False)
    importances.to_csv(
        args.output_dir / "occupancy_poi_ablation_feature_importance.csv", index=False
    )
    print(f"Saved metrics: {args.output_dir / 'occupancy_poi_ablation_metrics.csv'}")
    print(
        "Saved feature importance: "
        f"{args.output_dir / 'occupancy_poi_ablation_feature_importance.csv'}"
    )


if __name__ == "__main__":
    main()
