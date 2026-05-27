"""Historical-time occupancy prediction for recommendation ranking.

The API treats a timestamp after the model cutoff as the demo's "now". That
keeps prediction deployable without live charger or weather APIs: current
state, lag features, price, weather, and station profiles all come from the
UrbanEV history already bundled with the project.
"""

from __future__ import annotations

import json
import math
import pickle
from datetime import datetime
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FULL_STATION_DIR = (
    PROJECT_ROOT
    / "ML"
    / "Data"
    / "UrbanEVDataset"
    / "UrbanEVDataset"
    / "20220901-20230228_station-processed"
)
FULL_WEATHER_FILE = (
    PROJECT_ROOT
    / "ML"
    / "Data"
    / "UrbanEVSupplemental"
    / "UrbanEVSupplemental"
    / "20220901-20230228_weather_central.csv"
)
RUNTIME_OCCUPANCY_DIR = PROJECT_ROOT / "data" / "runtime" / "occupancy_week"
DEFAULT_STATION_DIR = RUNTIME_OCCUPANCY_DIR / "station-processed"
DEFAULT_WEATHER_FILE = RUNTIME_OCCUPANCY_DIR / "weather_central.csv"
DEFAULT_MODEL_FILE = PROJECT_ROOT / "models" / "occupancy_horizon_xgboost.pkl"
DEFAULT_FEATURE_FILE = PROJECT_ROOT / "models" / "occupancy_horizon_features.json"
DEFAULT_POI_FILE = PROJECT_ROOT / "data" / "processed" / "station_poi_features.csv"
DEFAULT_SIMULATION_WEEK_START = pd.Timestamp("2023-02-06 00:00:00")
DEFAULT_SIMULATION_WEEK_END = pd.Timestamp("2023-02-12 23:55:00")
DEFAULT_CUTOFF_TIME = pd.Timestamp("2023-01-23 19:05:00")
DEFAULT_NEIGHBOR_K = 5
MIN_HORIZON_MIN = 5.0
MAX_HORIZON_MIN = 120.0
EARTH_RADIUS_M = 6_371_008.8
CHINA_HOLIDAYS = {
    "2022-09-10",
    "2022-09-11",
    "2022-09-12",
    "2022-10-01",
    "2022-10-02",
    "2022-10-03",
    "2022-10-04",
    "2022-10-05",
    "2022-10-06",
    "2022-10-07",
    "2022-12-31",
    "2023-01-01",
    "2023-01-02",
    "2023-01-21",
    "2023-01-22",
    "2023-01-23",
    "2023-01-24",
    "2023-01-25",
    "2023-01-26",
    "2023-01-27",
}


@dataclass(frozen=True)
class OccupancyPrediction:
    predicted_occupancy_rate: float | None
    prediction_horizon_min: float | None
    prediction_time: str | None
    prediction_source: str


class HistoricalOccupancyPredictor:
    """Predict future occupancy using historical UrbanEV rows as demo state."""

    def __init__(
        self,
        model_file: Path = DEFAULT_MODEL_FILE,
        feature_file: Path = DEFAULT_FEATURE_FILE,
        station_dir: Path = DEFAULT_STATION_DIR,
        weather_file: Path = DEFAULT_WEATHER_FILE,
        poi_file: Path = DEFAULT_POI_FILE,
        simulated_now: pd.Timestamp | None = None,
        cutoff_time: pd.Timestamp = DEFAULT_CUTOFF_TIME,
        neighbor_k: int = DEFAULT_NEIGHBOR_K,
    ) -> None:
        self.model_file = model_file
        self.feature_file = feature_file
        self.station_dir = station_dir
        self.weather_file = weather_file
        self.poi_file = poi_file
        self.simulated_now = simulated_now
        self.cutoff_time = cutoff_time
        self.neighbor_k = neighbor_k
        self._model: Any | None = None
        self._features: list[str] | None = None
        self._weather: pd.DataFrame | None = None
        self._poi: pd.DataFrame | None = None
        self._neighbors: dict[int, list[tuple[int, float]]] | None = None

    @property
    def available(self) -> bool:
        return self.model_file.exists() and self.feature_file.exists() and self.station_dir.exists()

    def predict(
        self,
        station_ids: list[int],
        drive_times_min: list[float | None],
        simulated_now: pd.Timestamp | None = None,
    ) -> dict[int, OccupancyPrediction]:
        if not self.available:
            raise FileNotFoundError(
                "Occupancy model artifacts are required for recommendations. "
                f"Missing one of: {self.model_file}, {self.feature_file}, {self.station_dir}."
            )
        now = pd.Timestamp(simulated_now or self.simulated_now or historical_now())
        rows: list[dict[str, float]] = []
        row_station_ids: list[int] = []
        horizons: list[float] = []
        for station_id, drive_time_min in zip(station_ids, drive_times_min):
            if drive_time_min is None or not math.isfinite(float(drive_time_min)):
                continue
            horizon_min = _bounded_horizon(float(drive_time_min))
            row = self._feature_row(station_id, now, horizon_min)
            if row is None:
                continue
            rows.append(row)
            row_station_ids.append(station_id)
            horizons.append(horizon_min)

        predictions = {
            station_id: OccupancyPrediction(None, None, None, "insufficient_history")
            for station_id in station_ids
        }
        if not rows:
            return predictions

        features = self._load_features()
        frame = pd.DataFrame(rows).reindex(columns=features).fillna(0.0)
        values = np.clip(self._load_model().predict(frame), 0.0, 1.0)
        for station_id, horizon_min, value in zip(row_station_ids, horizons, values):
            target_time = now + pd.to_timedelta(horizon_min, unit="m")
            predictions[station_id] = OccupancyPrediction(
                predicted_occupancy_rate=float(value),
                prediction_horizon_min=float(horizon_min),
                prediction_time=target_time.isoformat(),
                prediction_source="historical_urbanev",
            )
        return predictions

    def warmup(
        self,
        station_ids: Sequence[int],
        drive_times_min: Sequence[float | None],
        simulated_now: pd.Timestamp | None = None,
    ) -> None:
        """Populate the lazy caches used by the first real prediction call."""
        if not self.available:
            return
        now = pd.Timestamp(simulated_now or self.simulated_now or historical_now())
        self._load_features()
        self._load_model()
        self._weather_at(now)
        if self._poi is None:
            self._poi = _load_poi_features(self.poi_file)
        if self._neighbors is None:
            stations = _station_coordinates(self.station_dir)
            self._neighbors = _neighbor_map_by_k(stations, self.neighbor_k)
        for station_id, drive_time_min in zip(station_ids, drive_times_min):
            if drive_time_min is None or not math.isfinite(float(drive_time_min)):
                continue
            self._feature_row(int(station_id), now, _bounded_horizon(float(drive_time_min)))

    def _feature_row(self, station_id: int, now: pd.Timestamp, horizon_min: float) -> dict[str, float] | None:
        current = _station_state(self.station_dir, station_id, now)
        if current is None:
            return None
        station_context = _station_context(self.station_dir, station_id)
        if station_context is None:
            return None

        target_time = now + pd.to_timedelta(horizon_min, unit="m")
        row: dict[str, float] = {
            "prediction_horizon_min": horizon_min,
            "horizon_sqrt": float(np.sqrt(horizon_min)),
            **_prefixed_time_features(now, "current"),
            **_prefixed_time_features(target_time, "target"),
            **self._weather_at(now),
            **station_context,
            **self._poi_features(station_id),
            **_station_profiles(self.station_dir, station_id, self.cutoff_time, int(now.hour)),
            **current,
            **self._neighbor_features(station_id, int(now.dayofweek), int(now.hour)),
        }
        return row

    def _load_model(self) -> Any:
        if self._model is None:
            with self.model_file.open("rb") as file:
                self._model = pickle.load(file)
        return self._model

    def _load_features(self) -> list[str]:
        if self._features is None:
            with self.feature_file.open("r", encoding="utf-8") as file:
                metadata = json.load(file)
            self._features = list(metadata["features"])
        return self._features

    def _weather_at(self, now: pd.Timestamp) -> dict[str, float]:
        if self._weather is None:
            self._weather = _load_weather(self.weather_file).sort_values("weather_hour")
        hour = now.floor("h")
        weather = self._weather[self._weather["weather_hour"] <= hour].tail(1)
        if weather.empty:
            weather = self._weather.head(1)
        row = weather.iloc[0]
        return {
            "temperature": float(row["temperature"]),
            "humidity": float(row["humidity"]),
            "rain": float(row["rain"]),
        }

    def _poi_features(self, station_id: int) -> dict[str, float]:
        if self._poi is None:
            self._poi = _load_poi_features(self.poi_file)
        match = self._poi[self._poi["station_id"] == station_id]
        if match.empty:
            return {
                "poi_total_count": 0.0,
                "poi_lifestyle_services_count": 0.0,
                "poi_business_residential_count": 0.0,
                "poi_food_beverage_count": 0.0,
                "poi_lifestyle_ratio": 0.0,
                "poi_business_residential_ratio": 0.0,
                "poi_food_beverage_ratio": 0.0,
            }
        row = match.iloc[0]
        return {column: float(row[column]) for column in match.columns if column != "station_id"}

    def _neighbor_features(self, station_id: int, weekday: int, hour: int) -> dict[str, float]:
        if self._neighbors is None:
            stations = _station_coordinates(self.station_dir)
            self._neighbors = _neighbor_map_by_k(stations, self.neighbor_k)
        neighbors = self._neighbors.get(station_id, [])
        profiles = [
            _station_profiles(self.station_dir, neighbor_id, self.cutoff_time, hour, weekday)
            for neighbor_id, _ in neighbors
        ]
        distances = [distance for _, distance in neighbors]
        return {
            "neighbor_count": float(len(neighbors)),
            "neighbor_avg_distance_m": _mean(distances, 0.0),
            "neighbor_avg_station_occupancy": _profile_mean(profiles, "station_avg_occupancy"),
            "neighbor_max_station_occupancy": _profile_max(profiles, "station_avg_occupancy"),
            "neighbor_avg_peak_occupancy": _profile_mean(profiles, "station_peak_avg_occupancy"),
            "neighbor_avg_duration": _profile_mean(profiles, "station_avg_duration"),
            "neighbor_avg_charge_count": _mean(
                [_station_context(self.station_dir, neighbor_id).get("charge_count", np.nan) for neighbor_id, _ in neighbors],
                0.0,
            ),
            "neighbor_avg_same_hour_occupancy": _profile_mean(profiles, "station_same_hour_occupancy"),
            "neighbor_avg_same_weekday_hour_occupancy": _profile_mean(
                profiles,
                "station_same_weekday_hour_occupancy",
                fallback_key="station_same_hour_occupancy",
            ),
        }


@lru_cache(maxsize=1)
def get_historical_occupancy_predictor() -> HistoricalOccupancyPredictor:
    return HistoricalOccupancyPredictor()


def historical_now(current_time: datetime | pd.Timestamp | None = None) -> pd.Timestamp:
    """Map the real clock's weekday/hour/minute onto one stable 2023 demo week."""
    current = pd.Timestamp(current_time or datetime.now())
    minute = int(current.minute // 5 * 5)
    base_date = DEFAULT_SIMULATION_WEEK_START.normalize() + pd.Timedelta(days=int(current.dayofweek))
    simulated = base_date + pd.Timedelta(hours=int(current.hour), minutes=minute)
    return min(max(simulated, DEFAULT_SIMULATION_WEEK_START), DEFAULT_SIMULATION_WEEK_END)


def _bounded_horizon(drive_time_min: float) -> float:
    return min(MAX_HORIZON_MIN, max(MIN_HORIZON_MIN, drive_time_min))


def _prefixed_time_features(value: pd.Timestamp, prefix: str) -> dict[str, float]:
    hour = int(value.hour)
    return {
        f"{prefix}_weekday": float(value.dayofweek),
        f"{prefix}_hour_sin": float(np.sin(2 * np.pi * hour / 24)),
        f"{prefix}_hour_cos": float(np.cos(2 * np.pi * hour / 24)),
        f"{prefix}_is_holiday": float(value.strftime("%Y-%m-%d") in CHINA_HOLIDAYS),
        f"{prefix}_is_morning_peak": float(7 <= hour <= 9),
        f"{prefix}_is_evening_peak": float(17 <= hour <= 19),
    }


@lru_cache(maxsize=2048)
def _station_frame(station_dir: Path, station_id: int) -> pd.DataFrame:
    path = station_dir / f"{station_id}.csv"
    if not path.exists():
        path = station_dir / f"{station_id}.csv.gz"
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(
        path,
        usecols=["time", "busy", "idle", "s_price", "e_price", "duration"],
    )
    frame["time"] = pd.to_datetime(frame["time"])
    denominator = frame["busy"] + frame["idle"]
    frame = frame[denominator > 0].copy()
    frame["occupancy_rate"] = frame["busy"] / denominator
    frame["duration"] = pd.to_numeric(frame["duration"], errors="coerce").fillna(0.0)
    frame["hour"] = frame["time"].dt.hour
    frame["weekday"] = frame["time"].dt.dayofweek
    frame["is_morning_peak"] = frame["hour"].between(7, 9).astype(int)
    frame["is_evening_peak"] = frame["hour"].between(17, 19).astype(int)
    return frame.sort_values("time").reset_index(drop=True)


def _station_state(station_dir: Path, station_id: int, now: pd.Timestamp) -> dict[str, float] | None:
    frame = _station_frame(station_dir, station_id)
    if frame.empty:
        return None
    history = frame[frame["time"] <= now.floor("5min")].tail(12)
    if len(history) < 12:
        return None
    occupancy = history["occupancy_rate"].to_numpy(dtype=float)
    current = history.iloc[-1]
    shifted = occupancy[:-1]
    return {
        "s_price": float(current["s_price"]),
        "e_price": float(current["e_price"]),
        "occupancy_lag_1": float(occupancy[-2]),
        "occupancy_lag_3": float(occupancy[-4]),
        "occupancy_lag_6": float(occupancy[-7]),
        "occupancy_lag_12": float(occupancy[0]),
        "occupancy_rolling_mean_6": float(np.mean(shifted[-6:])),
        "occupancy_rolling_mean_12": float(np.mean(shifted)),
        "occupancy_rolling_std_12": float(np.std(shifted, ddof=1)) if len(shifted) > 1 else 0.0,
        "occupancy_trend_12": float(occupancy[-2] - occupancy[0]),
    }


@lru_cache(maxsize=1)
def _station_info(station_dir: Path) -> pd.DataFrame:
    return pd.read_csv(station_dir / "features" / "station_inf.csv")


def _station_context(station_dir: Path, station_id: int) -> dict[str, float] | None:
    info = _station_info(station_dir)
    match = info[info["station_id"] == station_id]
    if match.empty:
        return None
    row = match.iloc[0]
    return {
        "longitude": float(row["longitude"]),
        "latitude": float(row["latitude"]),
        "charge_count": float(row["charge_count"]),
        "TAZID": float(row["TAZID"]),
    }


@lru_cache(maxsize=1)
def _station_coordinates(station_dir: Path) -> pd.DataFrame:
    info = _station_info(station_dir)
    return (
        info[["station_id", "latitude", "longitude"]]
        .drop_duplicates("station_id")
        .sort_values("station_id")
        .reset_index(drop=True)
    )


@lru_cache(maxsize=4096)
def _station_profiles(
    station_dir: Path,
    station_id: int,
    cutoff_time: pd.Timestamp,
    hour: int,
    weekday: int | None = None,
) -> dict[str, float]:
    precomputed = _precomputed_station_profile(station_dir, station_id, hour, weekday)
    if precomputed is not None:
        return precomputed

    frame = _station_frame(station_dir, station_id)
    train = frame[frame["time"] < cutoff_time]
    if train.empty:
        return {
            "station_avg_occupancy": 0.0,
            "station_peak_avg_occupancy": 0.0,
            "station_avg_duration": 0.0,
            "station_same_hour_occupancy": 0.0,
            "station_same_weekday_hour_occupancy": 0.0,
            "global_same_hour_occupancy": 0.0,
        }
    peak = train[(train["is_morning_peak"] == 1) | (train["is_evening_peak"] == 1)]
    same_hour = train[train["hour"] == hour]
    if weekday is None:
        same_weekday_hour = same_hour
    else:
        same_weekday_hour = same_hour[same_hour["weekday"] == weekday]
    avg = float(train["occupancy_rate"].mean())
    hour_avg = float(same_hour["occupancy_rate"].mean()) if not same_hour.empty else avg
    return {
        "station_avg_occupancy": avg,
        "station_peak_avg_occupancy": float(peak["occupancy_rate"].mean()) if not peak.empty else avg,
        "station_avg_duration": float(train["duration"].mean()),
        "station_same_hour_occupancy": hour_avg,
        "station_same_weekday_hour_occupancy": float(same_weekday_hour["occupancy_rate"].mean())
        if not same_weekday_hour.empty
        else hour_avg,
        "global_same_hour_occupancy": hour_avg,
    }


@lru_cache(maxsize=4096)
def _precomputed_station_profile(
    station_dir: Path,
    station_id: int,
    hour: int,
    weekday: int | None,
) -> dict[str, float] | None:
    profiles_file = station_dir / "features" / "station_profiles.csv"
    if not profiles_file.exists():
        return None
    profiles = _station_profile_table(profiles_file)
    profile_weekday = -1 if weekday is None else int(weekday)
    match = profiles[
        (profiles["station_id"] == int(station_id))
        & (profiles["hour"] == int(hour))
        & (profiles["weekday"] == profile_weekday)
    ]
    if match.empty:
        return None
    row = match.iloc[0]
    return {
        "station_avg_occupancy": float(row["station_avg_occupancy"]),
        "station_peak_avg_occupancy": float(row["station_peak_avg_occupancy"]),
        "station_avg_duration": float(row["station_avg_duration"]),
        "station_same_hour_occupancy": float(row["station_same_hour_occupancy"]),
        "station_same_weekday_hour_occupancy": float(row["station_same_weekday_hour_occupancy"]),
        "global_same_hour_occupancy": float(row["global_same_hour_occupancy"]),
    }


@lru_cache(maxsize=4)
def _station_profile_table(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def _load_poi_features(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame({"station_id": []})
    poi = pd.read_csv(path)
    total = poi["poi_total_count"].replace(0, np.nan)
    poi["poi_lifestyle_ratio"] = poi["poi_lifestyle_services_count"] / total
    poi["poi_business_residential_ratio"] = poi["poi_business_residential_count"] / total
    poi["poi_food_beverage_ratio"] = poi["poi_food_beverage_count"] / total
    return poi.fillna(0.0)


def _load_weather(path: Path) -> pd.DataFrame:
    weather = pd.read_csv(path)
    weather["weather_hour"] = pd.to_datetime(weather["time"]).dt.floor("h")
    weather = weather.rename(columns={"T": "temperature", "U": "humidity", "RAIN": "rain"})
    return weather[["weather_hour", "temperature", "humidity", "rain"]]


def _neighbor_map_by_k(stations: pd.DataFrame, k: int) -> dict[int, list[tuple[int, float]]]:
    station_rows = stations[["station_id", "latitude", "longitude"]].to_dict("records")
    neighbors: dict[int, list[tuple[int, float]]] = {}
    for station in station_rows:
        station_id = int(station["station_id"])
        distances = []
        for other in station_rows:
            other_id = int(other["station_id"])
            if other_id == station_id:
                continue
            distances.append(
                (
                    other_id,
                    _haversine_m(
                        float(station["latitude"]),
                        float(station["longitude"]),
                        float(other["latitude"]),
                        float(other["longitude"]),
                    ),
                )
            )
        neighbors[station_id] = sorted(distances, key=lambda item: item[1])[:k]
    return neighbors


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return float(2 * EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def _mean(values: list[float], fallback: float) -> float:
    finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return float(np.mean(finite)) if finite else fallback


def _profile_mean(profiles: list[dict[str, float]], key: str, fallback_key: str | None = None) -> float:
    values = []
    for profile in profiles:
        value = profile.get(key)
        if value is None and fallback_key is not None:
            value = profile.get(fallback_key)
        if value is not None and math.isfinite(float(value)):
            values.append(float(value))
    return float(np.mean(values)) if values else 0.0


def _profile_max(profiles: list[dict[str, float]], key: str) -> float:
    values = [float(profile[key]) for profile in profiles if key in profile and math.isfinite(float(profile[key]))]
    return float(np.max(values)) if values else 0.0
