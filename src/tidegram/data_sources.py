from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
from typing import Any
from zoneinfo import ZoneInfo

import requests


@dataclass(frozen=True)
class TideEvent:
    time: dt.datetime
    event_type: str  # "H" or "L"
    height_ft: float | None
    station_id: str

    @property
    def label(self) -> str:
        return "High" if self.event_type == "H" else "Low"

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["time"] = self.time.isoformat()
        return data


@dataclass(frozen=True)
class WeatherPeriod:
    start: dt.datetime
    end: dt.datetime
    temperature_f: int | None
    wind_speed_text: str
    short_forecast: str
    precip_probability: int
    is_daytime: bool

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["start"] = self.start.isoformat()
        data["end"] = self.end.isoformat()
        return data


def _local_date_range(days: int, tz_name: str) -> tuple[dt.date, dt.date]:
    today = dt.datetime.now(ZoneInfo(tz_name)).date()
    return today, today + dt.timedelta(days=days)


def fetch_noaa_tides(
    station_id: str,
    days: int,
    tz_name: str = "America/New_York",
    units: str = "english",
    datum: str = "MLLW",
    session: requests.Session | None = None,
) -> list[TideEvent]:
    """Fetch high/low tide predictions from NOAA CO-OPS."""
    session = session or requests.Session()
    start_date, end_date = _local_date_range(days, tz_name)
    params = {
        "product": "predictions",
        "application": "marblehead_tidegram",
        "begin_date": start_date.strftime("%Y%m%d"),
        "end_date": end_date.strftime("%Y%m%d"),
        "datum": datum,
        "station": station_id,
        "time_zone": "lst_ldt",
        "units": units,
        "interval": "hilo",
        "format": "json",
    }
    response = session.get(
        "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter",
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(f"NOAA CO-OPS error: {payload['error']}")

    zone = ZoneInfo(tz_name)
    events: list[TideEvent] = []
    for item in payload.get("predictions", []):
        try:
            event_time = dt.datetime.strptime(item["t"], "%Y-%m-%d %H:%M").replace(tzinfo=zone)
        except (KeyError, ValueError) as exc:
            raise RuntimeError(f"Unexpected NOAA tide item: {item}") from exc
        try:
            height_ft = float(item["v"])
        except (KeyError, TypeError, ValueError):
            height_ft = None
        events.append(TideEvent(event_time, item.get("type", ""), height_ft, station_id))
    return sorted(events, key=lambda e: e.time)


def fetch_nws_hourly_weather(
    latitude: float,
    longitude: float,
    days: int,
    user_agent: str,
    tz_name: str = "America/New_York",
    session: requests.Session | None = None,
) -> list[WeatherPeriod]:
    """Fetch hourly forecast periods from the National Weather Service API."""
    session = session or requests.Session()
    if "replace-with-your-email" in user_agent or "your-email" in user_agent:
        raise RuntimeError(
            "Please set NWS_USER_AGENT to a real contact string, for example: "
            "marblehead-tidegram/0.1 (you@example.com)"
        )

    headers = {
        "User-Agent": user_agent,
        "Accept": "application/geo+json, application/json",
    }
    point_response = session.get(
        f"https://api.weather.gov/points/{latitude:.4f},{longitude:.4f}",
        headers=headers,
        timeout=30,
    )
    point_response.raise_for_status()
    points = point_response.json()
    hourly_url = points["properties"]["forecastHourly"]

    hourly_response = session.get(hourly_url, headers=headers, timeout=30)
    hourly_response.raise_for_status()
    periods = hourly_response.json()["properties"]["periods"]

    zone = ZoneInfo(tz_name)
    now = dt.datetime.now(zone)
    horizon = now + dt.timedelta(days=days + 1)

    results: list[WeatherPeriod] = []
    for item in periods:
        start = dt.datetime.fromisoformat(item["startTime"]).astimezone(zone)
        end = dt.datetime.fromisoformat(item["endTime"]).astimezone(zone)
        if start > horizon:
            continue
        precip = item.get("probabilityOfPrecipitation", {}).get("value")
        results.append(
            WeatherPeriod(
                start=start,
                end=end,
                temperature_f=item.get("temperature"),
                wind_speed_text=item.get("windSpeed", ""),
                short_forecast=item.get("shortForecast", ""),
                precip_probability=int(precip or 0),
                is_daytime=bool(item.get("isDaytime", False)),
            )
        )
    return results
