#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tidegram.config import SITE_DIR, ensure_output_dirs, load_beach_rules, load_settings
from tidegram.data_sources import fetch_noaa_tides, fetch_nws_hourly_weather
from tidegram.openai_background import (
    DAILY_ART_DIRECTIONS,
    VISUAL_STYLE_DIRECTIONS,
    build_full_post_prompt,
    build_reel_image_prompt,
    compose_art_direction,
    daily_art_direction,
    generate_openai_full_post,
    generate_openai_reel_image,
    numbered_art_direction,
)
from tidegram.recommender import build_caption, build_recommendations
from tidegram.sample import sample_tides_and_weather
from tidegram.site import write_background_trials, write_index, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the Marblehead Tidegram static site assets.")
    parser.add_argument("--sample", action="store_true", help="Use sample data instead of NOAA/NWS API calls.")
    parser.add_argument("--days", type=int, default=None, help="Number of days to fetch/recommend.")
    parser.add_argument("--date", default=None, help="Use YYYY-MM-DD for dated output names and date-based art when no default is configured.")
    parser.add_argument(
        "--list-art-directions",
        "--list-backgrounds",
        dest="list_art_directions",
        action="store_true",
        help="List numbered background/art-direction prompts and exit.",
    )
    parser.add_argument(
        "--art-direction",
        "--background",
        default=None,
        help="Use a numbered art direction from --list-art-directions, or pass custom art-direction text.",
    )
    parser.add_argument(
        "--background-variants",
        "--try-backgrounds",
        dest="background_variants",
        type=int,
        default=0,
        help="Generate this many full OpenAI post trials with different background art directions.",
    )
    parser.add_argument(
        "--print-prompt",
        action="store_true",
        help="Print the OpenAI full-post prompt and exit without generating an image.",
    )
    parser.add_argument(
        "--print-reel-prompt",
        action="store_true",
        help="Print the OpenAI Reel-image prompt and exit without generating an image.",
    )
    parser.add_argument("--output-dir", default=str(SITE_DIR), help="Static site output directory.")
    return parser.parse_args()


def parse_visual_date(value: str | None, zone: ZoneInfo) -> dt.date:
    if not value:
        return dt.datetime.now(zone).date()
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit("--date must be in YYYY-MM-DD format.") from exc


def print_art_directions() -> None:
    print("auto. Date-rotated coastal theme + visual style with forecast-aware background cues")
    print("Visual style rotation:")
    for idx, style in enumerate(VISUAL_STYLE_DIRECTIONS, start=1):
        print(f"- {idx}. {style['label']}: {style['direction']}")
    print("Background composition rotation:")
    for idx, direction in enumerate(DAILY_ART_DIRECTIONS, start=1):
        print(f"{idx}. {direction}")


def resolve_art_direction(
    value: str | int | None,
    visual_date: dt.date,
    recommendations=None,
    offset: int = 0,
) -> str:
    rotation_date = visual_date + dt.timedelta(days=offset)
    if value is None:
        return daily_art_direction(rotation_date, recommendations=recommendations)

    selector = str(value).strip()
    if not selector or selector.lower() in {"auto", "daily", "rotate", "rotation", "weather"}:
        return daily_art_direction(rotation_date, recommendations=recommendations)

    try:
        direction_number = int(selector)
    except ValueError:
        return selector

    try:
        base_direction = numbered_art_direction(direction_number)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    return compose_art_direction(
        base_direction,
        recommendations=recommendations,
        day=visual_date,
        offset=offset,
    )


def build_trial_art_directions(count: int, selector: str | None, visual_date: dt.date, recommendations=None) -> list[str]:
    if count < 1:
        raise SystemExit("--background-variants must be 1 or greater.")

    if selector:
        if count == 1:
            return [resolve_art_direction(selector, visual_date, recommendations=recommendations)]
        return [
            (
                f"{resolve_art_direction(selector, visual_date, recommendations=recommendations, offset=idx - 1)}; "
                f"trial {idx}: keep the same brand/style but change the background composition, "
                "paper layer geometry, horizon placement, accent placement, and negative-space balance."
            )
            for idx in range(1, count + 1)
        ]

    trials: list[str] = []
    for offset in range(count):
        base = resolve_art_direction("auto", visual_date, recommendations=recommendations, offset=offset)
        cycle = offset // len(DAILY_ART_DIRECTIONS)
        if cycle:
            base = (
                f"{base}; alternate composition {cycle + 1} with different paper layer geometry, "
                "accent placement, and horizon spacing."
            )
        trials.append(base)
    return trials


def main() -> None:
    load_dotenv(ROOT / ".env")
    args = parse_args()
    if args.list_art_directions:
        print_art_directions()
        return
    if args.background_variants < 0:
        raise SystemExit("--background-variants must be 0 or greater.")

    settings = load_settings()
    beach_rules = load_beach_rules()
    ensure_output_dirs()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "assets").mkdir(parents=True, exist_ok=True)

    tz_name = settings.get("timezone", "America/New_York")
    zone = ZoneInfo(tz_name)
    visual_date = parse_visual_date(args.date, zone)
    days = args.days or int(settings["days_to_forecast"])

    if args.sample:
        tides, weather = sample_tides_and_weather(days=days, tz_name=tz_name)
    else:
        tides = fetch_noaa_tides(
            station_id=settings["noaa_station_id"],
            days=days,
            tz_name=tz_name,
        )
        weather = fetch_nws_hourly_weather(
            latitude=float(settings["latitude"]),
            longitude=float(settings["longitude"]),
            days=days,
            user_agent=settings["nws_user_agent"],
            tz_name=tz_name,
        )

    recommendations = build_recommendations(
        tides=tides,
        weather=weather,
        beach_rules=beach_rules,
        days=days,
        tz_name=tz_name,
        per_day=True,
        max_beach_options_per_day=int(settings.get("max_beach_options_per_day", 2)),
        alternate_min_score=float(settings.get("alternate_beach_min_score", 120)),
        alternate_max_score_gap=float(settings.get("alternate_beach_max_score_gap", 8)),
        alternate_min_overlap_minutes=int(settings.get("alternate_beach_min_overlap_minutes", 60)),
        recommended_window_min_minutes=int(settings.get("recommended_window_min_minutes", 120)),
        recommended_window_max_minutes=int(settings.get("recommended_window_max_minutes", 240)),
        preferred_start_hour=int(settings.get("preferred_window_start_hour", 9)),
        preferred_end_hour=int(settings.get("preferred_window_end_hour", 21)),
    )
    if not recommendations:
        raise RuntimeError("No beach recommendations were produced. Check tide/weather data and beach rules.")

    generated_at_dt = dt.datetime.now(zone)
    generated_at = generated_at_dt.isoformat()
    asset_version = generated_at_dt.strftime("%Y%m%d%H%M%S")
    date_slug = visual_date.strftime("%Y-%m-%d")
    versioned_slug = f"{date_slug}-{asset_version}"

    png_path = output_dir / "latest.png"
    jpg_path = output_dir / "latest.jpg"
    dated_png = output_dir / "assets" / f"tidegram-{versioned_slug}.png"
    dated_jpg = output_dir / "assets" / f"tidegram-{versioned_slug}.jpg"
    reel_png_path = output_dir / "latest-reel.png"
    reel_jpg_path = output_dir / "latest-reel.jpg"
    dated_reel_png = output_dir / "assets" / f"tidegram-{versioned_slug}-reel.png"
    dated_reel_jpg = output_dir / "assets" / f"tidegram-{versioned_slug}-reel.jpg"

    rendered_recommendations = recommendations[: int(settings.get("recommendations_to_render", 3))]
    reel_recommendations = recommendations[: int(settings.get("reel_recommendations_to_render", settings.get("recommendations_to_render", 3)))]
    image_width = int(settings.get("default_image_width", settings.get("default_image_size", 1080)))
    image_height = int(settings.get("default_image_height", settings.get("default_image_size", 1080)))
    reel_image_width = int(settings.get("reel_image_width", 1080))
    reel_image_height = int(settings.get("reel_image_height", 1920))
    title = settings.get("site_title", "Marblehead Tide + Weather Outlook")
    subtitle = settings.get("subtitle", "Best beach windows from tides + hourly forecast")
    reel_title = settings.get("reel_title", "Marblehead Beach Outlook")
    reel_subtitle = settings.get("reel_subtitle", "Three-day beach windows")
    art_direction_selector = args.art_direction if args.art_direction is not None else settings.get("default_art_direction")
    art_direction = resolve_art_direction(art_direction_selector, visual_date, recommendations=rendered_recommendations)

    if args.print_prompt:
        print(
            build_full_post_prompt(
                recommendations=rendered_recommendations,
                title=title,
                subtitle=subtitle,
                location_name=settings.get("location_name", "Marblehead, MA"),
                art_direction=art_direction,
            )
        )
        return

    if args.print_reel_prompt:
        print(
            build_reel_image_prompt(
                recommendations=reel_recommendations,
                title=reel_title,
                subtitle=reel_subtitle,
                location_name=settings.get("location_name", "Marblehead, MA"),
                art_direction=art_direction,
            )
        )
        return

    if args.background_variants:
        trial_art_directions = build_trial_art_directions(
            args.background_variants,
            args.art_direction,
            visual_date,
            recommendations=rendered_recommendations,
        )
        variants = []
        print(f"Generating {len(trial_art_directions)} full OpenAI background trial(s)...")
        for idx, trial_art_direction in enumerate(trial_art_directions, start=1):
            trial_slug = f"tidegram-{date_slug}-trial-{idx:02d}"
            trial_png = output_dir / "assets" / f"{trial_slug}.png"
            trial_jpg = output_dir / "assets" / f"{trial_slug}.jpg"
            print(f"- Trial {idx}: {trial_art_direction}")
            generate_openai_full_post(
                recommendations=rendered_recommendations,
                output_png=trial_png,
                output_jpg=trial_jpg,
                model=settings.get("openai_full_post_model", "gpt-image-2"),
                size=settings.get("openai_full_post_size", "1088x1360"),
                final_width=image_width,
                final_height=image_height,
                title=title,
                subtitle=subtitle,
                location_name=settings.get("location_name", "Marblehead, MA"),
                art_direction=trial_art_direction,
            )
            variants.append(
                {
                    "index": idx,
                    "art_direction": trial_art_direction,
                    "png": f"assets/{trial_slug}.png",
                    "jpg": f"assets/{trial_slug}.jpg",
                }
            )

        trial_metadata = {
            "generated_at": generated_at,
            "location_name": settings.get("location_name", "Marblehead, MA"),
            "days_to_forecast": days,
            "image_generation_mode": "openai_full_post",
            "image_model": settings.get("openai_full_post_model", "gpt-image-2"),
            "variants": variants,
            "recommendations": [r.to_json() for r in recommendations],
        }
        write_json(output_dir / "background-trials.json", trial_metadata)
        write_background_trials(output_dir / "background-trials.html", variants)
        print(f"Generated {output_dir / 'background-trials.html'}")
        print(f"Generated {output_dir / 'background-trials.json'}")
        return

    print("Generating full OpenAI Instagram post...")
    generate_openai_full_post(
        recommendations=rendered_recommendations,
        output_png=png_path,
        output_jpg=jpg_path,
        model=settings.get("openai_full_post_model", "gpt-image-2"),
        size=settings.get("openai_full_post_size", "1088x1360"),
        final_width=image_width,
        final_height=image_height,
        title=title,
        subtitle=subtitle,
        location_name=settings.get("location_name", "Marblehead, MA"),
        art_direction=art_direction,
    )
    shutil.copy2(png_path, dated_png)
    shutil.copy2(jpg_path, dated_jpg)

    print("Generating OpenAI Reel still...")
    generate_openai_reel_image(
        recommendations=reel_recommendations,
        output_png=reel_png_path,
        output_jpg=reel_jpg_path,
        model=settings.get("openai_reel_image_model", settings.get("openai_full_post_model", "gpt-image-2")),
        size=settings.get("openai_reel_image_size", "1088x1936"),
        final_width=reel_image_width,
        final_height=reel_image_height,
        title=reel_title,
        subtitle=reel_subtitle,
        location_name=settings.get("location_name", "Marblehead, MA"),
        art_direction=art_direction,
    )
    shutil.copy2(reel_png_path, dated_reel_png)
    shutil.copy2(reel_jpg_path, dated_reel_jpg)

    caption = build_caption(recommendations, settings.get("location_name", "Marblehead, MA"))
    metadata = {
        "generated_at": generated_at,
        "location_name": settings.get("location_name", "Marblehead, MA"),
        "timezone": tz_name,
        "latitude": settings.get("latitude"),
        "longitude": settings.get("longitude"),
        "noaa_station_id": settings.get("noaa_station_id"),
        "noaa_station_label": settings.get("noaa_station_label"),
        "days_to_forecast": days,
        "caption": caption,
        "asset_version": asset_version,
        "latest_jpg": "latest.jpg",
        "latest_png": "latest.png",
        "dated_jpg": f"assets/{dated_jpg.name}",
        "dated_png": f"assets/{dated_png.name}",
        "latest_reel_jpg": "latest-reel.jpg",
        "latest_reel_png": "latest-reel.png",
        "dated_reel_jpg": f"assets/{dated_reel_jpg.name}",
        "dated_reel_png": f"assets/{dated_reel_png.name}",
        "recommendations": [r.to_json() for r in recommendations],
        "tide_events": [t.to_json() for t in tides],
        "weather_period_count": len(weather),
        "image_generation_mode": "openai_full_post",
        "image_model": settings.get("openai_full_post_model", "gpt-image-2"),
        "image_size": settings.get("openai_full_post_size", "1088x1360"),
        "reel_image_generation_mode": "openai_reel_image",
        "reel_image_model": settings.get("openai_reel_image_model", settings.get("openai_full_post_model", "gpt-image-2")),
        "reel_image_size": settings.get("openai_reel_image_size", "1088x1936"),
        "reel_image_final_size": f"{reel_image_width}x{reel_image_height}",
        "art_direction": art_direction,
        "sources": {
            "tides": "NOAA CO-OPS Data API predictions, interval=hilo",
            "weather": "National Weather Service hourly forecast API",
            "beach_rules": "User-provided Marblehead beach preferences in config/beaches.json",
        },
    }

    write_json(output_dir / "latest.json", metadata)
    write_index(
        output_dir / "index.html",
        recommendations=recommendations,
        metadata=metadata,
        title=settings.get("site_title", "Marblehead Tide + Weather Outlook"),
    )

    print(f"Generated {png_path}")
    print(f"Generated {jpg_path}")
    print(f"Generated {reel_png_path}")
    print(f"Generated {reel_jpg_path}")
    rendered_count = int(settings.get("recommendations_to_render", 3))
    print("Top recommendations:")
    for rec in recommendations[:rendered_count]:
        print(f"- {rec.day_label}: {rec.window_label()} · {rec.beach_name} · {rec.activity} · score {rec.score}")


if __name__ == "__main__":
    main()
