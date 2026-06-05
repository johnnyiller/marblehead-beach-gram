from __future__ import annotations

import base64
import datetime as dt
import io
import os
from pathlib import Path

from PIL import Image, ImageOps

from .recommender import BeachRecommendation


DAILY_ART_DIRECTIONS = [
    "stacked pale sky, sea-glass water, and warm sand paper layers with one tiny sail triangle near the horizon",
    "minimal dune-grass paper cutouts along the lower edge with soft golden paper sun and calm open sky",
    "simple horizontal harbor bands in dusty blue and ivory with two small sailcloth paper triangles",
    "a polished top coastal papercraft band with granite-gray shoreline, muted teal water layers, cream sky, soft sun, and one tiny distant sail; no town, lighthouse, church, houses, or large sailboat",
    "soft foggy blue paper layers with a tiny buoy circle and restrained sand-colored lower edge",
    "warm ivory sky, faded terracotta sun disk, sea-glass wave band, and sparse paper dune grass",
    "weathered shingle-gray paper sky, thin harbor-blue water strip, and one restrained lobster-buoy color accent",
    "salt-marsh paper reeds along one corner with pale sand layers, muted teal water, and wide open ivory sky",
    "simple rocky cove shapes in granite gray and sand paper with a tiny off-white sail far from the text area",
    "soft beach-rose green paper leaves near the lower edge with faded coral accent and calm sea-glass bands",
    "minimal lighthouse-red sliver on the horizon, foggy blue paper sky, and broad quiet cream negative space",
    "low-tide sandbar paper shape with shallow teal pools, tiny shell-like cutouts, and restrained warm shadows",
]


def daily_art_direction(day: dt.date | None = None) -> str:
    day = day or dt.datetime.now().date()
    return DAILY_ART_DIRECTIONS[day.toordinal() % len(DAILY_ART_DIRECTIONS)]


def numbered_art_direction(number: int) -> str:
    if number < 1 or number > len(DAILY_ART_DIRECTIONS):
        raise ValueError(f"Art direction must be between 1 and {len(DAILY_ART_DIRECTIONS)}.")
    return DAILY_ART_DIRECTIONS[number - 1]


def _format_hour(value: dt.datetime) -> str:
    hour = value.strftime("%I").lstrip("0") or "12"
    if value.minute:
        return f"{hour}:{value.strftime('%M %p')}"
    return f"{hour} {value.strftime('%p')}"


def _ordinal_day(day: int) -> str:
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _full_day_label(rec: BeachRecommendation) -> str:
    try:
        value = dt.date.fromisoformat(rec.date)
    except ValueError:
        return rec.day_label
    return f"{value.strftime('%A')} {value.strftime('%B')} {_ordinal_day(value.day)}"


def _beach_options(rec: BeachRecommendation, include_activity: bool = True) -> list[str]:
    options = [f"{rec.beach_name}: {rec.activity}" if include_activity else rec.beach_name]
    for option in rec.alternate_beaches:
        if include_activity:
            option_time = "" if option.window_label() == rec.window_label() else f", {option.window_label()}"
            option_text = f"{option.beach_name}: {option.activity}{option_time}"
        else:
            option_text = option.beach_name
        if option_text not in options:
            options.append(option_text)
    return options


def _hourly_rows(rec: BeachRecommendation) -> list[str]:
    rows = []
    for snapshot in rec.hourly_snapshots[:3]:
        temp = "--" if snapshot.temperature_f is None else f"{snapshot.temperature_f}°"
        rain = "" if snapshot.precip_probability <= 30 else f", {snapshot.precip_probability}% rain"
        wind = snapshot.wind_speed_text.replace(" to ", "-")
        rows.append(f"{_format_hour(snapshot.time)}: {temp}, {wind}{rain}; weather icon should reflect {snapshot.forecast}")
    return rows


def build_full_post_prompt(
    recommendations: list[BeachRecommendation],
    title: str,
    subtitle: str,
    location_name: str,
    art_direction: str,
) -> str:
    cards: list[str] = []
    for idx, rec in enumerate(recommendations[:3], start=1):
        tide_height = "tide height unavailable" if rec.tide_height_ft is None else f"{rec.tide_height_ft:.1f} ft"
        beach_options_text = "\n".join(_beach_options(rec, include_activity=True))
        daily_tides_text = rec.daily_tides_label()
        hourly = _hourly_rows(rec)
        hourly_text = "\n".join(hourly) if hourly else "No hourly forecast available"
        cards.append(
            f"""
Card {idx}
Day: {rec.day_label}
Time window: {rec.window_label()}
Beach options:
{beach_options_text}
Recommended tide: {tide_height} at {_format_hour(rec.tide_time)}
Tides: {daily_tides_text}
Hourly weather:
{hourly_text}
""".strip()
        )

    return f"""
Create a complete vertical 4:5 Instagram feed image for {location_name}.
Final design should look like a minimal coastal New England papercraft weather-and-tide poster.

Canvas and layout:
- Portrait 4:5 composition for Instagram.
- Clean mobile-first infographic layout with three stacked recommendation cards.
- Use the same two-column card layout on every card: left content column for day/time/beaches, right info rail for tide plus hourly weather.
- The right info rail must be consistent across all cards. Put the tide module at the top of the right info rail, then put the hourly weather rows directly below it.
- Do not move the tide module to the left side, bottom, center, or into the beach text area on any card.
- Use a polished scenic header band across the top, about 22-26% of the canvas height, with the title over or above it.
- The header should feel prettier and more designed than plain empty paper, but the recommendation cards remain the main subject.
- Prioritize the content. Give the cards, text, icons, tide values, and weather rows enough room to breathe.
- Do not compress, shrink, overlap, or squash the card content vertically just to reveal more background.
- It is okay for the cards to occupy most of the canvas if that improves readability.
- Keep card spacing compact and efficient, but never cramped, overlapping, or hard to read.
- Render exactly every hourly weather row listed for each card. If three rows are listed, show all three rows. Do not drop rows to make room for scenery.
- Put the attribution line at the very bottom as a tiny, quiet footer in much smaller print than the card text.
- Do not add any text beyond the exact text content listed below.
- Render all text crisply and exactly. Do not invent, omit, abbreviate, or alter the tide/weather numbers.
- Preserve tide times exactly, including minutes. Do not round tide times to the nearest hour.
- Tide module structure must be identical on every card:
  1. Small teal wave icon on the left.
  2. Recommended tide value on the same line, using the exact height and time from "Recommended tide".
  3. Compact high/low tide line below, using the exact text from "Tides".
- Include both the high tide and low tide information from the Tides line on every card, but do not render the label "Tides" or "Daily tides".
- Keep the high/low tide line aligned the same way on every card. Do not vary its position, icon, color, size, or layout from card to card.
- Render beach options as a compact beach-name list. Use full beach names only, for example "Gas House Beach". Do not add invitation phrasing, recommendation labels, or field labels before beach names.
- If a card has more than one beach option, keep the options visually grouped and understated. Do not number the beach options.

Visual style:
- Minimal papercraft look with layered cut-paper shapes, soft paper shadows, subtle fiber texture, and rounded handmade edges.
- Coastal New England mood: warm ivory, faded sand, sea-glass green, dusty sky blue, weathered navy, muted terracotta, soft golden paper.
- Background should be simple and quiet behind the content, with the prettiest detail concentrated in the top header band: abstract sky, water bands, sand layers, tiny sailcloth shapes, granite shoreline, and a soft sun disk.
- Do not create a village, townscape, church, lighthouse, row of houses, busy harbor illustration, or prominent sailboat. These distract from the card content.
- Icons should be simple coastal papercraft icons: sun/cloud/rain for weather and one consistent simple wave for tide.
- The tide icon must always be the same small teal three-crest wave icon. Use exactly one wave icon per card. Do not use a star, shell, anchor, water droplet, compass, badge, circle, spiral curl, or decorative surf illustration for tide.
- Do not use bookmark tabs, ribbons, flags, corner tabs, checkmarks, ratings, or left-side decorative gutters. Use that space for content instead.
- Do not use star icons anywhere. Do not place a star beside the recommended tide line.
- For hourly weather rows, show the weather condition as an icon only. Do not write forecast words like Sunny, Mostly Sunny, Partly Sunny, Cloudy, or Showers.
- Only show rain text when the rain percentage is above 30%.
- Do not use map pins, location markers, pin-drop icons, address icons, or navigation glyphs.
- Avoid photorealism, busy illustrations, tattoo styling, thick outlines, cartoon clip art, crowded scenery, decorative borders, and extra labels.
- Daily art direction: {art_direction}.

Exact text content to render:
Title: {title}
Subtitle: {subtitle}
Footer attribution: Data: NOAA tides + NWS forecast

{chr(10).join(cards)}
""".strip()


def build_reel_image_prompt(
    recommendations: list[BeachRecommendation],
    title: str,
    subtitle: str,
    location_name: str,
    art_direction: str,
) -> str:
    cards: list[str] = []
    for idx, rec in enumerate(recommendations[:3], start=1):
        tide_height = "tide height unavailable" if rec.tide_height_ft is None else f"{rec.tide_height_ft:.1f} ft"
        beach_options_text = "\n".join(_beach_options(rec, include_activity=False))
        hourly_text = "\n".join(_hourly_rows(rec)) or "No hourly forecast available"
        cards.append(
            f"""
Card {idx}
Day: {_full_day_label(rec)}
Time window: {rec.window_label()}
Beach names:
{beach_options_text}
Activity: {rec.activity}
Recommended tide: {tide_height} at {_format_hour(rec.tide_time)}
High/low tide line: {rec.daily_tides_label()}
Hourly weather:
{hourly_text}
""".strip()
        )

    return f"""
Create a complete vertical 9:16 Instagram Reel still image for {location_name}.
Final design should look like a calm, minimal coastal New England papercraft three-day beach forecast poster.

Canvas and layout:
- True 9:16 Reel composition. Do not create a 4:5 feed post centered inside a taller canvas.
- Use the whole vertical frame naturally, with no large blank padding above or below the design.
- This image will be used as the visual track for a narrated Reel, so the content must be readable on a phone.
- Show exactly three day cards, stacked vertically below the scenic header.
- Use a scenic papercraft header band across the top 20-24% of the canvas: layered sea-glass water, cream sky, warm sand, granite shoreline, tiny distant sailcloth shapes, and soft paper shadows.
- The three day cards are the main subject. Do not shrink them just to show more scenery.
- Each day card must use the same compact two-column layout: left side for day, time window, beach names, and activity; right side for tide and hourly weather.
- Make the day, beach names, and time window larger than the supporting tide/weather text, but keep all three cards balanced.
- Give every card enough room to breathe while keeping spacing compact and efficient. Do not overlap rows or shrink the hourly weather rows.
- Render exactly every hourly weather row listed below. If three rows are listed, show all three rows.
- Put the attribution line at the very bottom as tiny quiet footer text.
- Render all text crisply and exactly. Do not invent, omit, abbreviate, round, or alter any tide/weather numbers.
- Preserve tide times exactly, including minutes.
- The field names in "Exact text content to render" are source labels only. Do not render labels like Title, Subtitle, Date, Time window, Beach names, Activity, Recommended tide, High/low tide line, Hourly weather, or Footer attribution.
- Do not add labels like Best, Recommendation, or Daily Tides.
- Keep the high/low tide line exactly as written in the source value, including the words High and Low.
- Beach names must be plain full beach names. Do not add "Go to" or map/location marker text.

Visual style:
- Minimal papercraft look with layered cut-paper shapes, soft paper shadows, subtle fiber texture, and rounded handmade edges.
- Relaxed retro coastal palette: warm ivory, faded sand, sea-glass green, dusty sky blue, weathered navy, muted terracotta, soft golden paper.
- Icons should be simple coastal papercraft icons: sun/cloud/rain for weather and one consistent small teal three-crest wave for tide.
- The tide icon must be exactly one small teal three-crest wave icon. Do not use stars, shells, anchors, pins, droplets, compasses, badges, circles, spirals, or decorative surf illustrations for tide.
- Do not use bookmark tabs, ribbons, flags, corner tabs, checkmarks, ratings, or left-side decorative gutters. Use that space for content instead.
- For hourly weather rows, show the weather condition as an icon only. Do not write forecast words like Sunny, Mostly Sunny, Partly Sunny, Cloudy, or Showers.
- Only show rain text when the rain percentage is above 30%.
- Avoid photorealism, busy illustrations, tattoo styling, thick outlines, cartoon clip art, crowded scenery, decorative borders, and extra labels.
- Daily art direction: {art_direction}.

Exact text content to render:
Title: {title}
Subtitle: {subtitle}
Footer attribution: Data: NOAA tides + NWS forecast

{chr(10).join(cards)}
""".strip()


def _generate_openai_image(
    prompt: str,
    output_png: str | Path,
    output_jpg: str | Path,
    model: str,
    size: str,
    final_width: int,
    final_height: int,
) -> tuple[Path, Path]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai package is required for full-post generation. Run: pip install -r requirements.txt") from exc

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    result = client.images.generate(model=model, prompt=prompt, size=size)
    image_b64 = result.data[0].b64_json
    if not image_b64:
        raise RuntimeError("OpenAI image response did not include b64_json image data.")

    image_bytes = base64.b64decode(image_b64)
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = ImageOps.fit(img, (final_width, final_height), method=Image.Resampling.LANCZOS)

    output_png = Path(output_png)
    output_jpg = Path(output_jpg)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    output_jpg.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_png, format="PNG", optimize=True)
    img.save(output_jpg, format="JPEG", quality=92, optimize=True)
    return output_png, output_jpg


def generate_openai_full_post(
    recommendations: list[BeachRecommendation],
    output_png: str | Path,
    output_jpg: str | Path,
    model: str = "gpt-image-2",
    size: str = "1088x1360",
    final_width: int = 1080,
    final_height: int = 1350,
    title: str = "Marblehead Tide + Weather Outlook",
    subtitle: str = "Best beach windows from tides + hourly forecast",
    location_name: str = "Marblehead, MA",
    art_direction: str | None = None,
) -> tuple[Path, Path]:
    """Generate the entire Instagram post with GPT Image."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required when OpenAI full-post generation is enabled.")

    daily_direction = art_direction or daily_art_direction()
    prompt = build_full_post_prompt(
        recommendations=recommendations,
        title=title,
        subtitle=subtitle,
        location_name=location_name,
        art_direction=daily_direction,
    )

    return _generate_openai_image(
        prompt=prompt,
        output_png=output_png,
        output_jpg=output_jpg,
        model=model,
        size=size,
        final_width=final_width,
        final_height=final_height,
    )


def generate_openai_reel_image(
    recommendations: list[BeachRecommendation],
    output_png: str | Path,
    output_jpg: str | Path,
    model: str = "gpt-image-2",
    size: str = "1088x1936",
    final_width: int = 1080,
    final_height: int = 1920,
    title: str = "Marblehead Beach Outlook",
    subtitle: str = "Three-day beach windows",
    location_name: str = "Marblehead, MA",
    art_direction: str | None = None,
) -> tuple[Path, Path]:
    """Generate a Reel-native 9:16 still image with GPT Image."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required when OpenAI Reel image generation is enabled.")
    if not recommendations:
        raise RuntimeError("At least one recommendation is required to generate a Reel image.")

    daily_direction = art_direction or daily_art_direction()
    prompt = build_reel_image_prompt(
        recommendations=recommendations,
        title=title,
        subtitle=subtitle,
        location_name=location_name,
        art_direction=daily_direction,
    )
    return _generate_openai_image(
        prompt=prompt,
        output_png=output_png,
        output_jpg=output_jpg,
        model=model,
        size=size,
        final_width=final_width,
        final_height=final_height,
    )
