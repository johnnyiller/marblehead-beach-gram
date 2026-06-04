from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from .data_sources import TideEvent, WeatherPeriod


def sample_tides_and_weather(days: int = 5, tz_name: str = "America/New_York") -> tuple[list[TideEvent], list[WeatherPeriod]]:
    """Small deterministic-ish sample for local layout testing without API calls."""
    zone = ZoneInfo(tz_name)
    today = dt.datetime.now(zone).date()
    tides: list[TideEvent] = []
    weather: list[WeatherPeriod] = []

    for i in range(days + 1):
        date = today + dt.timedelta(days=i)
        low = dt.datetime.combine(date, dt.time(8, 30), zone) + dt.timedelta(minutes=45 * i)
        high = low + dt.timedelta(hours=6, minutes=15)
        tides.extend(
            [
                TideEvent(time=low, event_type="L", height_ft=0.4 + 0.1 * i, station_id="sample"),
                TideEvent(time=high, event_type="H", height_ft=9.2 - 0.1 * i, station_id="sample"),
            ]
        )
        for hour in range(6, 21):
            start = dt.datetime.combine(date, dt.time(hour, 0), zone)
            forecast = "Mostly Sunny" if i < 3 else "Partly Sunny"
            precip = 0 if i < 3 else 15
            weather.append(
                WeatherPeriod(
                    start=start,
                    end=start + dt.timedelta(hours=1),
                    temperature_f=66 + i * 2 + max(0, hour - 10),
                    wind_speed_text="6 to 10 mph" if i < 2 else "8 to 13 mph",
                    short_forecast=forecast,
                    precip_probability=precip,
                    is_daytime=True,
                )
            )
    return sorted(tides, key=lambda t: t.time), sorted(weather, key=lambda w: w.start)
