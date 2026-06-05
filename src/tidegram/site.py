from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .recommender import BeachRecommendation, build_caption, summarize_for_site


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return output


def write_index(
    path: str | Path,
    recommendations: list[BeachRecommendation],
    metadata: dict[str, Any],
    title: str = "Marblehead Tide + Weather Outlook",
) -> Path:
    rows = summarize_for_site(recommendations)
    table_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(r['day'])}</td>"
        f"<td>{html.escape(r['best_time'])}</td>"
        f"<td>{html.escape(r['beach'])}</td>"
        f"<td>{html.escape(r['activity'])}</td>"
        f"<td>{html.escape(r['tide'])}</td>"
        f"<td>{html.escape(r['weather'])}</td>"
        "</tr>"
        for r in rows
    )
    caption = html.escape(build_caption(recommendations, metadata.get("location_name", "Marblehead, MA")))
    generated = html.escape(metadata.get("generated_at", ""))
    station = html.escape(metadata.get("noaa_station_label", metadata.get("noaa_station_id", "")))
    asset_version = str(metadata.get("asset_version", "")).strip()
    cache_suffix = f"?v={html.escape(asset_version)}" if asset_version else ""
    latest_jpg = html.escape(str(metadata.get("latest_jpg", "latest.jpg")))
    latest_png = html.escape(str(metadata.get("latest_png", "latest.png")))
    latest_jpg_versioned = f"{latest_jpg}{cache_suffix}"

    document = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{html.escape(title)}</title>
  <meta property=\"og:title\" content=\"{html.escape(title)}\" />
  <meta property=\"og:image\" content=\"{latest_jpg_versioned}\" />
  <style>
    :root {{ color-scheme: light; font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
    body {{ margin: 0; background: #f5efe3; color: #1f3750; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 32px 20px 64px; }}
    .hero {{ display: grid; gap: 20px; grid-template-columns: minmax(0, 1fr); }}
    img {{ width: min(100%, 640px); border-radius: 28px; box-shadow: 0 18px 48px rgba(31,55,80,.18); }}
    .card {{ background: white; border-radius: 24px; padding: 24px; box-shadow: 0 12px 34px rgba(31,55,80,.10); }}
    h1 {{ margin: 0 0 8px; font-size: clamp(2rem, 4vw, 3.2rem); }}
    p {{ line-height: 1.55; }}
    table {{ width: 100%; border-collapse: collapse; overflow: hidden; border-radius: 16px; background: white; }}
    th, td {{ text-align: left; padding: 12px 10px; border-bottom: 1px solid #e5edf0; vertical-align: top; }}
    th {{ background: #1f3750; color: white; }}
    code, pre {{ white-space: pre-wrap; }}
    a {{ color: #236f7a; }}
  </style>
</head>
<body>
  <main>
    <section class=\"hero\">
      <div>
        <h1>{html.escape(title)}</h1>
        <p>Generated {generated}. Tide predictions use station {station}. The image below is the direct asset used for Instagram publishing.</p>
      </div>
      <a href=\"{latest_jpg_versioned}\"><img src=\"{latest_jpg_versioned}\" alt=\"{html.escape(title)} infographic\" /></a>
    </section>

    <section class=\"card\" style=\"margin-top: 28px;\">
      <h2>Recommendations</h2>
      <table>
        <thead>
          <tr><th>Day</th><th>Best time</th><th>Beach</th><th>Activity</th><th>Tide</th><th>Weather</th></tr>
        </thead>
        <tbody>{table_rows}</tbody>
      </table>
    </section>

    <section class=\"card\" style=\"margin-top: 28px;\">
      <h2>Caption</h2>
      <pre>{caption}</pre>
      <p><a href=\"latest.json\">latest.json</a> · <a href=\"{latest_png}{cache_suffix}\">PNG</a> · <a href=\"{latest_jpg_versioned}\">JPG</a></p>
    </section>
  </main>
</body>
</html>
"""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    return output


def write_background_trials(
    path: str | Path,
    variants: list[dict[str, Any]],
    title: str = "OpenAI Background Trials",
) -> Path:
    cards = "\n".join(
        f"""
      <article class=\"trial\">
        <a href=\"{html.escape(v['jpg'])}\"><img src=\"{html.escape(v['jpg'])}\" alt=\"Trial {v['index']}\" /></a>
        <h2>Trial {v['index']}</h2>
        <p>{html.escape(v['art_direction'])}</p>
        <p><a href=\"{html.escape(v['jpg'])}\">JPG</a> | <a href=\"{html.escape(v['png'])}\">PNG</a></p>
      </article>
""".strip()
        for v in variants
    )
    document = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
    body {{ margin: 0; background: #f5efe3; color: #1f3750; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 64px; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(2rem, 4vw, 3rem); }}
    p {{ line-height: 1.55; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 22px; margin-top: 28px; }}
    .trial {{ background: white; border-radius: 18px; padding: 16px; box-shadow: 0 12px 34px rgba(31,55,80,.12); }}
    img {{ width: 100%; border-radius: 12px; display: block; box-shadow: 0 10px 26px rgba(31,55,80,.14); }}
    h2 {{ margin: 14px 0 6px; font-size: 1.1rem; }}
    a {{ color: #236f7a; }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
    <p>Full OpenAI-generated post trials using the same tide and weather data with different art-direction prompts.</p>
    <section class=\"grid\">
{cards}
    </section>
  </main>
</body>
</html>
"""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    return output
