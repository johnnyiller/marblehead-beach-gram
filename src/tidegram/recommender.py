from __future__ import annotations

import datetime as dt
import re
from dataclasses import asdict, dataclass, replace
from typing import Any
from zoneinfo import ZoneInfo

from .data_sources import TideEvent, WeatherPeriod


@dataclass(frozen=True)
class HourlySnapshot:
    time: dt.datetime
    temperature_f: int | None
    forecast: str
    precip_probability: int
    wind_speed_text: str

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["time"] = self.time.isoformat()
        return data


@dataclass(frozen=True)
class BeachOption:
    beach_name: str
    beach_short_name: str
    activity: str
    start: dt.datetime
    end: dt.datetime
    score: float
    note: str

    def window_label(self) -> str:
        return f"{format_time(self.start)}–{format_time(self.end)}"

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["start"] = self.start.isoformat()
        data["end"] = self.end.isoformat()
        data["window_label"] = self.window_label()
        return data


@dataclass(frozen=True)
class TideSummary:
    label: str
    time: dt.datetime
    height_ft: float | None

    def display_label(self, include_height: bool = True) -> str:
        height = "" if self.height_ft is None or not include_height else f" {self.height_ft:.1f} ft"
        return f"{self.label} {format_time(self.time)}{height}"

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["time"] = self.time.isoformat()
        data["display_label"] = self.display_label()
        return data


@dataclass(frozen=True)
class BeachRecommendation:
    date: str
    day_label: str
    start: dt.datetime
    end: dt.datetime
    beach_name: str
    beach_short_name: str
    activity: str
    tide_label: str
    tide_time: dt.datetime
    tide_height_ft: float | None
    forecast: str
    temperature_f: int | None
    wind_speed_text: str
    precip_probability: int
    score: float
    note: str
    hourly_snapshots: tuple[HourlySnapshot, ...] = ()
    alternate_beaches: tuple[BeachOption, ...] = ()
    daily_tides: tuple[TideSummary, ...] = ()

    def window_label(self) -> str:
        return f"{format_time(self.start)}–{format_time(self.end)}"

    def tide_label_full(self) -> str:
        height = "" if self.tide_height_ft is None else f" · {self.tide_height_ft:.1f} ft"
        return f"{self.tide_label} {format_time(self.tide_time)}{height}"

    def one_line_weather(self) -> str:
        temp = "" if self.temperature_f is None else f"{self.temperature_f}°F · "
        precip = f" · {self.precip_probability}% rain" if self.precip_probability else ""
        return f"{temp}{self.forecast} · {self.wind_speed_text}{precip}"

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["start"] = self.start.isoformat()
        data["end"] = self.end.isoformat()
        data["tide_time"] = self.tide_time.isoformat()
        data["hourly_snapshots"] = [snapshot.to_json() for snapshot in self.hourly_snapshots]
        data["alternate_beaches"] = [option.to_json() for option in self.alternate_beaches]
        data["daily_tides"] = [tide.to_json() for tide in self.daily_tides]
        data["window_label"] = self.window_label()
        data["tide_label_full"] = self.tide_label_full()
        data["daily_tides_label"] = self.daily_tides_label()
        data["weather"] = self.one_line_weather()
        return data

    def daily_tides_label(self) -> str:
        if not self.daily_tides:
            return "Tides unavailable"

        grouped = {"High": [], "Low": []}
        for tide in self.daily_tides:
            grouped.setdefault(tide.label, []).append(tide)

        parts = []
        for label in ["High", "Low"]:
            tides = grouped.get(label, [])
            if tides:
                parts.append(f"{label}: {', '.join(t.display_label(include_height=False).replace(label + ' ', '') for t in tides)}")
        return "; ".join(parts) if parts else "Tides unavailable"


def format_time(value: dt.datetime) -> str:
    hour = value.strftime("%I").lstrip("0") or "12"
    return f"{hour}:{value.strftime('%M %p')}"


def format_day_label(value: dt.datetime) -> str:
    return f"{value.strftime('%a')} {value.strftime('%b')} {value.day}"


def parse_wind_mph(wind_speed_text: str) -> float:
    """Return the highest mph-like number in a NWS wind speed string."""
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", wind_speed_text or "")]
    if not nums:
        return 0.0
    return max(nums)


def _forecast_sun_score(short_forecast: str) -> float:
    text = short_forecast.lower()
    score = 0.0
    if "sunny" in text or "clear" in text:
        score += 26
    elif "partly" in text:
        score += 17
    elif "mostly cloudy" in text:
        score += 5
    elif "cloudy" in text or "overcast" in text:
        score -= 6

    if "rain" in text or "showers" in text:
        score -= 28
    if "thunder" in text:
        score -= 45
    if "fog" in text:
        score -= 12
    return score


def _temperature_score(temp_f: int | None) -> float:
    if temp_f is None:
        return 0.0
    # Comfortable North Shore beach-walk target. Penalize cold/very hot, but gently.
    ideal = 72
    return max(-12.0, 18.0 - abs(temp_f - ideal) * 0.65)


def _wind_score(wind_speed_text: str, profile: str) -> float:
    mph = parse_wind_mph(wind_speed_text)
    if profile == "shelter":
        if mph <= 16:
            return 4
        if mph <= 24:
            return -2
        return -10
    if profile == "paddle":
        if mph <= 8:
            return 20
        if mph <= 12:
            return 10
        if mph <= 16:
            return -5
        return -25
    # walking / tidepooling profile
    if mph <= 10:
        return 12
    if mph <= 16:
        return 5
    if mph <= 22:
        return -6
    return -18


def weather_score(period: WeatherPeriod, wind_profile: str, sun_required: bool) -> float:
    score = 0.0
    if not period.is_daytime:
        score -= 100
    if wind_profile == "shelter":
        score += _shelter_weather_score(period)
    else:
        score += _forecast_sun_score(period.short_forecast)
    score += _temperature_score(period.temperature_f)
    score += _wind_score(period.wind_speed_text, wind_profile)
    if wind_profile == "shelter":
        score += min(24.0, period.precip_probability * 0.35)
    else:
        score -= period.precip_probability * 0.55
    if sun_required and not _is_sunny_enough(period.short_forecast):
        score -= 18
    return score


def _is_rain_threat(short_forecast: str, precip_probability: int) -> bool:
    text = short_forecast.lower()
    return (
        precip_probability >= 30
        or "rain" in text
        or "showers" in text
        or "thunder" in text
        or "drizzle" in text
    )


def _shelter_weather_score(period: WeatherPeriod) -> float:
    if _is_rain_threat(period.short_forecast, period.precip_probability):
        score = 32.0
        if "thunder" in period.short_forecast.lower():
            score -= 12
        return score
    if "cloud" in period.short_forecast.lower() or "fog" in period.short_forecast.lower():
        return 4.0
    return -18.0


def _is_sunny_enough(short_forecast: str) -> bool:
    text = short_forecast.lower()
    return any(term in text for term in ["sunny", "clear", "partly sunny", "partly cloudy", "mostly sunny"])


def _overlaps(period: WeatherPeriod, start: dt.datetime, end: dt.datetime) -> bool:
    return period.start < end and period.end > start


def _overlap_minutes(
    first_start: dt.datetime,
    first_end: dt.datetime,
    second_start: dt.datetime,
    second_end: dt.datetime,
) -> float:
    overlap_start = max(first_start, second_start)
    overlap_end = min(first_end, second_end)
    if overlap_start >= overlap_end:
        return 0.0
    return (overlap_end - overlap_start).total_seconds() / 60


def _best_weather_period(
    periods: list[WeatherPeriod],
    start: dt.datetime,
    end: dt.datetime,
    wind_profile: str,
    sun_required: bool,
) -> tuple[WeatherPeriod | None, float]:
    overlaps = [
        (p, _overlap_minutes(p.start, p.end, start, end))
        for p in periods
        if _overlaps(p, start, end)
    ]
    if not overlaps:
        return None, -999.0

    candidates = [p for p, _ in overlaps]
    scored = [(weather_score(p, wind_profile, sun_required), p) for p in candidates]
    scored.sort(key=lambda x: x[0], reverse=True)
    best_period = scored[0][1]

    total_minutes = sum(minutes for _, minutes in overlaps)
    if total_minutes <= 0:
        return best_period, scored[0][0]

    weighted_score = sum(
        weather_score(period, wind_profile, sun_required) * minutes
        for period, minutes in overlaps
    ) / total_minutes
    max_precip = max(period.precip_probability for period in candidates)
    avg_precip = sum(period.precip_probability * minutes for period, minutes in overlaps) / total_minutes
    max_wind = max(parse_wind_mph(period.wind_speed_text) for period in candidates)

    # A beach window should not win because one hour is nice while the rest is wet or windy.
    if max_precip >= 70:
        weighted_score -= 26
    elif max_precip >= 50:
        weighted_score -= 16
    elif max_precip >= 35:
        weighted_score -= 8
    if avg_precip >= 45:
        weighted_score -= 14
    elif avg_precip >= 30:
        weighted_score -= 7

    if wind_profile == "paddle" and max_wind > 14:
        weighted_score -= 90
    elif wind_profile == "paddle" and max_wind > 12:
        weighted_score -= 45
    elif max_wind > 22:
        weighted_score -= 8

    return best_period, weighted_score


def _window_weather_flags(
    periods: list[WeatherPeriod],
    start: dt.datetime,
    end: dt.datetime,
) -> tuple[bool, float]:
    overlaps = [
        (p, _overlap_minutes(p.start, p.end, start, end))
        for p in periods
        if _overlaps(p, start, end)
    ]
    if not overlaps:
        return False, 0.0

    total_minutes = sum(minutes for _, minutes in overlaps)
    max_wind = max(parse_wind_mph(period.wind_speed_text) for period, _ in overlaps)
    if total_minutes <= 0:
        rain_threat = any(_is_rain_threat(period.short_forecast, period.precip_probability) for period, _ in overlaps)
        return rain_threat, max_wind

    threatened_minutes = sum(
        minutes
        for period, minutes in overlaps
        if _is_rain_threat(period.short_forecast, period.precip_probability)
    )
    max_precip = max(period.precip_probability for period, _ in overlaps)
    rain_threat = threatened_minutes / total_minutes >= 0.25 or max_precip >= 40
    return rain_threat, max_wind


def _workweek_timing_score(start: dt.datetime, end: dt.datetime) -> float:
    if start.weekday() >= 5:
        return 4.0

    work_start = start.replace(hour=9, minute=0, second=0, microsecond=0)
    work_end = start.replace(hour=17, minute=0, second=0, microsecond=0)
    overlap = _overlap_minutes(start, end, work_start, work_end)
    total_minutes = max(1.0, (end - start).total_seconds() / 60)
    overlap_ratio = overlap / total_minutes

    score = -46.0 * overlap_ratio
    if end <= work_start:
        score += 18.0
    elif start >= work_end:
        score += 22.0
    elif start.hour == 12 or (start.hour <= 12 and end.hour >= 13):
        score += 8.0
    return score


def _time_of_day_window(
    value: dt.datetime,
    start_hour: int,
    end_hour: int,
) -> tuple[dt.datetime, dt.datetime]:
    day_start = value.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    day_end = value.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    if day_end <= day_start:
        day_end += dt.timedelta(days=1)
    return day_start, day_end


def _clip_to_preferred_visit_hours(
    start: dt.datetime,
    end: dt.datetime,
    start_hour: int,
    end_hour: int,
) -> tuple[dt.datetime, dt.datetime] | None:
    best_overlap: tuple[dt.datetime, dt.datetime] | None = None
    best_minutes = 0.0
    for day_offset in range(-1, 2):
        visit_start, visit_end = _time_of_day_window(
            start + dt.timedelta(days=day_offset),
            start_hour,
            end_hour,
        )
        clipped_start = max(start, visit_start)
        clipped_end = min(end, visit_end)
        overlap = _overlap_minutes(clipped_start, clipped_end, clipped_start, clipped_end)
        if overlap > best_minutes:
            best_minutes = overlap
            best_overlap = (clipped_start, clipped_end)

    return best_overlap


def _friendly_window_within_bounds(
    start: dt.datetime,
    end: dt.datetime,
    bound_start: dt.datetime,
    bound_end: dt.datetime,
) -> tuple[dt.datetime, dt.datetime]:
    rounded_start = max(bound_start, round_to_half_hour(start, direction="ceil"))
    rounded_end = min(bound_end, round_to_half_hour(end))

    if rounded_end <= rounded_start:
        return start, end

    return rounded_start, rounded_end


def _clip_recommended_window(
    rule_start: dt.datetime,
    rule_end: dt.datetime,
    best_period: WeatherPeriod,
    min_minutes: int = 120,
    max_minutes: int = 240,
) -> tuple[dt.datetime, dt.datetime]:
    rule_minutes = max(0, int((rule_end - rule_start).total_seconds() / 60))
    if rule_minutes == 0:
        return round_to_half_hour(rule_start), round_to_half_hour(rule_end, direction="ceil")

    desired_minutes = min(max_minutes, rule_minutes)
    if rule_minutes >= min_minutes:
        desired_minutes = max(min_minutes, desired_minutes)

    best_midpoint = best_period.start + (best_period.end - best_period.start) / 2
    start = best_midpoint - dt.timedelta(minutes=desired_minutes / 2)
    end = start + dt.timedelta(minutes=desired_minutes)

    if start < rule_start:
        end += rule_start - start
        start = rule_start
    if end > rule_end:
        start -= end - rule_end
        end = rule_end
    start = max(rule_start, start)
    end = min(rule_end, end)

    # Round to friendlier half-hour labels without expanding past the target duration.
    rounded_start, rounded_end = _friendly_window_within_bounds(start, end, rule_start, rule_end)
    desired_delta = dt.timedelta(minutes=desired_minutes)
    if rounded_end - rounded_start > desired_delta:
        rounded_end = rounded_start + desired_delta
    return rounded_start, rounded_end


def round_to_half_hour(value: dt.datetime, direction: str = "floor") -> dt.datetime:
    minute = value.minute
    if direction == "ceil":
        add = (30 - minute % 30) % 30
        if add == 0 and value.second == 0 and value.microsecond == 0:
            rounded = value
        else:
            rounded = value + dt.timedelta(minutes=add)
        return rounded.replace(second=0, microsecond=0)

    rounded_minute = 0 if minute < 30 else 30
    return value.replace(minute=rounded_minute, second=0, microsecond=0)


def _hourly_snapshots_around_window(
    periods: list[WeatherPeriod],
    start: dt.datetime,
    end: dt.datetime,
    max_items: int = 3,
) -> tuple[HourlySnapshot, ...]:
    window_start = start - dt.timedelta(hours=1)
    window_end = end + dt.timedelta(hours=1)
    candidates = [
        period
        for period in periods
        if window_start <= period.start <= window_end
    ]
    if not candidates:
        return ()

    midpoint = start + (end - start) / 2
    targets = [start, midpoint, end]
    chosen: list[WeatherPeriod] = []
    for target in targets:
        remaining = [period for period in candidates if period not in chosen]
        if not remaining:
            break
        closest = min(remaining, key=lambda p: abs((p.start - target).total_seconds()))
        chosen.append(closest)

    chosen.sort(key=lambda p: p.start)
    return tuple(
        HourlySnapshot(
            time=period.start,
            temperature_f=period.temperature_f,
            forecast=period.short_forecast,
            precip_probability=period.precip_probability,
            wind_speed_text=period.wind_speed_text,
        )
        for period in chosen[:max_items]
    )


def _daily_tide_summaries(tides: list[TideEvent]) -> dict[str, tuple[TideSummary, ...]]:
    by_day: dict[str, list[TideSummary]] = {}
    for tide in tides:
        by_day.setdefault(tide.time.date().isoformat(), []).append(
            TideSummary(
                label=tide.label,
                time=tide.time,
                height_ft=tide.height_ft,
            )
        )
    return {
        day: tuple(sorted(day_tides, key=lambda tide: tide.time))
        for day, day_tides in by_day.items()
    }


def _option_from_recommendation(rec: BeachRecommendation) -> BeachOption:
    return BeachOption(
        beach_name=rec.beach_name,
        beach_short_name=rec.beach_short_name,
        activity=rec.activity,
        start=rec.start,
        end=rec.end,
        score=rec.score,
        note=rec.note,
    )


def _add_alternate_beaches(
    primary: BeachRecommendation,
    day_candidates: list[BeachRecommendation],
    max_beach_options_per_day: int,
    alternate_min_score: float,
    alternate_max_score_gap: float,
    alternate_min_overlap_minutes: int,
) -> BeachRecommendation:
    alternate_limit = max(0, max_beach_options_per_day - 1)
    if alternate_limit == 0:
        return primary

    alternates: list[BeachOption] = []
    used_beaches = {primary.beach_name}
    for candidate in day_candidates:
        if len(alternates) >= alternate_limit:
            break
        if candidate.beach_name in used_beaches:
            continue
        if candidate.score < alternate_min_score:
            continue
        if primary.score - candidate.score > alternate_max_score_gap:
            continue
        overlap = _overlap_minutes(primary.start, primary.end, candidate.start, candidate.end)
        if overlap < alternate_min_overlap_minutes:
            continue

        alternates.append(_option_from_recommendation(candidate))
        used_beaches.add(candidate.beach_name)

    return replace(primary, alternate_beaches=tuple(alternates))


def build_recommendations(
    tides: list[TideEvent],
    weather: list[WeatherPeriod],
    beach_rules: dict[str, Any],
    days: int,
    tz_name: str = "America/New_York",
    per_day: bool = True,
    max_beach_options_per_day: int = 2,
    alternate_min_score: float = 120.0,
    alternate_max_score_gap: float = 8.0,
    alternate_min_overlap_minutes: int = 60,
    recommended_window_min_minutes: int = 120,
    recommended_window_max_minutes: int = 240,
    preferred_start_hour: int = 6,
    preferred_end_hour: int = 21,
) -> list[BeachRecommendation]:
    zone = ZoneInfo(tz_name)
    today = dt.datetime.now(zone).date()
    horizon = today + dt.timedelta(days=days)
    daily_tides_by_date = _daily_tide_summaries(tides)

    candidates: list[BeachRecommendation] = []
    for tide in tides:
        if tide.time.date() < today or tide.time.date() > horizon:
            continue
        for beach in beach_rules.get("beaches", []):
            for rule in beach.get("rules", []):
                if rule.get("event_type") != tide.event_type:
                    continue
                start = tide.time + dt.timedelta(minutes=int(rule["start_minutes"]))
                end = tide.time + dt.timedelta(minutes=int(rule["end_minutes"]))
                preferred_window = _clip_to_preferred_visit_hours(
                    start,
                    end,
                    start_hour=preferred_start_hour,
                    end_hour=preferred_end_hour,
                )
                if preferred_window is None:
                    continue
                start, end = preferred_window
                if _overlap_minutes(start, end, start, end) < max(30, recommended_window_min_minutes // 2):
                    continue
                start, end = _friendly_window_within_bounds(start, end, start, end)
                best_period, wx_score = _best_weather_period(
                    weather,
                    start,
                    end,
                    wind_profile=rule.get("wind_profile", "walk"),
                    sun_required=bool(rule.get("sun_required", True)),
                )
                if best_period is None:
                    continue
                if best_period.is_daytime is False:
                    continue
                rec_start, rec_end = _clip_recommended_window(
                    start,
                    end,
                    best_period,
                    min_minutes=recommended_window_min_minutes,
                    max_minutes=recommended_window_max_minutes,
                )
                tide_score = float(rule.get("base_score", 60))

                # Prefer windows close to the tide event center.
                midpoint = rec_start + (rec_end - rec_start) / 2
                minutes_from_tide = abs((midpoint - tide.time).total_seconds()) / 60
                closeness_bonus = max(0.0, 16 - minutes_from_tide / 10)

                wind_profile = rule.get("wind_profile", "walk")
                rain_threat, max_wind = _window_weather_flags(weather, rec_start, rec_end)
                score = tide_score + wx_score + closeness_bonus
                score += _workweek_timing_score(rec_start, rec_end)
                if rain_threat:
                    if wind_profile == "shelter":
                        score += 95
                    else:
                        score -= 150
                elif wind_profile == "shelter":
                    score -= 80

                if wind_profile == "paddle" and max_wind > 12:
                    score -= 140

                candidates.append(
                    BeachRecommendation(
                        date=tide.time.date().isoformat(),
                        day_label=format_day_label(tide.time),
                        start=rec_start,
                        end=rec_end,
                        beach_name=beach.get("name", "Unknown beach"),
                        beach_short_name=beach.get("short_name", beach.get("name", "Beach")),
                        activity=rule.get("activity", "Beach visit"),
                        tide_label=tide.label,
                        tide_time=tide.time,
                        tide_height_ft=tide.height_ft,
                        forecast=best_period.short_forecast,
                        temperature_f=best_period.temperature_f,
                        wind_speed_text=best_period.wind_speed_text,
                        precip_probability=best_period.precip_probability,
                        score=round(score, 1),
                        note=rule.get("note", beach.get("display_note", "")),
                        hourly_snapshots=_hourly_snapshots_around_window(weather, rec_start, rec_end),
                        daily_tides=daily_tides_by_date.get(tide.time.date().isoformat(), ()),
                    )
                )

    if per_day:
        candidates_by_day: dict[str, list[BeachRecommendation]] = {}
        for rec in candidates:
            candidates_by_day.setdefault(rec.date, []).append(rec)

        best_by_day: list[BeachRecommendation] = []
        for day_candidates in candidates_by_day.values():
            ranked = sorted(day_candidates, key=lambda r: r.score, reverse=True)
            primary = ranked[0]
            best_by_day.append(
                _add_alternate_beaches(
                    primary,
                    ranked[1:],
                    max_beach_options_per_day=max_beach_options_per_day,
                    alternate_min_score=alternate_min_score,
                    alternate_max_score_gap=alternate_max_score_gap,
                    alternate_min_overlap_minutes=alternate_min_overlap_minutes,
                )
            )
        return sorted(best_by_day, key=lambda r: r.start)

    return sorted(candidates, key=lambda r: r.score, reverse=True)


def _caption_recommendation_for_date(
    recommendations: list[BeachRecommendation],
    target_date: dt.date | None,
) -> BeachRecommendation | None:
    if not recommendations:
        return None
    if target_date is None:
        return recommendations[0]

    target_iso = target_date.isoformat()
    same_day = [rec for rec in recommendations if rec.date == target_iso]
    if same_day:
        return max(same_day, key=lambda r: r.score)
    return None


def _periods_for_date(weather: list[WeatherPeriod], target_date: dt.date | None) -> list[WeatherPeriod]:
    if target_date is None:
        return []
    return [period for period in weather if period.start.date() == target_date]


def _most_common_forecasts(periods: list[WeatherPeriod], limit: int = 3) -> str:
    counts: dict[str, int] = {}
    for period in periods:
        forecast = period.short_forecast.strip()
        if forecast:
            counts[forecast] = counts.get(forecast, 0) + 1
    if not counts:
        return "forecast details unavailable"
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))
    return ", ".join(label for label, _ in ranked[:limit])


def _temperature_range(periods: list[WeatherPeriod]) -> str:
    temps = [period.temperature_f for period in periods if period.temperature_f is not None]
    if not temps:
        return "temps unavailable"
    low = min(temps)
    high = max(temps)
    if low == high:
        return f"around {high}°F"
    return f"{low}°F to {high}°F"


def _wind_summary(periods: list[WeatherPeriod]) -> tuple[str, float]:
    if not periods:
        return "wind unavailable", 0.0
    max_period = max(periods, key=lambda period: parse_wind_mph(period.wind_speed_text))
    max_wind = parse_wind_mph(max_period.wind_speed_text)
    return max_period.wind_speed_text or "wind unavailable", max_wind


def _rain_summary(periods: list[WeatherPeriod]) -> tuple[str, int, bool]:
    if not periods:
        return "rain chance unavailable", 0, False
    max_precip = max(period.precip_probability for period in periods)
    has_rain_text = any(_is_rain_threat(period.short_forecast, period.precip_probability) for period in periods)
    if max_precip <= 0 and not has_rain_text:
        return "little to no rain showing", max_precip, False
    return f"rain chance peaks near {max_precip}%", max_precip, has_rain_text


def _caption_advisories(periods: list[WeatherPeriod]) -> list[str]:
    if not periods:
        return []

    advisories: list[str] = []
    wind_text, max_wind = _wind_summary(periods)
    _, max_precip, has_rain_threat = _rain_summary(periods)
    forecast_text = " ".join(period.short_forecast.lower() for period in periods)

    if has_rain_threat or max_precip >= 30:
        advisories.append("Rain/threatening weather: Picnic Shelter is the sensible fallback.")
    if "thunder" in forecast_text:
        advisories.append("Thunder risk: skip exposed beach time if storms are nearby.")
    if max_wind > 12:
        advisories.append(f"Paddleboard caution: wind may reach {wind_text}.")
    if "fog" in forecast_text:
        advisories.append("Fog may reduce visibility near the water.")
    return advisories


def _daily_weather_caption(periods: list[WeatherPeriod]) -> str:
    if not periods:
        return "Weather: hourly details unavailable."

    forecasts = _most_common_forecasts(periods)
    temps = _temperature_range(periods)
    wind_text, _ = _wind_summary(periods)
    rain_text, _, _ = _rain_summary(periods)
    return f"Weather: {forecasts}; temps {temps}; wind {wind_text}; {rain_text}."


def _daily_tides_caption(rec: BeachRecommendation | None, tides: list[TideEvent], target_date: dt.date | None) -> str:
    if rec and rec.daily_tides:
        return f"Tides: {rec.daily_tides_label()}."
    if target_date is None:
        return "Tides: unavailable."
    daily_tides = [
        TideSummary(tide.label, tide.time, tide.height_ft)
        for tide in tides
        if tide.time.date() == target_date
    ]
    if not daily_tides:
        return "Tides: unavailable."

    grouped = {"High": [], "Low": []}
    for tide in sorted(daily_tides, key=lambda item: item.time):
        grouped.setdefault(tide.label, []).append(tide)

    parts = []
    for label in ["High", "Low"]:
        values = grouped.get(label, [])
        if values:
            parts.append(f"{label}: {', '.join(t.display_label(include_height=False).replace(label + ' ', '') for t in values)}")
    return f"Tides: {'; '.join(parts)}."


def build_caption(
    recommendations: list[BeachRecommendation],
    location_name: str,
    target_date: dt.date | None = None,
    weather: list[WeatherPeriod] | None = None,
    tides: list[TideEvent] | None = None,
) -> str:
    rec = _caption_recommendation_for_date(recommendations, target_date)
    if not rec and not recommendations:
        return f"{location_name} tide + weather outlook 🌊"

    periods = _periods_for_date(weather or [], target_date)
    target_label = format_day_label(dt.datetime.combine(target_date, dt.time())) if target_date else (rec.day_label if rec else "Today")
    lines = [
        f"{location_name} beach outlook for {target_label} 🌊☀️",
    ]

    if rec:
        lines.extend(
            [
                f"Best window: {rec.window_label()} at {rec.beach_short_name}.",
                f"{rec.activity}. Recommended tide: {rec.tide_label_full()}.",
            ]
        )
    else:
        lines.append("No standout beach window for today from the current tide/weather mix.")

    lines.extend(
        [
            _daily_weather_caption(periods),
            _daily_tides_caption(rec, tides or [], target_date),
        ]
    )

    advisories = _caption_advisories(periods)
    if advisories:
        lines.append("Heads up: " + " ".join(advisories))

    lines.extend(
        [
            "",
            "Built from NOAA tides + NWS hourly weather.",
            "#MarbleheadMA #NorthShoreMA #BeachWeather #TideWatch",
        ]
    )
    return "\n".join(lines)


def summarize_for_site(recommendations: list[BeachRecommendation]) -> list[dict[str, str]]:
    rows = []
    for rec in recommendations:
        beach_names = [rec.beach_name, *[option.beach_name for option in rec.alternate_beaches]]
        rows.append(
            {
                "day": rec.day_label,
                "best_time": rec.window_label(),
                "beach": "; ".join(beach_names),
                "activity": rec.activity,
                "tide": rec.daily_tides_label(),
                "weather": rec.one_line_weather(),
                "note": rec.note,
            }
        )
    return rows
