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
DEFAULT_GRAPH_API_BASE_URL = "https://graph.instagram.com"


def truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def clean_env_value(name: str, default: str = "") -> str:
    value = (os.getenv(name) or default).strip()
    prefix = f"{name}="
    if value.startswith(prefix):
        value = value[len(prefix) :].strip()
    return value.strip("'\"")


def load_caption(default_caption: str, metadata_path: Path, key: str = "caption") -> str:
    if metadata_path.exists():
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        caption = payload.get(key) or payload.get("caption") or default_caption
    else:
        caption = default_caption

    disclosure = "Voiceover is AI-generated."
    if key == "reel_caption" and disclosure.lower() not in caption.lower():
        return f"{caption}\n\n{disclosure}"
    return caption


def graph_api_url(base_url: str, version: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{version.strip('/')}/{path.lstrip('/')}"


def uses_bearer_auth(base_url: str) -> bool:
    return "graph.instagram.com" in base_url.lower()


def normalize_media_type(value: str | None) -> str:
    normalized = (value or "image").strip().lower()
    if normalized in {"reel", "reels", "video"}:
        return "reel"
    return "image"


def wait_for_public_media(
    media_url: str,
    expected_content_kind: str,
    timeout_seconds: int = 180,
    interval_seconds: int = 10,
) -> None:
    """Wait until the static media URL is publicly reachable and has the expected content kind."""
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            response = requests.get(media_url, stream=True, timeout=20)
            content_type = response.headers.get("Content-Type", "").lower()
            if response.status_code == 200 and expected_content_kind in content_type:
                response.close()
                return
            last_error = f"HTTP {response.status_code}, Content-Type={content_type}"
            response.close()
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(interval_seconds)
    raise TimeoutError(f"Timed out waiting for public media URL {media_url}. Last error: {last_error}")


def wait_for_public_image(image_url: str, timeout_seconds: int = 180, interval_seconds: int = 10) -> None:
    wait_for_public_media(image_url, expected_content_kind="image", timeout_seconds=timeout_seconds, interval_seconds=interval_seconds)


def public_media_wait_seconds(default: int = 180) -> int:
    value = clean_env_value("PUBLIC_MEDIA_WAIT_SECONDS") or clean_env_value("PUBLIC_IMAGE_WAIT_SECONDS")
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError("PUBLIC_MEDIA_WAIT_SECONDS must be an integer number of seconds.") from exc


def graph_post(base_url: str, version: str, path: str, data: dict[str, Any], access_token: str) -> dict[str, Any]:
    url = graph_api_url(base_url, version, path)
    headers = {"Authorization": f"Bearer {access_token}"} if uses_bearer_auth(base_url) else None
    payload_data = data if uses_bearer_auth(base_url) else {**data, "access_token": access_token}
    response = requests.post(url, data=payload_data, headers=headers, timeout=45)
    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = {"raw": response.text}
    if response.status_code >= 400:
        raise RuntimeError(f"Graph API POST {url} failed ({response.status_code}): {payload}")
    return payload


def graph_get(base_url: str, version: str, path: str, params: dict[str, Any], access_token: str) -> dict[str, Any]:
    url = graph_api_url(base_url, version, path)
    headers = {"Authorization": f"Bearer {access_token}"} if uses_bearer_auth(base_url) else None
    query_params = params if uses_bearer_auth(base_url) else {**params, "access_token": access_token}
    response = requests.get(url, params=query_params, headers=headers, timeout=30)
    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = {"raw": response.text}
    if response.status_code >= 400:
        raise RuntimeError(f"Graph API GET {url} failed ({response.status_code}): {payload}")
    return payload


def create_media_container(
    base_url: str,
    version: str,
    ig_user_id: str,
    access_token: str,
    media_url: str,
    caption: str,
    media_type: str = "image",
    alt_text: str | None = None,
    share_to_feed: bool = True,
) -> str:
    if media_type == "reel":
        payload: dict[str, Any] = {
            "media_type": "REELS",
            "video_url": media_url,
            "caption": caption,
            "share_to_feed": "true" if share_to_feed else "false",
        }
    else:
        payload = {
            "image_url": media_url,
            "caption": caption,
        }

    if alt_text and media_type == "image":
        payload["alt_text"] = alt_text
    result = graph_post(base_url, version, f"{ig_user_id}/media", payload, access_token)
    container_id = result.get("id")
    if not container_id:
        raise RuntimeError(f"Instagram media container response did not include id: {result}")
    return str(container_id)


def wait_for_container(base_url: str, version: str, container_id: str, access_token: str, timeout_seconds: int = 120) -> None:
    """Poll media container status when the endpoint exposes it. Images are usually quick."""
    deadline = time.time() + timeout_seconds
    last_status = None
    while time.time() < deadline:
        try:
            payload = graph_get(
                base_url,
                version,
                container_id,
                {"fields": "status_code,status"},
                access_token,
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


def publish_container(base_url: str, version: str, ig_user_id: str, access_token: str, container_id: str) -> dict[str, Any]:
    return graph_post(
        base_url,
        version,
        f"{ig_user_id}/media_publish",
        {"creation_id": container_id},
        access_token,
    )


def validate_instagram_credentials(base_url: str, version: str, ig_user_id: str, access_token: str) -> None:
    payload = graph_get(
        base_url,
        version,
        ig_user_id,
        {"fields": "id,username"},
        access_token,
    )
    username = payload.get("username")
    label = f"@{username}" if username else payload.get("id", ig_user_id)
    print(f"Instagram credentials validated for {label}.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish latest Tidegram media to Instagram.")
    parser.add_argument("--image-url", default=os.getenv("PUBLIC_IMAGE_URL"), help="Public direct image URL, usually GitHub Pages latest.jpg.")
    parser.add_argument("--video-url", default=os.getenv("PUBLIC_VIDEO_URL"), help="Public direct MP4 URL for Reel publishing.")
    parser.add_argument(
        "--media-type",
        choices=["image", "reel"],
        default=normalize_media_type(os.getenv("IG_MEDIA_TYPE")),
        help="Publish a static image feed post or a Reel video.",
    )
    parser.add_argument("--metadata", default=str(ROOT / "site" / "latest.json"), help="Path to latest.json for caption.")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and print intended post without publishing.")
    parser.add_argument("--validate-credentials", action="store_true", help="Validate IG_USER_ID and IG_ACCESS_TOKEN without publishing.")
    parser.add_argument("--skip-url-wait", action="store_true", help="Do not wait for the media URL to be reachable.")
    return parser.parse_args()


def main() -> None:
    load_dotenv(ROOT / ".env")
    args = parse_args()

    media_type = args.media_type
    media_url = args.video_url if media_type == "reel" else args.image_url
    if not media_url and not args.validate_credentials:
        env_name = "PUBLIC_VIDEO_URL" if media_type == "reel" else "PUBLIC_IMAGE_URL"
        arg_name = "--video-url" if media_type == "reel" else "--image-url"
        raise RuntimeError(f"{env_name} or {arg_name} is required.")

    base_url = clean_env_value("IG_GRAPH_API_BASE_URL", DEFAULT_GRAPH_API_BASE_URL) or DEFAULT_GRAPH_API_BASE_URL
    version = clean_env_value("GRAPH_API_VERSION", "v23.0") or "v23.0"
    ig_user_id = clean_env_value("IG_USER_ID")
    access_token = clean_env_value("IG_ACCESS_TOKEN")
    alt_text = clean_env_value("ALT_TEXT") or None
    dry_run = args.dry_run or truthy(os.getenv("DRY_RUN"), default=False)
    share_to_feed = truthy(os.getenv("IG_REEL_SHARE_TO_FEED"), default=True)

    metadata_path = Path(args.metadata)
    caption = load_caption(
        "Marblehead tide + weather outlook 🌊☀️ #MarbleheadMA #NorthShoreMA",
        metadata_path,
        key="reel_caption" if media_type == "reel" else "caption",
    )

    if args.validate_credentials:
        if not ig_user_id or not access_token:
            raise RuntimeError("IG_USER_ID and IG_ACCESS_TOKEN are required to validate Instagram credentials.")
        validate_instagram_credentials(base_url, version, ig_user_id, access_token)
        return

    if dry_run:
        print("DRY RUN: would publish to Instagram")
        print(
            json.dumps(
                {
                    "media_type": media_type,
                    "media_url": media_url,
                    "caption": caption,
                    "base_url": base_url,
                    "version": version,
                    "share_to_feed": share_to_feed if media_type == "reel" else None,
                },
                indent=2,
            )
        )
        if not args.skip_url_wait:
            wait_for_public_media(
                media_url,
                expected_content_kind="video" if media_type == "reel" else "image",
                timeout_seconds=min(public_media_wait_seconds(), 60),
                interval_seconds=5,
            )
            print("Media URL is reachable.")
        return

    if not ig_user_id or not access_token:
        raise RuntimeError("IG_USER_ID and IG_ACCESS_TOKEN are required unless DRY_RUN=true.")

    if not args.skip_url_wait:
        wait_for_public_media(
            media_url,
            expected_content_kind="video" if media_type == "reel" else "image",
            timeout_seconds=public_media_wait_seconds(),
        )

    container_id = create_media_container(
        base_url=base_url,
        version=version,
        ig_user_id=ig_user_id,
        access_token=access_token,
        media_url=media_url,
        caption=caption,
        media_type=media_type,
        alt_text=alt_text,
        share_to_feed=share_to_feed,
    )
    print(f"Created Instagram media container: {container_id}")

    wait_for_container(base_url, version, container_id, access_token, timeout_seconds=600 if media_type == "reel" else 120)
    result = publish_container(base_url, version, ig_user_id, access_token, container_id)
    print(f"Published Instagram media: {json.dumps(result, indent=2)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
