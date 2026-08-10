"""Instagram posting — Meta Instagram Graph API, container -> publish flow
(CLAUDE.md §4). Requires a Business/Creator account linked to the FB Page —
one-time human setup.

Env vars required to actually post:
  IG_USER_ID, IG_ACCESS_TOKEN

Never posts if `ready` is False upstream — no exceptions, no stock photos
(Reviewer Pass A already enforces this, this is a second guard).
"""
import os

import requests

GRAPH_VERSION = "v19.0"
REQUEST_TIMEOUT = 20


def post(caption, image_url, ready, dry_run=True):
    """Returns (posted: bool, platform_post_id_or_None, detail: str)."""
    if not ready or not image_url:
        return False, None, "skipped: not ready or no image (Instagram requires an image)"

    if dry_run:
        return False, None, f"[dry-run] would post to Instagram: {caption[:80]}..."

    ig_user_id = os.environ.get("IG_USER_ID")
    token = os.environ.get("IG_ACCESS_TOKEN")
    if not ig_user_id or not token:
        return False, None, "Instagram credentials not fully set in environment"

    base = f"https://graph.facebook.com/{GRAPH_VERSION}/{ig_user_id}"

    container_resp = requests.post(
        f"{base}/media",
        data={"image_url": image_url, "caption": caption, "access_token": token},
        timeout=REQUEST_TIMEOUT,
    )
    if container_resp.status_code >= 300:
        return False, None, f"container create error {container_resp.status_code}: {container_resp.text[:300]}"
    creation_id = container_resp.json().get("id")
    if not creation_id:
        return False, None, "container create returned no id"

    publish_resp = requests.post(
        f"{base}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=REQUEST_TIMEOUT,
    )
    if publish_resp.status_code >= 300:
        return False, None, f"publish error {publish_resp.status_code}: {publish_resp.text[:300]}"

    return True, publish_resp.json().get("id"), "posted"
