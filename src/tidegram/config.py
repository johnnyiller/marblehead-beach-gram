from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
SITE_DIR = ROOT / "site"
ASSETS_DIR = SITE_DIR / "assets"


def load_json(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = ROOT / file_path
    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_settings() -> dict[str, Any]:
    settings = load_json(CONFIG_DIR / "settings.json")

    # Environment overrides make GitHub Actions and local testing easier.
    if os.getenv("NOAA_STATION_ID"):
        settings["noaa_station_id"] = os.environ["NOAA_STATION_ID"]
    if os.getenv("LOCATION_LAT"):
        settings["latitude"] = float(os.environ["LOCATION_LAT"])
    if os.getenv("LOCATION_LON"):
        settings["longitude"] = float(os.environ["LOCATION_LON"])
    if os.getenv("DAYS_TO_FORECAST"):
        settings["days_to_forecast"] = int(os.environ["DAYS_TO_FORECAST"])
    if os.getenv("NWS_USER_AGENT"):
        settings["nws_user_agent"] = os.environ["NWS_USER_AGENT"]

    return settings


def load_beach_rules() -> dict[str, Any]:
    return load_json(CONFIG_DIR / "beaches.json")


def ensure_output_dirs() -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
