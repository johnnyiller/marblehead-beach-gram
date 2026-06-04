#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_caption(default_caption: str, metadata_path: Path) -> str:
    if metadata_path.exists():
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        return payload.get("caption") or default_caption
    return default_caption


def wait_for_public_image(image_url: str, timeout_seconds: int = 180, interval_seconds: int = 10) -> None:
    """Wait until the static image URL is publicly reachable and looks like an image."""
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            response = requests.get(image_url, stream=True, timeout=20)
            content_type = response.headers.get("Content-Type", "").lower()
            if response.status_code == 200 and "image" in content_type:
                response.close()
                return
            last_error = f"HTTP {response.status_code}, Content-Type={content_type}"
            response.close()
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(interval_seconds)
    raise TimeoutError(f"Timed out waiting for public image URL {image_url}. Last error: {last_error}")


def graph_post(version: str, path: str, data: dict[str, Any]) -> dict[str, Any]:
    url = f"https://graph.facebook.com/{version}/{path.lstrip('/')}"
    response = requests.post(url, data=data, timeout=45)
    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = {"raw": response.text}
    if response.status_code >= 400:
        raise RuntimeError(f"Graph API POST {url} failed ({response.status_code}): {payload}")
    return payload


def graph_get(version: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"https://graph.facebook.com/{version}/{path.lstrip('/')}"
    response = requests.get(url, params=params, timeout=30)
    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = {"raw": response.text}
    if response.status_code >= 400:
        raise RuntimeError(f"Graph API GET {url} failed ({response.status_code}): {payload}")
    return payload


def create_media_container(
    version: str,
    ig_user_id: str,
    access_token: str,
    image_url: str,
    caption: str,
    alt_text: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "image_url": image_url,
        "caption": caption,
        "access_token": access_token,
    }
    if alt_text:
        payload["alt_text"] = alt_text
    result = graph_post(version, f"{ig_user_id}/media", payload)
    container_id = result.get("id")
    if not container_id:
        raise RuntimeError(f"Instagram media container response did not include id: {result}")
    return str(container_id)


def wait_for_container(version: str, container_id: str, access_token: str, timeout_seconds: int = 120) -> None:
    """Poll media container status when the endpoint exposes it. Images are usually quick."""
    deadline = time.time() + timeout_seconds
    last_status = None
    while time.time() < deadline:
        try:
            payload = graph_get(
                version,
                container_id,
                {"fields": "status_code,status", "access_token": access_token},
            )
            last_status = payload.get("status_code") or payload.get("status")
            if last_status in {"FINISHED", "PUBLISHED"}:
                return
            if last_status in {"ERROR", "EXPIRED"}:
                raise RuntimeError(f"Instagram container status: {payload}")
        except RuntimeError as exc:
            # Some Graph API configurations do not expose status for image containers.
            # A short delay is still useful before publishing.
            last_status = str(exc)
        time.sleep(10)
    # Do not fail hard if status polling is unavailable; publish may still succeed.
    print(f"Container status polling timed out/unavailable; attempting publish. Last status: {last_status}")


def publish_container(version: str, ig_user_id: str, access_token: str, container_id: str) -> dict[str, Any]:
    return graph_post(
        version,
        f"{ig_user_id}/media_publish",
        {"creation_id": container_id, "access_token": access_token},
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish latest Tidegram image to Instagram.")
    parser.add_argument("--image-url", default=os.getenv("PUBLIC_IMAGE_URL"), help="Public direct image URL, usually GitHub Pages latest.jpg.")
    parser.add_argument("--metadata", default=str(ROOT / "site" / "latest.json"), help="Path to latest.json for caption.")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and print intended post without publishing.")
    parser.add_argument("--skip-url-wait", action="store_true", help="Do not wait for image URL to be reachable.")
    return parser.parse_args()


def main() -> None:
    load_dotenv(ROOT / ".env")
    args = parse_args()

    image_url = args.image_url
    if not image_url:
        raise RuntimeError("PUBLIC_IMAGE_URL or --image-url is required.")

    version = os.getenv("GRAPH_API_VERSION", "v23.0")
    ig_user_id = os.getenv("IG_USER_ID", "")
    access_token = os.getenv("IG_ACCESS_TOKEN", "")
    alt_text = os.getenv("ALT_TEXT")
    dry_run = args.dry_run or truthy(os.getenv("DRY_RUN"), default=False)

    metadata_path = Path(args.metadata)
    caption = load_caption(
        "Marblehead tide + weather outlook 🌊☀️ #MarbleheadMA #NorthShoreMA",
        metadata_path,
    )

    if dry_run:
        print("DRY RUN: would publish to Instagram")
        print(json.dumps({"image_url": image_url, "caption": caption, "version": version}, indent=2))
        if not args.skip_url_wait:
            wait_for_public_image(image_url, timeout_seconds=60, interval_seconds=5)
            print("Image URL is reachable.")
        return

    if not ig_user_id or not access_token:
        raise RuntimeError("IG_USER_ID and IG_ACCESS_TOKEN are required unless DRY_RUN=true.")

    if not args.skip_url_wait:
        wait_for_public_image(image_url)

    container_id = create_media_container(
        version=version,
        ig_user_id=ig_user_id,
        access_token=access_token,
        image_url=image_url,
        caption=caption,
        alt_text=alt_text,
    )
    print(f"Created Instagram media container: {container_id}")

    wait_for_container(version, container_id, access_token)
    result = publish_container(version, ig_user_id, access_token, container_id)
    print(f"Published Instagram media: {json.dumps(result, indent=2)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
