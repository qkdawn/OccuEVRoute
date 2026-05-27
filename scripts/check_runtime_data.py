"""Validate occupancy runtime data files required by the app."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / "data" / "runtime" / "occupancy_week"
STATION_DIR = RUNTIME_DIR / "station-processed"
FEATURE_DIR = STATION_DIR / "features"

REQUIRED_FILES = {
    RUNTIME_DIR / "weather_central.csv": "Weather rows for the simulation week",
    FEATURE_DIR / "station_inf.csv": "Station static context",
    FEATURE_DIR / "station_profiles.csv": "Precomputed station profile features",
}


def main() -> None:
    missing = []
    print(f"Checking occupancy runtime data in {RUNTIME_DIR}")
    for path, description in REQUIRED_FILES.items():
        if not path.exists():
            missing.append(str(path.relative_to(PROJECT_ROOT)))
            print(f"missing  {path.name} - {description}")
            continue
        print(f"ok       {path.relative_to(PROJECT_ROOT)} ({path.stat().st_size / 1024 / 1024:.1f} MB)")

    station_files = sorted(STATION_DIR.glob("*.csv.gz"))
    if not station_files:
        missing.append(str(STATION_DIR / "*.csv.gz"))
        print("missing  station *.csv.gz files - simulation-week station history")
    else:
        print(f"ok       {len(station_files)} station history files")

    if missing:
        joined = ", ".join(missing)
        raise SystemExit(f"Missing required occupancy runtime data: {joined}")
    print("Occupancy runtime data is ready.")


if __name__ == "__main__":
    main()
