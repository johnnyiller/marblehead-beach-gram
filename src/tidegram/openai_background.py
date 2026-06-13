from __future__ import annotations

import base64
import datetime as dt
import io
import os
import re
from pathlib import Path

from PIL import Image, ImageOps

from .recommender import BeachRecommendation


DAILY_ART_DIRECTIONS = [
    "stacked pale sky, sea-glass water, and warm sand bands with one tiny sail triangle near the horizon",
    "minimal dune grass along the lower edge with soft golden sun and calm open sky",
    "simple horizontal harbor bands in dusty blue and ivory with two small sailcloth triangles",
    "a polished top coastal band with granite-gray shoreline, muted teal water layers, cream sky, soft sun, and one tiny distant sail; no town, church, houses, or large focal sailboat",
    "soft foggy blue layers with a tiny buoy circle and restrained sand-colored lower edge",
    "warm ivory sky, faded terracotta sun disk, sea-glass wave band, and sparse dune grass",
    "weathered shingle-gray sky, thin harbor-blue water strip, and one restrained lobster-buoy color accent",
    "salt-marsh reeds along one corner with pale sand layers, muted teal water, and wide open ivory sky",
    "simple rocky cove shapes in granite gray and sand with a tiny off-white sail far from the text area",
    "soft beach-rose green leaves near the lower edge with faded coral accent and calm sea-glass bands",
    "minimal lighthouse-red sliver on the horizon, foggy blue sky, and broad quiet cream negative space",
    "low-tide sandbar shape with shallow teal pools, tiny shell-like marks, and restrained warm shadows",
]

VISUAL_STYLE_DIRECTIONS = [
    {
        "label": "papercraft",
        "direction": (
            "layered cut-paper shapes, soft paper shadows, subtle fiber texture, rounded handmade edges, "
            "and simple coastal paper icons"
        ),
    },
    {
        "label": "watercolor field journal",
        "direction": (
            "soft watercolor washes, light ink contour lines, warm sketchbook paper grain, restrained hand-painted "
            "weather icons, and airy negative space"
        ),
    },
    {
        "label": "vintage harbor postcard",
        "direction": (
            "slightly faded postcard color, gentle print texture, clean mid-century travel-poster geometry, "
            "small flat weather icons, and tidy editorial spacing"
        ),
    },
    {
        "label": "risograph coast",
        "direction": (
            "muted two- or three-ink risograph texture, tiny registration offsets, simple blocky coastal shapes, "
            "limited spot color, and crisp readable typography"
        ),
    },
    {
        "label": "nautical chart note",
        "direction": (
            "cream chart-paper texture, thin navy linework, subtle contour and current-line accents, small stamped "
            "weather icons, and a tidy field-note feeling"
        ),
    },
    {
        "label": "soft linocut",
        "direction": (
            "gentle linocut-inspired coastal shapes, softened ink edges, sparse hatch texture, restrained color blocks, "
            "and simple carved-looking icons"
        ),
    },
]

COASTAL_MOTIF_DIRECTIONS = [
    "one tiny lighthouse accent far on the horizon, reduced to a simple cream-and-red shape",
    "flat granite rock shapes and a few quiet tide-pool ovals along the header shoreline",
    "two small lobster traps and a muted buoy tucked near one header edge, not touching text",
    "two distant sailboats with simple off-white triangular sails, kept tiny and far from the cards",
    "a pair of paddleboards resting on warm sand as flat silhouettes in the header",
    "beach-rose leaves and sparse dune grass as small lower-edge accents",
    "a low island silhouette with a few harbor mooring dots in muted navy and teal",
    "a weathered dinghy shape pulled high on the sand, simplified and quiet",
]


def _parse_wind_mph(wind_speed_text: str) -> float:
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", wind_speed_text or "")]
    return max(nums) if nums else 0.0


def _condition_for_values(forecasts: list[str], rain_chance: int, wind_mph: float) -> str:
    text = " ".join(forecasts).lower()
    if "thunder" in text or rain_chance >= 55:
        return "stormy"
    if rain_chance > 30 or "rain" in text or "showers" in text or "drizzle" in text:
        return "rainy"
    if wind_mph >= 18:
        return "windy"
    if "fog" in text or "mist" in text or "haze" in text:
        return "foggy"
    if "overcast" in text or "cloudy" in text:
        return "cloudy"
    if "sunny" in text or "clear" in text:
        return "sunny"
    return "calm"


def _condition_for_recommendation(rec: BeachRecommendation) -> str:
    forecasts = [rec.forecast, *[snapshot.forecast for snapshot in rec.hourly_snapshots]]
    rain = max([rec.precip_probability, *[snapshot.precip_probability for snapshot in rec.hourly_snapshots]] or [0])
    wind = max([_parse_wind_mph(rec.wind_speed_text), *[_parse_wind_mph(snapshot.wind_speed_text) for snapshot in rec.hourly_snapshots]] or [0.0])
    return _condition_for_values(forecasts, rain, wind)


def weather_background_direction(recommendations: list[BeachRecommendation] | None) -> str:
    if not recommendations:
        return "Weather cue: calm morning beach light with clean cream sky and soft sea-glass water."

    primary = recommendations[0]
    condition = _condition_for_recommendation(primary)
    if condition == "stormy":
        return "Weather cue: moody rain-ready coast with layered slate-gray clouds, darker teal water, and a few tiny raindrop accents; still calm, readable, and not dramatic."
    if condition == "rainy":
        return "Weather cue: soft rainy beach morning with pale gray-blue clouds, muted water, tiny raindrop accents, and gentle reflected light."
    if condition == "windy":
        return "Weather cue: breezy harbor day with subtle swept cloud strips, angled dune grass, and a little motion in the water bands."
    if condition == "foggy":
        return "Weather cue: quiet fog bank with translucent-looking blue-gray layers, softened horizon, and low-contrast coastal shapes."
    if condition == "cloudy":
        return "Weather cue: relaxed cloudy coast with layered off-white and blue-gray cloud cutouts, muted sun glow, and calm water."
    if condition == "sunny":
        return "Weather cue: warm sunny beach day with a soft golden sun disk, bright cream sky, and lightly sparkling sea-glass water."
    return "Weather cue: calm coastal morning with balanced sky, water, sand, and soft shadows."


def coastal_motif_direction(day: dt.date | None = None, offset: int = 0) -> str:
    day = day or dt.datetime.now().date()
    return COASTAL_MOTIF_DIRECTIONS[(day.toordinal() + offset) % len(COASTAL_MOTIF_DIRECTIONS)]


def visual_style_direction(day: dt.date | None = None, offset: int = 0) -> str:
    day = day or dt.datetime.now().date()
    style = VISUAL_STYLE_DIRECTIONS[(day.toordinal() + offset) % len(VISUAL_STYLE_DIRECTIONS)]
    return f"{style['label']}: {style['direction']}"


def card_weather_cues(recommendations: list[BeachRecommendation] | None) -> str:
    if not recommendations:
        return "No card-specific weather accents needed."
    cues = [
        f"{_full_day_label(rec)}: {_condition_for_recommendation(rec)}"
        for rec in recommendations[:3]
    ]
    return "Card weather cues: " + "; ".join(cues) + "."


def compose_art_direction(
    base_direction: str,
    recommendations: list[BeachRecommendation] | None = None,
    day: dt.date | None = None,
    offset: int = 0,
) -> str:
    weather = weather_background_direction(recommendations)
    style = visual_style_direction(day, offset=offset)
    motif = coastal_motif_direction(day, offset=offset)
    cues = card_weather_cues(recommendations)
    return (
        f"{base_direction}; Visual style profile: {style}. {weather} Rotating coastal motif: {motif}. "
        f"{cues} Keep all weather, texture, and motif details minimal, quiet, and behind or above the content"
    )


def daily_art_direction(day: dt.date | None = None, recommendations: list[BeachRecommendation] | None = None) -> str:
    day = day or dt.datetime.now().date()
    base_direction = DAILY_ART_DIRECTIONS[day.toordinal() % len(DAILY_ART_DIRECTIONS)]
    if recommendations is None:
        return base_direction
    return compose_art_direction(base_direction, recommendations=recommendations, day=day)


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
Left column:
Day: {rec.day_label}
Time window: {rec.window_label()}
Beach options:
{beach_options_text}
Right rail:
Recommended tide: {tide_height} at {_format_hour(rec.tide_time)}
High/low tide line: {daily_tides_text}
Hourly weather:
{hourly_text}
""".strip()
        )

    return f"""
Create a complete vertical 4:5 Instagram feed image for {location_name}.
Final design should look like a minimal coastal New England weather-and-tide poster in the visual style specified by the Daily art direction.

Canvas and layout:
- Portrait 4:5 composition for Instagram.
- Clean mobile-first infographic layout with three stacked recommendation cards.
- Use the same two-column card layout on every card: left content column for day/time/beaches, right info rail for tide plus hourly weather.
- Render the "Left column" source content only in the left content column.
- Render the "Right rail" source content only in the right info rail.
- The right info rail must be consistent across all cards. Put the tide module at the top of the right info rail, then put the hourly weather rows directly below it.
- Do not move the tide module to the left side, bottom, center, or into the beach text area on any card.
- Do not render any tide text, tide times, high tide text, low tide text, tide height, or wave icon in the left content column.
- Render the recommended tide line and high/low tide line exactly once per card, only in the right info rail.
- Never duplicate the high/low tide line on both sides of a card.
- Use a polished scenic header band across the top, about 22-26% of the canvas height, with the title over or above it.
- The header should feel prettier and more designed than plain empty space, but the recommendation cards remain the main subject.
- Prioritize the content. Give the cards, text, icons, tide values, and weather rows enough room to breathe.
- Do not compress, shrink, overlap, or squash the card content vertically just to reveal more background.
- It is okay for the cards to occupy most of the canvas if that improves readability.
- Keep card spacing compact and efficient, but never cramped, overlapping, or hard to read.
- Render exactly every hourly weather row listed for each card. If three rows are listed, show all three rows. Do not drop rows to make room for scenery.
- Put the attribution line at the very bottom as a tiny, quiet footer in much smaller print than the card text.
- Do not add any text beyond the exact text content listed below.
- The labels Card, Left column, Right rail, Day, Time window, Beach options, Recommended tide, High/low tide line, Hourly weather, Title, Subtitle, and Footer attribution are source labels only. Do not render those labels.
- Render all text crisply and exactly. Do not invent, omit, abbreviate, or alter the tide/weather numbers.
- Preserve tide times exactly, including minutes. Do not round tide times to the nearest hour.
- Tide module structure must be identical on every card:
  1. Small teal wave icon on the left within the right-rail tide module.
  2. Recommended tide value on the same line, using the exact height and time from "Recommended tide".
  3. Compact high/low tide line below, using the exact text from "High/low tide line".
- Include both the high tide and low tide information from the high/low tide line on every card, but do not render the labels "High/low tide line", "Tides", or "Daily tides".
- Keep the high/low tide line aligned the same way on every card. Do not vary its position, icon, color, size, or layout from card to card.
- Render beach options as a compact beach-name list. Use full beach names only, for example "Gas House Beach". Do not add invitation phrasing, recommendation labels, or field labels before beach names.
- If a card has more than one beach option, keep the options visually grouped and understated. Do not number the beach options.

Visual style:
- Follow the Visual style profile inside the Daily art direction. Let that selected medium drive texture, edges, icon treatment, and background rendering.
- Keep the style variation tasteful and restrained; the post should still feel like the same Marblehead beach outlook series.
- Coastal New England mood: warm ivory, faded sand, sea-glass green, dusty sky blue, weathered navy, muted terracotta, and soft golden accents.
- Background should be simple and quiet behind the content, with the prettiest detail concentrated in the top header band.
- Let the background weather match the forecast cues in the daily art direction: rainy days can use soft clouds and tiny raindrops, windy days can use swept cloud strips and angled dune grass, cloudy/foggy days can use muted layered skies, and sunny days can use warm light.
- The daily art direction may specify one coastal New England motif such as a lighthouse, granite rocks, lobster traps, sailboats, paddleboards, beach roses, buoys, or a dinghy. Include that motif only as a small quiet accent in the header or background. It must never crowd, cover, or compete with the text.
- Do not create a village, townscape, church, row of houses, busy harbor illustration, or large focal object. These distract from the card content.
- Icons should be simple coastal icons matching the selected visual style: sun/cloud/rain for weather and one consistent simple wave for tide.
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
Left column:
Day: {_full_day_label(rec)}
Time window: {rec.window_label()}
Beach names:
{beach_options_text}
Activity: {rec.activity}
Right rail:
Recommended tide: {tide_height} at {_format_hour(rec.tide_time)}
High/low tide line: {rec.daily_tides_label()}
Hourly weather:
{hourly_text}
""".strip()
        )

    return f"""
Create a complete vertical 9:16 Instagram Reel still image for {location_name}.
Final design should look like a calm, minimal coastal New England three-day beach forecast poster in the visual style specified by the Daily art direction.

Canvas and layout:
- True 9:16 Reel composition. Do not create a 4:5 feed post centered inside a taller canvas.
- Use the whole vertical frame naturally, with no large blank padding above or below the design.
- This image will be used as the visual track for a narrated Reel, so the content must be readable on a phone.
- Show exactly three day cards, stacked vertically below the scenic header.
- Use a scenic header band across the top 20-24% of the canvas: layered sea-glass water, cream sky, warm sand, granite shoreline, tiny distant sailcloth shapes, and soft shadows.
- The three day cards are the main subject. Do not shrink them just to show more scenery.
- Each day card must use the same compact two-column layout: left side for day, time window, beach names, and activity; right side for tide and hourly weather.
- Render the "Left column" source content only in the left side of the card.
- Render the "Right rail" source content only in the right side of the card.
- Do not render any tide text, tide times, high tide text, low tide text, tide height, or wave icon in the left side of the card.
- Render the recommended tide line and high/low tide line exactly once per card, only in the right side of the card.
- Never duplicate the high/low tide line on both sides of a card.
- Make the day, beach names, and time window larger than the supporting tide/weather text, but keep all three cards balanced.
- Give every card enough room to breathe while keeping spacing compact and efficient. Do not overlap rows or shrink the hourly weather rows.
- Render exactly every hourly weather row listed below. If three rows are listed, show all three rows.
- Put the attribution line at the very bottom as tiny quiet footer text.
- Render all text crisply and exactly. Do not invent, omit, abbreviate, round, or alter any tide/weather numbers.
- Preserve tide times exactly, including minutes.
- The field names in "Exact text content to render" are source labels only. Do not render labels like Title, Subtitle, Left column, Right rail, Date, Time window, Beach names, Activity, Recommended tide, High/low tide line, Hourly weather, or Footer attribution.
- Do not add labels like Best, Recommendation, or Daily Tides.
- Keep the high/low tide line exactly as written in the source value, including the words High and Low.
- Beach names must be plain full beach names. Do not add "Go to" or map/location marker text.

Visual style:
- Follow the Visual style profile inside the Daily art direction. Let that selected medium drive texture, edges, icon treatment, and background rendering.
- Keep the style variation tasteful and restrained; the Reel still should still feel like the same Marblehead beach outlook series.
- Relaxed retro coastal palette: warm ivory, faded sand, sea-glass green, dusty sky blue, weathered navy, muted terracotta, and soft golden accents.
- Let the background weather match the forecast cues in the daily art direction: rainy days can use soft clouds and tiny raindrops, windy days can use swept cloud strips and angled dune grass, cloudy/foggy days can use muted layered skies, and sunny days can use warm light.
- The daily art direction may specify one coastal New England motif such as a lighthouse, granite rocks, lobster traps, sailboats, paddleboards, beach roses, buoys, or a dinghy. Include that motif only as a small quiet accent in the header or background. It must never crowd, cover, or compete with the text.
- Do not create a village, townscape, church, row of houses, busy harbor illustration, or large focal object. These distract from the card content.
- Icons should be simple coastal icons matching the selected visual style: sun/cloud/rain for weather and one consistent small teal three-crest wave for tide.
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
