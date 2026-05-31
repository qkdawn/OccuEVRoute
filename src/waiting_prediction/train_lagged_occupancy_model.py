"""Train a multi-horizon station occupancy model with a time-based split."""

from __future__ import annotations

import argparse
import json
import pickle
import time
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from sklearn.metrics import mean_absolute_error, r2_score
from xgboost import XGBRegressor

from plot_shap_occupancy import (
    CHINA_HOLIDAYS,
    DEFAULT_STATION_DIR,
    DEFAULT_WEATHER_FILE,
    PROJECT_ROOT,
    add_time_features,
    apply_station_profiles,
    build_training_frame,
    fit_station_profiles,
    load_weather,
)
from run_occupancy_poi_experiment import (
    DEFAULT_POI_FILE,
    add_poi_features,
    load_poi_features,
)
from search_neighbor_history_features import (
    NEIGHBOR_PROFILE_FEATURES,
    add_neighbor_features,
    load_station_coordinates,
    neighbor_map_by_k,
)


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "figures"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "models"
DEFAULT_CUTOFF_TIME = pd.Timestamp("2023-01-23 19:05:00")
DEFAULT_NEIGHBOR_K = 5
DEFAULT_MAX_STATIONS = 100
DEFAULT_HORIZONS_MIN = [5, 10, 15, 20, 30, 45, 60, 90, 120]
DEFAULT_MAX_ROWS_PER_HORIZON = 80_000
DEFAULT_BASE_ROWS_PER_STATION = 0

HORIZON_FEATURES = [
    "prediction_horizon_min",
    "horizon_sqrt",
]

CURRENT_TIME_FEATURES = [
    "current_weekday",
    "current_hour_sin",
    "current_hour_cos",
    "current_is_holiday",
    "current_is_morning_peak",
    "current_is_evening_peak",
]

TARGET_TIME_FEATURES = [
    "target_weekday",
    "target_hour_sin",
    "target_hour_cos",
    "target_is_holiday",
    "target_is_morning_peak",
    "target_is_evening_peak",
]

WEATHER_FEATURES = [
    "temperature",
    "humidity",
    "rain",
]

STATION_STATIC_FEATURES = [
    "longitude",
    "latitude",
    "charge_count",
    "TAZID",
]

PRICE_FEATURES = [
    "s_price",
    "e_price",
]

POI_FEATURES = [
    "poi_total_count",
    "poi_lifestyle_services_count",
    "poi_business_residential_count",
    "poi_food_beverage_count",
    "poi_lifestyle_ratio",
    "poi_business_residential_ratio",
    "poi_food_beverage_ratio",
]

HISTORY_PROFILE_FEATURES = [
    "station_avg_occupancy",
    "station_peak_avg_occupancy",
    "station_avg_duration",
    "station_same_hour_occupancy",
    "global_same_hour_occupancy",
]

BASE_CONTEXT_FEATURES = [
    *HORIZON_FEATURES,
    *CURRENT_TIME_FEATURES,
    *TARGET_TIME_FEATURES,
    *WEATHER_FEATURES,
    *STATION_STATIC_FEATURES,
    *PRICE_FEATURES,
    *POI_FEATURES,
    *HISTORY_PROFILE_FEATURES,
    *NEIGHBOR_PROFILE_FEATURES,
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
    "prediction_horizon_min": "Prediction horizon (min)",
    "horizon_sqrt": "Prediction horizon sqrt",
    "current_weekday": "Current weekday",
    "current_hour_sin": "Current hour (sin)",
    "current_hour_cos": "Current hour (cos)",
    "current_is_holiday": "Current holiday",
    "current_is_morning_peak": "Current morning peak",
    "current_is_evening_peak": "Current evening peak",
    "target_weekday": "Target weekday",
    "target_hour_sin": "Target hour (sin)",
    "target_hour_cos": "Target hour (cos)",
    "target_is_holiday": "Target holiday",
    "target_is_morning_peak": "Target morning peak",
    "target_is_evening_peak": "Target evening peak",
    "temperature": "Temperature",
    "humidity": "Humidity",
    "rain": "Rainfall",
    "longitude": "Station longitude",
    "latitude": "Station latitude",
    "charge_count": "Connector count",
    "TAZID": "Traffic zone",
    "s_price": "Service price",
    "e_price": "Energy price",
    "poi_total_count": "Nearby POI count",
    "poi_lifestyle_services_count": "Lifestyle POI count",
    "poi_business_residential_count": "Business/residential POI count",
    "poi_food_beverage_count": "Food/beverage POI count",
    "poi_lifestyle_ratio": "Lifestyle POI ratio",
    "poi_business_residential_ratio": "Business/residential POI ratio",
    "poi_food_beverage_ratio": "Food/beverage POI ratio",
    "station_avg_occupancy": "Station average occupancy",
    "station_peak_avg_occupancy": "Station peak average occupancy",
    "station_avg_duration": "Station average duration",
    "station_same_hour_occupancy": "Station same-hour occupancy",
    "global_same_hour_occupancy": "Global same-hour occupancy",
    "neighbor_count": "Nearby station count",
    "neighbor_avg_distance_m": "Average neighbor distance",
    "neighbor_avg_station_occupancy": "Neighbor average occupancy",
    "neighbor_max_station_occupancy": "Neighbor max occupancy",
    "neighbor_avg_peak_occupancy": "Neighbor peak occupancy",
    "neighbor_avg_duration": "Neighbor average duration",
    "neighbor_avg_charge_count": "Neighbor connector count",
    "neighbor_avg_same_hour_occupancy": "Neighbor same-hour occupancy",
    "neighbor_avg_same_weekday_hour_occupancy": "Neighbor weekday-hour occupancy",
    "occupancy_lag_1": "Previous 5 min occupancy",
    "occupancy_lag_3": "Previous 15 min occupancy",
    "occupancy_lag_6": "Previous 30 min occupancy",
    "occupancy_lag_12": "Previous 60 min occupancy",
    "occupancy_rolling_mean_6": "30 min rolling mean",
    "occupancy_rolling_mean_12": "60 min rolling mean",
    "occupancy_rolling_std_12": "60 min volatility",
    "occupancy_trend_12": "60 min trend",
}

HORIZON_CONTEXT_LAG_FEATURES = [*BASE_CONTEXT_FEATURES, *LAG_FEATURES]

FEATURE_SETS = {
    "horizon_context": BASE_CONTEXT_FEATURES,
    "horizon_lag_only": [*HORIZON_FEATURES, *TARGET_TIME_FEATURES, *LAG_FEATURES],
    "horizon_context_lag_no_station_id": HORIZON_CONTEXT_LAG_FEATURES,
    "horizon_history_core_lag": [
        *HORIZON_FEATURES,
        *TARGET_TIME_FEATURES,
        "station_avg_occupancy",
        "station_peak_avg_occupancy",
        "station_same_hour_occupancy",
        "global_same_hour_occupancy",
        "occupancy_lag_1",
        "occupancy_lag_3",
        "occupancy_lag_6",
        "occupancy_rolling_mean_6",
        "occupancy_rolling_mean_12",
        "occupancy_trend_12",
    ],
}

PREFERRED_FEATURE_SET = "horizon_context_lag_no_station_id"


def load_station_history(
    station_dir: Path,
    tail_rows_per_station: int,
    base_rows_per_station: int,
    horizons_min: list[int],
    max_stations: int | None,
    random_seed: int,
) -> pd.DataFrame:
    files = sorted(p for p in station_dir.glob("*.csv") if p.stem.isdigit())
    if max_stations is not None and max_stations > 0:
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
        df = add_lagged_features(df)
        for horizon_min in horizons_min:
            steps = horizon_min // 5
            df[f"target_occupancy_rate_{horizon_min}"] = df["occupancy_rate"].shift(-steps)
        if base_rows_per_station > 0 and len(df) > base_rows_per_station:
            df = df.sort_values("time").iloc[
                np.linspace(0, len(df) - 1, base_rows_per_station, dtype=int)
            ]
        parts.append(df)

    if not parts:
        raise ValueError(f"No station CSV files found in {station_dir}")
    return pd.concat(parts, ignore_index=True)


def load_station_context(station_dir: Path) -> pd.DataFrame:
    station_info = pd.read_csv(station_dir / "features" / "station_inf.csv")
    required = {"station_id", "longitude", "latitude", "charge_count", "TAZID"}
    missing = required - set(station_info.columns)
    if missing:
        raise ValueError(f"Station info file is missing columns: {sorted(missing)}")
    return station_info[
        ["station_id", "longitude", "latitude", "charge_count", "TAZID"]
    ].copy()


def add_cyclical_time_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    return df


def add_time_features_with_prefix(df: pd.DataFrame, time_column: str, prefix: str) -> pd.DataFrame:
    df = df.copy()
    values = pd.to_datetime(df[time_column])
    hour = values.dt.hour
    df[f"{prefix}_weekday"] = values.dt.dayofweek
    df[f"{prefix}_hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df[f"{prefix}_hour_cos"] = np.cos(2 * np.pi * hour / 24)
    df[f"{prefix}_is_holiday"] = (
        values.dt.strftime("%Y-%m-%d").isin(CHINA_HOLIDAYS).astype(int)
    )
    df[f"{prefix}_is_morning_peak"] = hour.between(7, 9).astype(int)
    df[f"{prefix}_is_evening_peak"] = hour.between(17, 19).astype(int)
    return df


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


def parse_horizons(value: str) -> list[int]:
    horizons = [int(item.strip()) for item in value.split(",") if item.strip()]
    invalid = [item for item in horizons if item <= 0 or item % 5 != 0]
    if invalid:
        raise ValueError(f"Horizons must be positive multiples of 5 minutes: {invalid}")
    return horizons


def add_horizon_targets(
    df: pd.DataFrame,
    horizons_min: list[int],
    max_rows_per_horizon: int,
    random_seed: int,
) -> pd.DataFrame:
    df = df.sort_values(["station_id", "time"]).copy()
    parts = []
    grouped = df.groupby("station_id", group_keys=False)
    for horizon_min in horizons_min:
        steps = horizon_min // 5
        target_column = f"target_occupancy_rate_{horizon_min}"
        if target_column in df.columns:
            target = df[target_column]
        else:
            target = grouped["occupancy_rate"].shift(-steps)
        valid_index = target.dropna().index
        if max_rows_per_horizon > 0 and len(valid_index) > max_rows_per_horizon:
            valid_index = valid_index.to_series().sample(
                max_rows_per_horizon,
                random_state=random_seed + horizon_min,
            ).to_numpy()
        horizon_df = df.loc[valid_index].copy()
        horizon_df["prediction_horizon_min"] = float(horizon_min)
        horizon_df["horizon_sqrt"] = np.sqrt(float(horizon_min))
        horizon_df["target_time"] = horizon_df["time"] + pd.to_timedelta(horizon_min, unit="m")
        horizon_df["target_occupancy_rate"] = target.loc[valid_index].to_numpy()
        parts.append(horizon_df)
    if not parts:
        raise ValueError("No horizon training rows were created.")
    out = pd.concat(parts, ignore_index=True)
    out = add_time_features_with_prefix(out, "time", "current")
    out = add_time_features_with_prefix(out, "target_time", "target")
    return out.reset_index(drop=True)


def build_lagged_frame(args: argparse.Namespace) -> pd.DataFrame:
    weather = load_weather(args.weather_file)
    station_data = load_station_history(
        args.station_dir,
        args.tail_rows_per_station,
        args.base_rows_per_station,
        args.horizons_min,
        args.max_stations,
        args.random_seed,
    )
    station_info = load_station_context(args.station_dir)
    station_data = station_data.merge(station_info, on="station_id", how="left")
    df = build_training_frame(station_data, weather)
    df = add_cyclical_time_features(df)
    df = add_poi_features(df, load_poi_features(args.poi_file))
    return add_horizon_targets(
        df,
        args.horizons_min,
        args.max_rows_per_horizon,
        args.random_seed,
    )


def time_split(df: pd.DataFrame, cutoff_time: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_df = df[df["time"] < cutoff_time].copy()
    test_df = df[df["time"] >= cutoff_time].copy()
    if train_df.empty or test_df.empty:
        raise ValueError("Time split produced an empty train or test set.")
    return train_df, test_df


DEFAULT_MODEL_PARAMS = {
    "n_estimators": 500,
    "max_depth": 5,
    "learning_rate": 0.04,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
}


def normalize_model_params(params: dict[str, Any]) -> dict[str, Any]:
    out = dict(params)
    for key in ["n_estimators", "max_depth", "min_child_weight"]:
        if key in out:
            out[key] = int(out[key])
    for key in ["learning_rate", "subsample", "colsample_bytree", "reg_alpha", "reg_lambda"]:
        if key in out:
            out[key] = float(out[key])
    return out


def load_model_params(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    params = data.get("best_params", data)
    if not isinstance(params, dict):
        raise ValueError(f"Model params file must contain an object or best_params object: {path}")
    return normalize_model_params(params)


def make_model(random_seed: int, model_params: dict[str, Any] | None = None) -> XGBRegressor:
    params = {**DEFAULT_MODEL_PARAMS, **(model_params or {})}
    return XGBRegressor(
        objective="reg:squarederror",
        random_state=random_seed,
        n_jobs=-1,
        **params,
    )


def add_same_hour_profiles(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    global_avg = float(train_df["occupancy_rate"].mean())
    global_hour = train_df.groupby("hour")["occupancy_rate"].mean()
    station_hour = train_df.groupby(["station_id", "hour"])["occupancy_rate"].mean()

    def apply_profiles(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["global_same_hour_occupancy"] = out["hour"].map(global_hour).fillna(global_avg)
        station_keys = pd.MultiIndex.from_frame(out[["station_id", "hour"]])
        out["station_same_hour_occupancy"] = station_hour.reindex(station_keys).to_numpy()
        out["station_same_hour_occupancy"] = out["station_same_hour_occupancy"].fillna(
            out["global_same_hour_occupancy"]
        )
        return out

    return apply_profiles(train_df), apply_profiles(test_df)


def prepare_context_features(
    args: argparse.Namespace,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    profiles = fit_station_profiles(train_df)
    train_df = apply_station_profiles(train_df, profiles)
    test_df = apply_station_profiles(test_df, profiles)
    train_df, test_df = add_same_hour_profiles(train_df, test_df)

    stations = load_station_coordinates(args.station_dir)
    neighbors = neighbor_map_by_k(stations, args.neighbor_k)
    train_df, test_df = add_neighbor_features(train_df, test_df, neighbors)
    return train_df, test_df


def evaluate_feature_set(
    name: str,
    features: list[str],
    df: pd.DataFrame,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    random_seed: int,
    model_params: dict[str, Any] | None = None,
) -> tuple[XGBRegressor, dict[str, object], pd.DataFrame]:
    started = time.perf_counter()
    model = make_model(random_seed, model_params)
    model.fit(train_df[features], train_df["target_occupancy_rate"])
    predictions = np.clip(model.predict(test_df[features]), 0.0, 1.0)

    metrics = {
        "feature_set": name,
        "target": "target_occupancy_rate",
        "features": len(features),
        "rows": len(df),
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "stations": int(df["station_id"].nunique()),
        "mae": float(mean_absolute_error(test_df["target_occupancy_rate"], predictions)),
        "r2": float(r2_score(test_df["target_occupancy_rate"], predictions)),
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


def evaluate_by_horizon(
    model: XGBRegressor,
    test_df: pd.DataFrame,
    features: list[str],
) -> pd.DataFrame:
    predictions = np.clip(model.predict(test_df[features]), 0.0, 1.0)
    rows = []
    scored = test_df[["prediction_horizon_min", "target_occupancy_rate"]].copy()
    scored["prediction"] = predictions
    for horizon_min, group in scored.groupby("prediction_horizon_min"):
        target_mean = float(group["target_occupancy_rate"].mean())
        mae = float(mean_absolute_error(group["target_occupancy_rate"], group["prediction"]))
        rows.append(
            {
                "prediction_horizon_min": float(horizon_min),
                "test_rows": len(group),
                "target_mean": target_mean,
                "mae": mae,
                "relative_mae": float(mae / target_mean) if target_mean > 0 else np.nan,
                "r2": float(r2_score(group["target_occupancy_rate"], group["prediction"])),
            }
        )
    return pd.DataFrame(rows).sort_values("prediction_horizon_min").reset_index(drop=True)


def train_and_evaluate(
    args: argparse.Namespace,
) -> tuple[
    XGBRegressor,
    dict[str, object],
    pd.DataFrame,
    dict[str, object],
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    started = time.perf_counter()
    model_params = load_model_params(args.model_params_file)
    df = build_lagged_frame(args)
    train_df, test_df = time_split(df, pd.Timestamp(args.cutoff_time))
    train_df, test_df = prepare_context_features(args, train_df, test_df)

    rows = []
    importance_parts = []
    models = {}
    for name, features in FEATURE_SETS.items():
        model, row, importance = evaluate_feature_set(
            name,
            features,
            df,
            train_df,
            test_df,
            args.random_seed,
            model_params,
        )
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
    selected_feature_set = (
        args.preferred_feature_set
        if args.preferred_feature_set in models
        else str(metrics_table.iloc[0]["feature_set"])
    )
    model = models[selected_feature_set]
    metrics = metrics_table.loc[
        metrics_table["feature_set"] == selected_feature_set
    ].iloc[0].to_dict()
    metadata = {
        "selected_feature_set": selected_feature_set,
        "best_feature_set_by_r2": str(metrics_table.iloc[0]["feature_set"]),
        "features": FEATURE_SETS[selected_feature_set],
        "feature_sets": FEATURE_SETS,
        "preferred_feature_set": args.preferred_feature_set,
        "target": "target_occupancy_rate",
        "horizons_min": args.horizons_min,
        "horizon_rule": "The target is occupancy_rate at time + prediction_horizon_min. Training labels are built from 5-minute sampled station records.",
        "continuous_horizon_note": "Non-5-minute horizons are continuous estimates within the trained 0-120 minute range, not directly observed labels.",
        "lag_rule": "All lag and rolling occupancy features use shift(1), so each row uses only prior station records at or before the current time.",
        "profile_rule": "Station, same-hour, and neighbor historical profile features are fit on the training split only, then applied to the holdout split.",
        "cutoff_time": pd.Timestamp(args.cutoff_time).isoformat(),
        "neighbor_k": args.neighbor_k,
        "base_rows_per_station": args.base_rows_per_station,
        "max_rows_per_horizon": args.max_rows_per_horizon,
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "model": "XGBRegressor",
        "model_params_file": str(args.model_params_file) if args.model_params_file else None,
        "model_params": model.get_params(),
        "station_dir": str(args.station_dir),
        "weather_file": str(args.weather_file),
        "poi_file": str(args.poi_file),
        "total_elapsed_seconds": time.perf_counter() - started,
    }
    by_horizon = evaluate_by_horizon(model, test_df, FEATURE_SETS[selected_feature_set])
    return (
        model,
        metrics,
        pd.concat(importance_parts, ignore_index=True),
        metadata,
        metrics_table,
        by_horizon,
        test_df,
    )


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
    shap_importance.to_csv(output_dir / "occupancy_horizon_shap_importance.csv", index=False)

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
    ax.set_title("Multi-Horizon Occupancy Model: Feature Impact", fontsize=16, fontweight="bold", color="#172033", pad=14)
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
    fig.savefig(output_dir / "occupancy_horizon_shap_bar.png", dpi=240)
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
    plt.title("Multi-Horizon Occupancy Model: SHAP Summary", fontsize=16, fontweight="bold", color="#172033", pad=12)
    plt.tight_layout()
    fig.savefig(output_dir / "occupancy_horizon_shap_summary.png", dpi=240, bbox_inches="tight")
    plt.close(fig)


def save_outputs(
    model: XGBRegressor,
    metrics: dict[str, object],
    importance: pd.DataFrame,
    metadata: dict[str, object],
    metrics_table: pd.DataFrame,
    by_horizon: pd.DataFrame,
    test_df: pd.DataFrame,
    output_dir: Path,
    model_dir: Path,
    shap_sample_size: int,
    random_seed: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)

    with (model_dir / "occupancy_horizon_xgboost.pkl").open("wb") as file:
        pickle.dump(model, file)
    with (model_dir / "occupancy_horizon_features.json").open("w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=2)

    pd.DataFrame([metrics]).to_csv(output_dir / "occupancy_horizon_model_metrics.csv", index=False)
    metrics_table.to_csv(output_dir / "occupancy_horizon_feature_set_metrics.csv", index=False)
    by_horizon.to_csv(output_dir / "occupancy_horizon_by_horizon_metrics.csv", index=False)
    importance.to_csv(output_dir / "occupancy_horizon_feature_importance.csv", index=False)
    shap_sample, shap_values, shap_importance = compute_shap_summary(
        model,
        test_df,
        metadata["features"],
        shap_sample_size,
        random_seed,
    )
    save_shap_plots(shap_sample, shap_values, shap_importance, metrics, output_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train multi-horizon station occupancy model.")
    parser.add_argument("--station-dir", type=Path, default=DEFAULT_STATION_DIR)
    parser.add_argument("--weather-file", type=Path, default=DEFAULT_WEATHER_FILE)
    parser.add_argument("--poi-file", type=Path, default=DEFAULT_POI_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument(
        "--model-params-file",
        type=Path,
        default=None,
        help="Optional JSON file containing best_params from the tuning script.",
    )
    parser.add_argument("--cutoff-time", type=str, default=DEFAULT_CUTOFF_TIME.isoformat())
    parser.add_argument("--tail-rows-per-station", type=int, default=0)
    parser.add_argument(
        "--base-rows-per-station",
        type=int,
        default=DEFAULT_BASE_ROWS_PER_STATION,
        help="Evenly sample this many lag-ready rows per station before horizon expansion; use 0 for all rows.",
    )
    parser.add_argument("--max-stations", type=int, default=DEFAULT_MAX_STATIONS)
    parser.add_argument("--neighbor-k", type=int, default=DEFAULT_NEIGHBOR_K)
    parser.add_argument("--preferred-feature-set", type=str, default=PREFERRED_FEATURE_SET)
    parser.add_argument(
        "--horizons-min",
        type=parse_horizons,
        default=DEFAULT_HORIZONS_MIN,
        help="Comma-separated positive 5-minute horizons used to build training labels.",
    )
    parser.add_argument(
        "--max-rows-per-horizon",
        type=int,
        default=DEFAULT_MAX_ROWS_PER_HORIZON,
        help="Sample at most this many rows per horizon; use 0 for all rows.",
    )
    parser.add_argument("--shap-sample-size", type=int, default=5000)
    parser.add_argument("--random-seed", type=int, default=42)
    return parser.parse_args()


def validate_arbitrary_horizon_predictions(
    model: XGBRegressor,
    test_df: pd.DataFrame,
    features: list[str],
    horizons_min: list[float],
    random_seed: int,
) -> pd.DataFrame:
    if test_df.empty:
        return pd.DataFrame()
    base = test_df.sample(1, random_state=random_seed).iloc[0].copy()
    rows = []
    for horizon_min in horizons_min:
        sample = base.copy()
        sample["prediction_horizon_min"] = float(horizon_min)
        sample["horizon_sqrt"] = np.sqrt(float(horizon_min))
        target_time = pd.Timestamp(sample["time"]) + pd.to_timedelta(float(horizon_min), unit="m")
        target_frame = pd.DataFrame([{"target_time": target_time}])
        target_frame = add_time_features_with_prefix(target_frame, "target_time", "target")
        for column in TARGET_TIME_FEATURES:
            sample[column] = target_frame.iloc[0][column]
        x = pd.DataFrame([sample])[features]
        prediction = float(np.clip(model.predict(x)[0], 0.0, 1.0))
        rows.append(
            {
                "station_id": int(sample["station_id"]),
                "current_time": pd.Timestamp(sample["time"]).isoformat(),
                "prediction_horizon_min": float(horizon_min),
                "target_time": target_time.isoformat(),
                "predicted_occupancy_rate": prediction,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()
    model, metrics, importance, metadata, metrics_table, by_horizon, test_df = train_and_evaluate(args)
    save_outputs(
        model,
        metrics,
        importance,
        metadata,
        metrics_table,
        by_horizon,
        test_df,
        args.output_dir,
        args.model_dir,
        args.shap_sample_size,
        args.random_seed,
    )
    print(metrics_table.to_string(index=False))
    print("\nBy horizon:")
    print(by_horizon.to_string(index=False))
    print("\nSelected feature set:", metadata["selected_feature_set"])
    selected_importance = importance[
        importance["feature_set"] == metadata["selected_feature_set"]
    ]
    print(selected_importance.head(20).to_string(index=False))
    arbitrary = validate_arbitrary_horizon_predictions(
        model,
        test_df,
        metadata["features"],
        [3.5, 7.0, 19.0, 120.0],
        args.random_seed,
    )
    print("\nArbitrary horizon smoke predictions:")
    print(arbitrary.to_string(index=False))


if __name__ == "__main__":
    main()
