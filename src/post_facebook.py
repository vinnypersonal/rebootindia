"""Facebook posting — Meta Graph API, Page access token (CLAUDE.md §4).

Env vars required to actually post:
  FB_PAGE_ID, FB_PAGE_ACCESS_TOKEN
"""
import os

import requests

GRAPH_VERSION = "v19.0"
REQUEST_TIMEOUT = 15


class PosterNotConfigured(Exception):
    pass


def post(text, dry_run=True):
    """Returns (posted: bool, platform_post_id_or_None, detail: str)."""
    if dry_run:
        return False, None, f"[dry-run] would post to Facebook: {text[:80]}..."

    page_id = os.environ.get("FB_PAGE_ID")
    token = os.environ.get("FB_PAGE_ACCESS_TOKEN")
    if not page_id or not token:
        return False, None, "Facebook credentials not fully set in environment"

    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{page_id}/feed"
    resp = requests.post(url, data={"message": text, "access_token": token}, timeout=REQUEST_TIMEOUT)
    if resp.status_code >= 300:
        return False, None, f"Graph API error {resp.status_code}: {resp.text[:300]}"

    data = resp.json()
    return True, data.get("id"), "posted"


def fetch_metrics(post_id):
    """Returns {'likes','shares','comments'} or None on any failure (missing
    token, API error, permission denied, etc). Growth Tracker treats None as
    no signal, never a crash."""
    token = os.environ.get("FB_PAGE_ACCESS_TOKEN")
    if not token:
        return None

    try:
        resp = requests.get(
            f"https://graph.facebook.com/{GRAPH_VERSION}/{post_id}",
            params={
                "fields": "likes.summary(true),comments.summary(true),shares",
                "access_token": token,
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "likes": data.get("likes", {}).get("summary", {}).get("total_count", 0),
            "shares": data.get("shares", {}).get("count", 0),
            "comments": data.get("comments", {}).get("summary", {}).get("total_count", 0),
        }
    except requests.RequestException:
        return None
