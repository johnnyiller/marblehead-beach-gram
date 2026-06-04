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
        beach_options = [f"{rec.beach_name}: {rec.activity}"]
        for option in rec.alternate_beaches:
            option_time = "" if option.window_label() == rec.window_label() else f", {option.window_label()}"
            beach_options.append(f"{option.beach_name}: {option.activity}{option_time}")
        beach_options_text = "\n".join(beach_options)
        daily_tides_text = rec.daily_tides_label()
        hourly = []
        for snapshot in rec.hourly_snapshots[:3]:
            temp = "--" if snapshot.temperature_f is None else f"{snapshot.temperature_f}°"
            rain = "" if snapshot.precip_probability <= 30 else f", {snapshot.precip_probability}% rain"
            wind = snapshot.wind_speed_text.replace(" to ", "-")
            hourly.append(f"{_format_hour(snapshot.time)}: {temp}, {wind}{rain}; weather icon should reflect {snapshot.forecast}")
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
- Use a simple right-side column inside each card for tide and hourly weather.
- Use a polished scenic header band across the top, about 22-26% of the canvas height, with the title over or above it.
- The header should feel prettier and more designed than plain empty paper, but the recommendation cards remain the main subject.
- Prioritize the content. Give the cards, text, icons, tide values, and weather rows enough room to breathe.
- Do not compress, shrink, overlap, or squash the card content vertically just to reveal more background.
- It is okay for the cards to occupy most of the canvas if that improves readability.
- Render exactly every hourly weather row listed for each card. If three rows are listed, show all three rows. Do not drop rows to make room for scenery.
- Put the attribution line at the very bottom as a tiny, quiet footer in much smaller print than the card text.
- Do not add any text beyond the exact text content listed below.
- Render all text crisply and exactly. Do not invent, omit, abbreviate, or alter the tide/weather numbers.
- Preserve tide times exactly, including minutes. Do not round tide times to the nearest hour.
- Include both the high tide and low tide information from the Tides line on every card, but do not render the label "Tides" or "Daily tides". Put the high/low values next to the simple wave icon.
- Render beach options as a compact beach-name list. Use full beach names only, for example "Gas House Beach". Do not add invitation phrasing, recommendation labels, or field labels before beach names.
- If a card has more than one beach option, keep the options visually grouped and understated. Do not number the beach options.

Visual style:
- Minimal papercraft look with layered cut-paper shapes, soft paper shadows, subtle fiber texture, and rounded handmade edges.
- Coastal New England mood: warm ivory, faded sand, sea-glass green, dusty sky blue, weathered navy, muted terracotta, soft golden paper.
- Background should be simple and quiet behind the content, with the prettiest detail concentrated in the top header band: abstract sky, water bands, sand layers, tiny sailcloth shapes, granite shoreline, and a soft sun disk.
- Do not create a village, townscape, church, lighthouse, row of houses, busy harbor illustration, or prominent sailboat. These distract from the card content.
- Icons should be simple coastal papercraft icons: sun/cloud/rain for weather, a simple wave for tide, and a small plain bookmark tab as a quiet decorative accent.
- The bookmark tab should be plain. Do not put stars, checkmarks, numbers, ratings, or symbols inside it.
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

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai package is required for full-post generation. Run: pip install -r requirements.txt") from exc

    client = OpenAI(api_key=api_key)
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
