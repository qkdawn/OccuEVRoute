"""Extract the compact occupancy dataset required by the demo runtime."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_STATION_DIR = (
    PROJECT_ROOT
    / "ML"
    / "Data"
    / "UrbanEVDataset"
    / "UrbanEVDataset"
    / "20220901-20230228_station-processed"
)
SOURCE_WEATHER_FILE = (
    PROJECT_ROOT
    / "ML"
    / "Data"
    / "UrbanEVSupplemental"
    / "UrbanEVSupplemental"
    / "20220901-20230228_weather_central.csv"
)
STATION_ACCESS_FILE = PROJECT_ROOT / "data" / "processed" / "station_road_access.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "runtime" / "occupancy_week"
RUNTIME_START = pd.Timestamp("2023-02-06 00:00:00")
RUNTIME_END = pd.Timestamp("2023-02-12 23:55:00")
LAG_START = RUNTIME_START - pd.Timedelta(minutes=55)
PROFILE_CUTOFF = pd.Timestamp("2023-01-23 19:05:00")
STATION_COLUMNS = ["time", "busy", "idle", "s_price", "e_price", "duration"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract the one-week occupancy runtime bundle.")
    parser.add_argument("--source-station-dir", type=Path, default=SOURCE_STATION_DIR)
    parser.add_argument("--source-weather-file", type=Path, default=SOURCE_WEATHER_FILE)
    parser.add_argument("--station-access-file", type=Path, default=STATION_ACCESS_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    station_ids = _station_ids(args.station_access_file)
    station_output_dir = args.output_dir / "station-processed"
    features_output_dir = station_output_dir / "features"
    if args.output_dir.exists():
        shutil.rmtree(args.output_dir)
    features_output_dir.mkdir(parents=True, exist_ok=True)

    _write_station_info(args.source_station_dir, features_output_dir, station_ids)
    profiles = []
    written_stations = 0
    for station_id in station_ids:
        source_file = args.source_station_dir / f"{station_id}.csv"
        if not source_file.exists():
            continue
        frame = pd.read_csv(source_file, usecols=STATION_COLUMNS)
        frame["time"] = pd.to_datetime(frame["time"])
        runtime = frame[(frame["time"] >= LAG_START) & (frame["time"] <= RUNTIME_END)].copy()
        if runtime.empty:
            continue
        runtime.to_csv(station_output_dir / f"{station_id}.csv.gz", index=False, compression="gzip")
        written_stations += 1
        profiles.extend(_station_profile_rows(station_id, frame))

    pd.DataFrame(profiles).to_csv(features_output_dir / "station_profiles.csv", index=False)
    _write_weather(args.source_weather_file, args.output_dir)
    print(f"wrote {written_stations} station files to {station_output_dir}")


def _station_ids(path: Path) -> list[int]:
    access = pd.read_csv(path, usecols=["station_id"])
    return sorted(access["station_id"].dropna().astype(int).unique().tolist())


def _write_station_info(source_station_dir: Path, output_dir: Path, station_ids: list[int]) -> None:
    station_info = pd.read_csv(source_station_dir / "features" / "station_inf.csv")
    station_info = station_info[station_info["station_id"].isin(station_ids)].copy()
    station_info.to_csv(output_dir / "station_inf.csv", index=False)


def _write_weather(source_weather_file: Path, output_dir: Path) -> None:
    weather = pd.read_csv(source_weather_file)
    weather_time = pd.to_datetime(weather["time"])
    weather = weather[(weather_time >= RUNTIME_START.floor("h")) & (weather_time <= RUNTIME_END.ceil("h"))].copy()
    weather.to_csv(output_dir / "weather_central.csv", index=False)


def _station_profile_rows(station_id: int, frame: pd.DataFrame) -> list[dict[str, float | int]]:
    denominator = frame["busy"] + frame["idle"]
    train = frame[(frame["time"] < PROFILE_CUTOFF) & (denominator > 0)].copy()
    if train.empty:
        return []
    train["occupancy_rate"] = train["busy"] / (train["busy"] + train["idle"])
    train["duration"] = pd.to_numeric(train["duration"], errors="coerce").fillna(0.0)
    train["hour"] = train["time"].dt.hour
    train["weekday"] = train["time"].dt.dayofweek
    train["is_morning_peak"] = train["hour"].between(7, 9)
    train["is_evening_peak"] = train["hour"].between(17, 19)

    avg = float(train["occupancy_rate"].mean())
    peak = train[train["is_morning_peak"] | train["is_evening_peak"]]
    peak_avg = float(peak["occupancy_rate"].mean()) if not peak.empty else avg
    duration_avg = float(train["duration"].mean())
    rows: list[dict[str, float | int]] = []
    for hour in range(24):
        same_hour = train[train["hour"] == hour]
        hour_avg = float(same_hour["occupancy_rate"].mean()) if not same_hour.empty else avg
        rows.append(_profile_row(station_id, hour, -1, avg, peak_avg, duration_avg, hour_avg, hour_avg))
        for weekday in range(7):
            same_weekday_hour = same_hour[same_hour["weekday"] == weekday]
            weekday_hour_avg = float(same_weekday_hour["occupancy_rate"].mean()) if not same_weekday_hour.empty else hour_avg
            rows.append(_profile_row(station_id, hour, weekday, avg, peak_avg, duration_avg, hour_avg, weekday_hour_avg))
    return rows


def _profile_row(
    station_id: int,
    hour: int,
    weekday: int,
    avg: float,
    peak_avg: float,
    duration_avg: float,
    hour_avg: float,
    weekday_hour_avg: float,
) -> dict[str, float | int]:
    return {
        "station_id": station_id,
        "hour": hour,
        "weekday": weekday,
        "station_avg_occupancy": avg,
        "station_peak_avg_occupancy": peak_avg,
        "station_avg_duration": duration_avg,
        "station_same_hour_occupancy": hour_avg,
        "station_same_weekday_hour_occupancy": weekday_hour_avg,
        "global_same_hour_occupancy": hour_avg,
    }


if __name__ == "__main__":
    main()
