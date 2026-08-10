"""Website publish hook (CLAUDE.md §11 T14) — POSTs each Reviewer-approved
campaign to rebootindia.com's backend.

The exact CMS/backend for rebootindia.com wasn't specified when this was
built, so this targets a generic, documented JSON contract rather than any
specific platform's API shape (WordPress/Strapi/Contentful/etc.). Point
WEBSITE_PUBLISH_URL at whatever endpoint receives that contract — a thin
adapter on the site's backend, a serverless function, a CMS webhook
receiver — and this module doesn't need to change. If rebootindia.com later
turns out to run on a specific CMS, replace the `requests.post` call below
with that platform's client; build_payload()'s contract can stay the same.

Env vars required to actually publish:
  WEBSITE_PUBLISH_URL       -- POST endpoint that accepts the JSON below
  WEBSITE_PUBLISH_API_KEY   -- optional, sent as `Authorization: Bearer <key>`

JSON contract sent on each publish (see build_payload()):
{
  "taskId": int,
  "kind": "national" | "city" | "trend" | "followup",
  "domain": "Education" | ... | null,
  "level": "Central" | "District",
  "city": "Pune, Maharashtra" | null,
  "problem": "...",
  "solution": "...",
  "responsibleOffice": "...",
  "sourceUrl": "...",
  "imageUrl": "..." | null,
  "satire": bool,
  "factAnchor": "..." | null,
  "posts": {"twitter": "..." | null, "facebook": "..." | null, "instagram": "..." | null},
  "publishedAt": <unix timestamp, float>
}
"""
import os
import time

import requests

REQUEST_TIMEOUT = 15


def build_payload(task, draft):
    header = draft.get("header", {})
    return {
        "taskId": task["id"],
        "kind": task["kind"],
        "domain": header.get("domain"),
        "level": header.get("level"),
        "city": task.get("city"),
        "problem": draft.get("problem"),
        "solution": draft.get("solution"),
        "responsibleOffice": draft.get("responsibleOffice"),
        "sourceUrl": draft.get("sourceUrl"),
        "imageUrl": header.get("imageUrl") or None,
        "satire": bool(header.get("satire")),
        "factAnchor": header.get("factAnchor") or None,
        "posts": {
            "twitter": draft.get("twitter", {}).get("text") or None,
            "facebook": draft.get("facebook", {}).get("text") or None,
            "instagram": draft.get("instagram", {}).get("caption") or None,
        },
        "publishedAt": time.time(),
    }


def publish(payload, dry_run=True):
    """Returns (published: bool, remote_id_or_None, detail: str). Missing
    config is a graceful skip, not an error — the website hook is additive
    to the social posts, never a reason to fail a campaign."""
    if dry_run:
        return False, None, f"[dry-run] would publish to website: {(payload.get('problem') or '')[:80]}..."

    url = os.environ.get("WEBSITE_PUBLISH_URL")
    if not url:
        return False, None, "WEBSITE_PUBLISH_URL not configured — skipping website publish"

    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("WEBSITE_PUBLISH_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        return False, None, f"website publish request failed: {exc}"

    if resp.status_code >= 300:
        return False, None, f"website publish error {resp.status_code}: {resp.text[:300]}"

    try:
        data = resp.json()
    except ValueError:
        data = {}
    remote_id = data.get("id") or data.get("slug")
    return True, remote_id, "published"
