"""X (Twitter) posting — X API v2, free tier (CLAUDE.md §4, §5).

Requires OAuth1.0a user-context credentials (posting needs write scope, which
free-tier app-only bearer tokens don't have). One-time human app setup —
Claude Code cannot click through X's consent screens.

Env vars required to actually post:
  X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET
"""
import os

import requests
from requests_oauthlib import OAuth1

TWEET_URL = "https://api.twitter.com/2/tweets"
REQUEST_TIMEOUT = 15


class PosterNotConfigured(Exception):
    pass


def _auth():
    keys = [os.environ.get(k) for k in (
        "X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET",
    )]
    if not all(keys):
        raise PosterNotConfigured("X/Twitter credentials not fully set in environment")
    return OAuth1(*keys)


def post(text, dry_run=True):
    """Returns (posted: bool, platform_post_id_or_None, detail: str)."""
    if dry_run:
        return False, None, f"[dry-run] would post to X ({len(text)} chars): {text[:80]}..."

    try:
        auth = _auth()
    except PosterNotConfigured as exc:
        return False, None, str(exc)

    resp = requests.post(TWEET_URL, auth=auth, json={"text": text}, timeout=REQUEST_TIMEOUT)
    if resp.status_code >= 300:
        return False, None, f"X API error {resp.status_code}: {resp.text[:300]}"

    data = resp.json()
    tweet_id = data.get("data", {}).get("id")
    return True, tweet_id, "posted"
