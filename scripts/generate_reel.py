#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCRIPT_MODEL = "gpt-5.5"
DEFAULT_TTS_MODEL = "gpt-audio-1.5"
DEFAULT_TTS_VOICE = "marin"
REEL_WIDTH = 1080
REEL_HEIGHT = 1920
DEFAULT_VOICE_LEAD_IN_SECONDS = 1.25
DEFAULT_WAVE_AUDIO_PATH = ROOT / "assets" / "audio" / "waves-public-domain.mp3"
DEFAULT_WAVE_AUDIO_SOURCE = "Wikimedia Commons File:Waves.ogg by Dsw4, public domain"
DEFAULT_WAVE_AUDIO_URL = "https://commons.wikimedia.org/wiki/File:Waves.ogg"


def clean_env_value(name: str, default: str = "") -> str:
    value = (os.getenv(name) or default).strip()
    prefix = f"{name}="
    if value.startswith(prefix):
        value = value[len(prefix) :].strip()
    return value.strip("'\"")


def truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an optional narrated Instagram Reel from the latest Tidegram image.")
    parser.add_argument("--metadata", default=str(ROOT / "site" / "latest.json"), help="Path to latest.json.")
    parser.add_argument("--output-dir", default=str(ROOT / "site"), help="Static site output directory.")
    parser.add_argument("--image", default=None, help="Override the image used for the Reel.")
    parser.add_argument("--audio", default=None, help="Use an existing narration MP3 instead of generating speech.")
    parser.add_argument("--max-days", type=int, default=1, help="Number of recommendation days to include in the narration.")
    parser.add_argument("--min-duration", type=float, default=60.0, help="Minimum Reel duration in seconds.")
    parser.add_argument("--voice-lead-in", type=float, default=DEFAULT_VOICE_LEAD_IN_SECONDS, help="Seconds of wave ambience before narration starts.")
    parser.add_argument("--script-model", default=clean_env_value("OPENAI_REEL_SCRIPT_MODEL", DEFAULT_SCRIPT_MODEL), help="OpenAI text model used to polish the narration script.")
    parser.add_argument("--no-script-polish", action="store_true", help="Use the deterministic draft narration without the LLM polish step.")
    parser.add_argument("--tts-model", default=clean_env_value("OPENAI_TTS_MODEL", DEFAULT_TTS_MODEL), help="OpenAI TTS model.")
    parser.add_argument("--voice", default=clean_env_value("OPENAI_TTS_VOICE", DEFAULT_TTS_VOICE), help="OpenAI TTS voice.")
    parser.add_argument(
        "--voice-instructions",
        default=clean_env_value(
            "OPENAI_TTS_INSTRUCTIONS",
            "Read like a friendly Marblehead local giving a calm morning beach note. Use natural pacing, small pauses, and a little emotional color from the weather. Keep it relaxed, human, and coastal, not announcer-like.",
        ),
        help="Style instructions for the TTS voice.",
    )
    parser.add_argument("--wave-audio", default=clean_env_value("REEL_WAVE_AUDIO", str(DEFAULT_WAVE_AUDIO_PATH)), help="Path to looping wave ambience audio.")
    parser.add_argument("--no-background-bed", action="store_true", help="Do not mix in the quiet wave ambience bed.")
    parser.add_argument("--print-script", action="store_true", help="Print the narration script and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned files and narration without creating audio/video.")
    return parser.parse_args()


def load_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"Metadata file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_image_path(metadata: dict[str, Any], output_dir: Path, override: str | None) -> Path:
    if override:
        image_path = Path(override)
        return image_path if image_path.is_absolute() else ROOT / image_path

    image_ref = metadata.get("dated_reel_jpg") or metadata.get("latest_reel_jpg") or metadata.get("dated_jpg") or metadata.get("latest_jpg") or "latest.jpg"
    return output_dir / image_ref


def resolve_rooted_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def relative_to_root(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def is_default_wave_audio(path: Path | None) -> bool:
    return path is not None and path.resolve() == DEFAULT_WAVE_AUDIO_PATH.resolve()


def versioned_asset_stem(metadata: dict[str, Any]) -> str:
    dated_jpg = metadata.get("dated_jpg")
    if dated_jpg:
        return Path(str(dated_jpg)).stem

    generated_at = str(metadata.get("generated_at", ""))
    date_slug = generated_at[:10] if len(generated_at) >= 10 else dt.date.today().isoformat()
    asset_version = str(metadata.get("asset_version", "")).strip() or dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S")
    return f"tidegram-{date_slug}-{asset_version}"


def local_now(metadata: dict[str, Any]) -> dt.datetime:
    tz_name = str(metadata.get("timezone") or "America/New_York")
    return dt.datetime.now(ZoneInfo(tz_name))


def strip_forecast_words(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    return text.replace("Mostly ", "").replace("Partly ", "")


def tide_phrase(label: str) -> str:
    text = (label or "").strip()
    if not text:
        return ""
    return text.replace("High:", "high tide").replace("Low:", "low tide").replace(";", ",")


def beach_phrase(rec: dict[str, Any]) -> str:
    names = [str(rec.get("beach_name") or rec.get("beach_short_name") or "the beach")]
    for option in rec.get("alternate_beaches") or []:
        name = str(option.get("beach_name") or "").strip()
        if name and name not in names:
            names.append(name)
    if len(names) == 1:
        return names[0]
    return " or ".join([", ".join(names[:-1]), names[-1]]) if len(names) > 2 else " or ".join(names)


def weather_phrase(rec: dict[str, Any]) -> str:
    pieces: list[str] = []
    temp = rec.get("temperature_f")
    if temp is not None:
        pieces.append(f"around {temp} degrees")

    forecast = strip_forecast_words(str(rec.get("forecast") or ""))
    if forecast:
        pieces.append(forecast.lower())

    wind = str(rec.get("wind_speed_text") or "").strip()
    if wind:
        pieces.append(f"wind {wind.lower()}")

    rain = int(rec.get("precip_probability") or 0)
    if rain > 30:
        pieces.append(f"{rain} percent rain chance")

    return ", ".join(pieces)


def ordinal_day(day: int) -> str:
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def spoken_date_label(rec: dict[str, Any]) -> str:
    date_value = str(rec.get("date") or "").strip()
    if date_value:
        try:
            value = dt.date.fromisoformat(date_value)
            return f"{value.strftime('%A')} {value.strftime('%B')} {ordinal_day(value.day)}"
        except ValueError:
            pass

    return str(rec.get("day_label") or "Today")


def normalize_spoken_dates(script: str, metadata: dict[str, Any], max_days: int) -> str:
    normalized = script
    for rec in list(metadata.get("recommendations") or [])[:max_days]:
        spoken = spoken_date_label(rec)
        date_value = str(rec.get("date") or "").strip()
        variants = {str(rec.get("day_label") or "").strip()}

        try:
            value = dt.date.fromisoformat(date_value)
            weekday = value.strftime("%A")
            weekday_abbr = value.strftime("%a")
            month = value.strftime("%B")
            month_abbr = value.strftime("%b")
            plain_day = str(value.day)
            ordinal = ordinal_day(value.day)
            variants.update(
                {
                    f"{weekday}, {month} {plain_day}",
                    f"{weekday}, {month} {ordinal}",
                    f"{weekday} {month} {plain_day}",
                    f"{weekday} {month} {ordinal}",
                    f"{weekday_abbr} {month_abbr} {plain_day}",
                    f"{weekday_abbr} {month_abbr} {ordinal}",
                    f"{weekday_abbr}, {month_abbr} {plain_day}",
                    f"{weekday_abbr}, {month_abbr} {ordinal}",
                }
            )
        except ValueError:
            pass

        for variant in sorted((v for v in variants if v), key=len, reverse=True):
            normalized = normalized.replace(variant, spoken)
    return re.sub(r"(\d+)(st|nd|rd|th)(st|nd|rd|th)+", r"\1\2", normalized)


def primary_recommendation(metadata: dict[str, Any]) -> dict[str, Any] | None:
    recommendations = list(metadata.get("recommendations") or [])
    return recommendations[0] if recommendations else None


def build_narration(metadata: dict[str, Any], max_days: int = 1) -> str:
    location = str(metadata.get("location_name") or "Marblehead")
    recommendations = list(metadata.get("recommendations") or [])[:max_days]
    lines = [f"Good morning {location}. Here is today's beach outlook."]

    for rec in recommendations:
        day = spoken_date_label(rec)
        window = str(rec.get("window_label") or "").strip()
        beach = beach_phrase(rec)
        weather = weather_phrase(rec)
        tides = tide_phrase(str(rec.get("daily_tides_label") or rec.get("tide_label_full") or ""))

        sentence = f"{day}: {beach}"
        if window:
            sentence += f", with the best window from {window}"
        if weather:
            sentence += f". Expect {weather}"
        if tides:
            sentence += f". Tide notes: {tides}"
        lines.append(sentence + ".")

    lines.append("Built from NOAA tides and National Weather Service hourly forecast data.")
    return " ".join(lines)


def mood_hint(rec: dict[str, Any] | None) -> str:
    if not rec:
        return "neutral and gentle"

    forecast = str(rec.get("forecast") or "").lower()
    rain = int(rec.get("precip_probability") or 0)
    score = float(rec.get("score") or 0)
    wind = str(rec.get("wind_speed_text") or "").lower()

    if rain > 50 or "thunder" in forecast:
        return "a little disappointed but still warm, practical, and helpful"
    if rain > 30 or "showers" in forecast or score < 80:
        return "softly cautious, a little wistful, but still useful"
    if score >= 130 and ("sunny" in forecast or "clear" in forecast):
        return "quietly upbeat, bright, and beach-day excited without sounding salesy"
    if "mph" in wind and any(token in wind for token in ["18", "19", "20", "21", "22"]):
        return "pleasant but a touch cautious about the breeze"
    return "relaxed, friendly, and optimistic"


def source_facts(metadata: dict[str, Any], max_days: int) -> dict[str, Any]:
    recommendations = list(metadata.get("recommendations") or [])[:max_days]
    return {
        "location": metadata.get("location_name") or "Marblehead",
        "generated_at": metadata.get("generated_at"),
        "recommendations": [
            {
                "day": spoken_date_label(rec),
                "spoken_day": spoken_date_label(rec),
                "window": rec.get("window_label"),
                "beach": beach_phrase(rec),
                "activity": rec.get("activity"),
                "weather": weather_phrase(rec),
                "forecast": rec.get("forecast"),
                "temperature_f": rec.get("temperature_f"),
                "wind_speed_text": rec.get("wind_speed_text"),
                "rain": f"{rec.get('precip_probability')} percent chance" if int(rec.get("precip_probability") or 0) > 30 else "do not mention rain",
                "tides": rec.get("daily_tides_label"),
                "score": rec.get("score"),
            }
            for rec in recommendations
        ],
    }


def polish_narration_script(metadata: dict[str, Any], draft_script: str, model: str, max_days: int) -> str:
    api_key = clean_env_value("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required to polish Reel narration.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai package is required for Reel narration. Run: pip install -r requirements.txt") from exc

    facts = source_facts(metadata, max_days)
    mood = mood_hint(primary_recommendation(metadata))
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You write short spoken local forecast scripts for a coastal New England Instagram Reel. "
                    "Sound like a real person: warm, observant, lightly conversational, and calm. "
                    "Adapt the emotional tone to the conditions. Keep every factual number exact. "
                    "Do not invent beaches, dates, times, temperatures, wind speeds, rain chances, or tide times. "
                    "Dates must use full spoken wording, like Friday June 5th. Never use abbreviations like Fri, Jun, Mon, Tue, Wed, Thu, Sat, or Sun. "
                    "Only mention rain if the facts say to mention rain. Never say zero percent chance of rain. "
                    "Do not mention scores, JSON, NOAA, NWS, or AI. Output only the spoken script."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Rewrite this draft into a natural one-day voiceover script.\n"
                    "Length target: 20 to 35 seconds of speech.\n"
                    f"Tone target: {mood}.\n"
                    "Use only these facts. Use each spoken_day exactly if you mention the date:\n"
                    f"{json.dumps(facts, indent=2)}\n\n"
                    f"Draft:\n{draft_script}"
                ),
            },
        ],
    )
    polished = (response.choices[0].message.content or "").strip()
    polished = " ".join(polished.split()) if polished else draft_script
    return normalize_spoken_dates(polished, metadata, max_days)


def build_reel_caption(metadata: dict[str, Any]) -> str:
    caption = str(metadata.get("caption") or "Marblehead tide and weather outlook.")
    disclosure = "Voiceover is AI-generated."
    if disclosure.lower() in caption.lower():
        return caption
    return f"{caption}\n\n{disclosure}"


def require_executable(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"{name} is required to build the Reel video. Install {name} and try again.")
    return path


def generate_chat_audio(script: str, output_mp3: Path, model: str, voice: str, instructions: str) -> Path:
    api_key = clean_env_value("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required to generate Reel narration.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai package is required for Reel narration. Run: pip install -r requirements.txt") from exc

    output_mp3.parent.mkdir(parents=True, exist_ok=True)
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        modalities=["text", "audio"],
        audio={"voice": voice, "format": "mp3"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Read the user's script exactly as a polished voiceover. "
                    "Do not add, remove, summarize, or rearrange words. "
                    f"Delivery notes: {instructions}"
                ),
            },
            {"role": "user", "content": script},
        ],
    )
    audio = response.choices[0].message.audio
    audio_data = getattr(audio, "data", None) if audio is not None else None
    if not audio_data:
        raise RuntimeError(f"{model} did not return audio data.")
    output_mp3.write_bytes(base64.b64decode(audio_data))
    return output_mp3


def generate_speech(script: str, output_mp3: Path, model: str, voice: str, instructions: str) -> Path:
    api_key = clean_env_value("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required to generate Reel narration.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai package is required for Reel narration. Run: pip install -r requirements.txt") from exc

    output_mp3.parent.mkdir(parents=True, exist_ok=True)
    client = OpenAI(api_key=api_key)
    with client.audio.speech.with_streaming_response.create(
        model=model,
        voice=voice,
        input=script,
        instructions=instructions,
        response_format="mp3",
    ) as response:
        response.stream_to_file(output_mp3)
    return output_mp3


def generate_narration_audio(script: str, output_mp3: Path, model: str, voice: str, instructions: str) -> Path:
    if model.startswith("gpt-audio"):
        return generate_chat_audio(script, output_mp3, model=model, voice=voice, instructions=instructions)
    return generate_speech(script, output_mp3, model=model, voice=voice, instructions=instructions)


def media_duration_seconds(path: Path) -> float:
    require_executable("ffprobe")
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def build_ffmpeg_command(
    image_path: Path,
    audio_path: Path,
    output_mp4: Path,
    include_background_bed: bool,
    min_duration_seconds: float,
    voice_lead_in_seconds: float,
    wave_audio_path: Path | None,
) -> list[str]:
    audio_duration = media_duration_seconds(audio_path)
    voice_delay_ms = max(0, round(voice_lead_in_seconds * 1000))
    target_duration = max(audio_duration + voice_lead_in_seconds, min_duration_seconds)
    fade_out_start = max(0.0, target_duration - 2.0)
    video_filter = (
        f"scale={REEL_WIDTH}:{REEL_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={REEL_WIDTH}:{REEL_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=0xF5EFE3,"
        "setsar=1"
    )

    if include_background_bed and wave_audio_path is not None:
        audio_filter = (
            f"[1:a]adelay={voice_delay_ms}:all=1,volume=1.0,asplit=2[voice][voice_sc];"
            f"[2:a]atrim=0:{target_duration:.3f},asetpts=PTS-STARTPTS,"
            "highpass=f=45,lowpass=f=6000,"
            f"afade=t=in:st=0:d=0.9,afade=t=out:st={fade_out_start:.3f}:d=2.0,volume=0.36[waves_raw];"
            "[waves_raw][voice_sc]sidechaincompress=threshold=0.025:ratio=7:attack=80:release=1400[bed];"
            f"[voice][bed]amix=inputs=2:duration=longest:dropout_transition=3,atrim=0:{target_duration:.3f}[a]"
        )
    elif include_background_bed:
        audio_filter = (
            f"[1:a]adelay={voice_delay_ms}:all=1,volume=1.0,asplit=2[voice][voice_sc];"
            f"anoisesrc=color=brown:amplitude=0.09:d={target_duration:.3f}[noise];"
            f"[noise]highpass=f=70,lowpass=f=1150,tremolo=f=0.16:d=0.70,"
            f"afade=t=in:st=0:d=0.9,afade=t=out:st={fade_out_start:.3f}:d=2.0,volume=0.18[waves];"
            "[waves][voice_sc]sidechaincompress=threshold=0.025:ratio=7:attack=80:release=1400[bed];"
            f"[voice][bed]amix=inputs=2:duration=longest:dropout_transition=3,atrim=0:{target_duration:.3f}[a]"
        )
    else:
        audio_filter = f"[1:a]adelay={voice_delay_ms}:all=1,volume=1.0,apad,atrim=0:{target_duration:.3f}[a]"

    command = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-framerate",
        "30",
        "-i",
        str(image_path),
        "-i",
        str(audio_path),
    ]
    if include_background_bed and wave_audio_path is not None:
        command.extend(["-stream_loop", "-1", "-i", str(wave_audio_path)])

    command.extend(
        [
            "-filter_complex",
            audio_filter,
            "-vf",
            video_filter,
            "-map",
            "0:v:0",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-tune",
            "stillimage",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-t",
            f"{target_duration:.3f}",
            "-movflags",
            "+faststart",
            str(output_mp4),
        ]
    )
    return command


def generate_video(
    image_path: Path,
    audio_path: Path,
    output_mp4: Path,
    include_background_bed: bool,
    min_duration_seconds: float,
    voice_lead_in_seconds: float,
    wave_audio_path: Path | None,
) -> Path:
    require_executable("ffmpeg")
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    command = build_ffmpeg_command(
        image_path,
        audio_path,
        output_mp4,
        include_background_bed,
        min_duration_seconds,
        voice_lead_in_seconds,
        wave_audio_path,
    )
    subprocess.run(command, check=True)
    return output_mp4


def write_preview(path: Path, metadata: dict[str, Any]) -> None:
    video_ref = html.escape(str(metadata.get("latest_reel_mp4") or "latest-reel.mp4"))
    image_ref = html.escape(str(metadata.get("latest_reel_jpg") or metadata.get("latest_jpg") or "latest.jpg"))
    narration = html.escape(str(metadata.get("reel_narration") or ""))
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Tidegram Reel Preview</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
    body {{ margin: 0; background: #f5efe3; color: #1f3750; }}
    main {{ max-width: 900px; margin: 0 auto; padding: 28px 20px 56px; }}
    video, img {{ width: min(100%, 420px); border-radius: 12px; box-shadow: 0 16px 42px rgba(31,55,80,.16); background: #efe6d6; }}
    .media {{ display: flex; flex-wrap: wrap; gap: 24px; align-items: flex-start; }}
    pre {{ white-space: pre-wrap; line-height: 1.5; background: white; border-radius: 8px; padding: 16px; }}
    a {{ color: #236f7a; }}
  </style>
</head>
<body>
  <main>
    <h1>Tidegram Reel Preview</h1>
    <div class="media">
      <div>
        <h2>Reel</h2>
        <video src="{video_ref}" controls playsinline preload="metadata"></video>
        <p><a href="{video_ref}">MP4</a></p>
      </div>
      <div>
        <h2>Image</h2>
        <img src="{image_ref}" alt="Tidegram image" />
        <p><a href="{image_ref}">JPG</a></p>
      </div>
    </div>
    <h2>Narration</h2>
    <pre>{narration}</pre>
  </main>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def main() -> None:
    load_dotenv(ROOT / ".env")
    args = parse_args()

    metadata_path = Path(args.metadata)
    output_dir = Path(args.output_dir)
    assets_dir = output_dir / "assets"
    metadata = load_metadata(metadata_path)
    image_path = resolve_image_path(metadata, output_dir, args.image)
    draft_script = build_narration(metadata, max_days=args.max_days)
    script = draft_script if args.no_script_polish else polish_narration_script(metadata, draft_script, args.script_model, args.max_days)
    wave_audio_path = None if args.no_background_bed else resolve_rooted_path(args.wave_audio)
    if wave_audio_path is not None and not wave_audio_path.is_file():
        print(f"WARNING: Wave audio not found at {wave_audio_path}; using synthetic ambience fallback.", file=sys.stderr)
        wave_audio_path = None

    if not image_path.is_file():
        raise RuntimeError(f"Reel source image does not exist: {image_path}")

    if args.print_script:
        print(script)
        return

    asset_stem = versioned_asset_stem(metadata)
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    latest_audio = output_dir / "latest-reel-audio.mp3"
    latest_reel = output_dir / "latest-reel.mp4"
    dated_audio = assets_dir / f"{asset_stem}-reel-audio.mp3"
    dated_reel = assets_dir / f"{asset_stem}-reel.mp4"
    audio_path = Path(args.audio) if args.audio else latest_audio

    if args.dry_run:
        print(
            json.dumps(
                {
                    "image": str(image_path),
                    "audio": str(audio_path),
                    "latest_reel": str(latest_reel),
                    "dated_reel": str(dated_reel),
                    "tts_model": args.tts_model,
                    "script_model": None if args.no_script_polish else args.script_model,
                    "voice": args.voice,
                    "min_duration": args.min_duration,
                    "voice_lead_in": args.voice_lead_in,
                    "background_bed": not args.no_background_bed,
                    "wave_audio": relative_to_root(wave_audio_path),
                    "wave_audio_source": DEFAULT_WAVE_AUDIO_SOURCE if is_default_wave_audio(wave_audio_path) else None,
                    "draft_narration": draft_script,
                    "narration": script,
                },
                indent=2,
            )
        )
        return

    if args.audio:
        audio_path = Path(args.audio)
        if not audio_path.is_file():
            raise RuntimeError(f"Narration audio does not exist: {audio_path}")
        shutil.copy2(audio_path, latest_audio)
    else:
        generate_narration_audio(script, latest_audio, model=args.tts_model, voice=args.voice, instructions=args.voice_instructions)

    shutil.copy2(latest_audio, dated_audio)
    generate_video(
        image_path,
        latest_audio,
        latest_reel,
        include_background_bed=not args.no_background_bed,
        min_duration_seconds=args.min_duration,
        voice_lead_in_seconds=args.voice_lead_in,
        wave_audio_path=wave_audio_path,
    )
    shutil.copy2(latest_reel, dated_reel)

    now = local_now(metadata).isoformat()
    metadata.update(
        {
            "reel_generated_at": now,
            "reel_video_size": f"{REEL_WIDTH}x{REEL_HEIGHT}",
            "reel_min_duration_seconds": args.min_duration,
            "reel_voice_lead_in_seconds": args.voice_lead_in,
            "reel_script_model": None if args.no_script_polish else args.script_model,
            "reel_audio_model": args.tts_model,
            "reel_voice": args.voice,
            "reel_background_bed": not args.no_background_bed,
            "reel_wave_audio": relative_to_root(wave_audio_path),
            "reel_wave_audio_source": DEFAULT_WAVE_AUDIO_SOURCE if is_default_wave_audio(wave_audio_path) else None,
            "reel_wave_audio_url": DEFAULT_WAVE_AUDIO_URL if is_default_wave_audio(wave_audio_path) else None,
            "reel_draft_narration": draft_script,
            "reel_narration": script,
            "reel_caption": build_reel_caption(metadata),
            "latest_reel_mp4": "latest-reel.mp4",
            "latest_reel_audio_mp3": "latest-reel-audio.mp3",
            "dated_reel_mp4": f"assets/{dated_reel.name}",
            "dated_reel_audio_mp3": f"assets/{dated_audio.name}",
        }
    )
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    write_preview(output_dir / "reel-preview.html", metadata)

    print(f"Generated {latest_reel}")
    print(f"Generated {dated_reel}")
    print(f"Generated {output_dir / 'reel-preview.html'}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
