"""Train an occupancy model and plot SHAP feature importance.

This script answers a narrow question for the project report:
is `month` important compared with weekday, clock time, weather, and station id?

It predicts occupancy_rate = busy / (busy + idle) using a balanced sample from
station-level 5-minute data, joins hourly central weather, then saves SHAP plots.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from xgboost import XGBRegressor


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATION_DIR = (
    PROJECT_ROOT
    / "ML"
    / "Data"
    / "UrbanEVDataset"
    / "UrbanEVDataset"
    / "20220901-20230228_station-processed"
)
DEFAULT_WEATHER_FILE = (
    PROJECT_ROOT
    / "ML"
    / "Data"
    / "UrbanEVSupplemental"
    / "UrbanEVSupplemental"
    / "20220901-20230228_weather_central.csv"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "figures"

FEATURES = [
    "station_id",
    "weekday",
    "hour",
    "minute",
    "is_weekend",
    "month",
    "temperature",
    "humidity",
    "rain",
    "charge_count",
    "s_price",
    "e_price",
]


def load_weather(weather_file: Path) -> pd.DataFrame:
    weather = pd.read_csv(weather_file)
    weather["weather_hour"] = pd.to_datetime(weather["time"]).dt.floor("h")
    weather = weather.rename(
        columns={
            "T": "temperature",
            "U": "humidity",
            "RAIN": "rain",
        }
    )
    return weather[["weather_hour", "temperature", "humidity", "rain"]]


def load_station_sample(
    station_dir: Path,
    rows_per_station: int,
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
            usecols=["time", "busy", "idle", "s_price", "e_price"],
        )
        if rows_per_station > 0 and len(df) > rows_per_station:
            df = df.sample(rows_per_station, random_state=random_seed + station_id)
        df["station_id"] = station_id
        parts.append(df)

    if not parts:
        raise ValueError(f"No station CSV files found in {station_dir}")
    return pd.concat(parts, ignore_index=True)


def load_station_info(station_dir: Path) -> pd.DataFrame:
    station_info = pd.read_csv(station_dir / "features" / "station_inf.csv")
    return station_info[["station_id", "charge_count"]]


def build_training_frame(station_data: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    df = station_data.copy()
    df["time"] = pd.to_datetime(df["time"])
    denominator = df["busy"] + df["idle"]
    df = df[denominator > 0].copy()
    df["occupancy_rate"] = df["busy"] / (df["busy"] + df["idle"])

    df["weekday"] = df["time"].dt.dayofweek
    df["hour"] = df["time"].dt.hour
    df["minute"] = df["time"].dt.minute
    df["is_weekend"] = (df["weekday"] >= 5).astype(int)
    df["month"] = df["time"].dt.month
    df["weather_hour"] = df["time"].dt.floor("h")

    df = df.merge(weather, on="weather_hour", how="left")
    df[["temperature", "humidity", "rain"]] = df[
        ["temperature", "humidity", "rain"]
    ].ffill().bfill()
    return df.dropna(subset=FEATURES + ["occupancy_rate"])


def train_model(df: pd.DataFrame, random_seed: int):
    x = df[FEATURES]
    y = df["occupancy_rate"]
    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.25,
        random_state=random_seed,
    )
    model = XGBRegressor(
        objective="reg:squarederror",
        n_estimators=300,
        max_depth=5,
        learning_rate=0.06,
        subsample=0.85,
        colsample_bytree=0.85,
        random_state=random_seed,
        n_jobs=-1,
    )
    model.fit(x_train, y_train)
    pred = model.predict(x_test)
    metrics = {
        "rows": len(df),
        "stations": int(df["station_id"].nunique()),
        "months": ",".join(str(m) for m in sorted(df["month"].unique())),
        "mae": float(mean_absolute_error(y_test, pred)),
        "r2": float(r2_score(y_test, pred)),
    }
    return model, x_test, metrics


def compute_shap(model, x_test: pd.DataFrame, shap_sample_size: int, random_seed: int):
    sample_size = min(shap_sample_size, len(x_test))
    x_sample = x_test.sample(sample_size, random_state=random_seed)
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(x_sample)
    shap_values = np.asarray(shap_values)
    importance = (
        pd.DataFrame(
            {
                "feature": x_sample.columns,
                "mean_abs_shap": np.abs(shap_values).mean(axis=0),
            }
        )
        .sort_values("mean_abs_shap", ascending=False)
        .reset_index(drop=True)
    )
    return x_sample, shap_values, importance


def save_plots(
    x_sample: pd.DataFrame,
    shap_values: np.ndarray,
    importance: pd.DataFrame,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(8, 5))
    order = importance.sort_values("mean_abs_shap", ascending=True)
    plt.barh(order["feature"], order["mean_abs_shap"], color="#4C78A8")
    plt.xlabel("Mean absolute SHAP value")
    plt.title("SHAP Feature Importance for Occupancy Prediction")
    plt.tight_layout()
    plt.savefig(output_dir / "shap_feature_importance.png", dpi=220)
    plt.close()

    shap.summary_plot(shap_values, x_sample, show=False, max_display=len(FEATURES))
    plt.tight_layout()
    plt.savefig(output_dir / "shap_summary.png", dpi=220, bbox_inches="tight")
    plt.close()

    importance.to_csv(output_dir / "shap_feature_importance.csv", index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot SHAP importance for occupancy model.")
    parser.add_argument("--station-dir", type=Path, default=DEFAULT_STATION_DIR)
    parser.add_argument("--weather-file", type=Path, default=DEFAULT_WEATHER_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--rows-per-station", type=int, default=250)
    parser.add_argument("--max-stations", type=int, default=None)
    parser.add_argument("--shap-sample-size", type=int, default=3000)
    parser.add_argument("--random-seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
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
    model, x_test, metrics = train_model(df, args.random_seed)
    x_sample, shap_values, importance = compute_shap(
        model,
        x_test,
        args.shap_sample_size,
        args.random_seed,
    )
    save_plots(x_sample, shap_values, importance, args.output_dir)

    pd.DataFrame([metrics]).to_csv(args.output_dir / "shap_model_metrics.csv", index=False)
    print("Saved SHAP outputs to:", args.output_dir)
    print("Model metrics:", metrics)
    print(importance.to_string(index=False))


if __name__ == "__main__":
    main()
