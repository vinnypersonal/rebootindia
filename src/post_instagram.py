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


def fetch_metrics(media_id):
    """Returns {'likes','shares','comments'} or None on any failure. Instagram
    Graph API has no share count for standard media, so 'shares' is always 0
    here — not a missing-data signal, a metric the platform doesn't expose."""
    token = os.environ.get("IG_ACCESS_TOKEN")
    if not token:
        return None

    try:
        resp = requests.get(
            f"https://graph.facebook.com/{GRAPH_VERSION}/{media_id}",
            params={"fields": "like_count,comments_count", "access_token": token},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "likes": data.get("like_count", 0),
            "shares": 0,
            "comments": data.get("comments_count", 0),
        }
    except requests.RequestException:
        return None
