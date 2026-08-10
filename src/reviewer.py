"""Reviewer / Verifier (CLAUDE.md §6) — every post, every platform, every run.

Pass A: deterministic code checks, ₹0.
Pass B: a second, separate Model Router call per platform text, ₹0 but
counted in the daily volume budget (§7).

Nothing here mutates the draft to "fix" it — a failing draft is bounced back
to worker.run() with the issues attached for ONE regeneration retry. If it
fails again, that platform's post is dropped, not degraded.
"""
import json
import re

import requests

from . import config, model_router, prompt_reviewer, store

HEAD_TIMEOUT = 8


class ReviewResult:
    def __init__(self, approved, issues=None):
        self.approved = approved
        self.issues = issues or []


def _url_resolves(url):
    if not url:
        return False
    for _ in range(2):  # one retry, per spec
        try:
            resp = requests.head(url, timeout=HEAD_TIMEOUT, allow_redirects=True)
            if resp.status_code == 200:
                return True
        except requests.RequestException:
            continue
    return False


def _banned_phrase_hits(text):
    if not text:
        return []
    lowered = text.lower()
    return [p for p in config.BANNED_ABSOLUTE_PHRASES if p in lowered]


def pass_a(draft, level, ministry_handle):
    """Deterministic checks. Returns list of issue strings (empty = clean)."""
    issues = []
    handles = config.load_handles()
    core_handle = handles["core"]["always_tag"]
    central_handle = handles["core"]["central_level_tag"]

    twitter = draft.get("twitter", {})
    twitter_text = twitter.get("text", "")

    real_len = len(twitter_text)
    if real_len > config.TWITTER_CHAR_LIMIT:
        issues.append(f"twitter text is {real_len} chars (limit {config.TWITTER_CHAR_LIMIT})")

    if core_handle not in twitter_text and core_handle not in draft.get("facebook", {}).get("text", ""):
        issues.append(f"required handle {core_handle} missing from post")

    if level == "Central" and central_handle not in twitter_text \
            and central_handle not in draft.get("facebook", {}).get("text", ""):
        issues.append(f"level=Central but {central_handle} missing from post")

    # ministry handle: either explicitly empty, or must match the known/configured handle —
    # never a value the Worker invented out of thin air.
    header = draft.get("header", {})
    mentioned_office = draft.get("responsibleOffice", "")
    if ministry_handle == "" and mentioned_office and "@" in mentioned_office:
        issues.append("responsibleOffice contains an @handle but none was configured/verified")

    source_url = draft.get("sourceUrl", "")
    if not _url_resolves(source_url):
        issues.append(f"sourceUrl does not resolve with HTTP 200: {source_url}")

    if not header.get("imageUrl"):
        draft.setdefault("instagram", {})["ready"] = False

    for platform_key in ("twitter", "facebook", "instagram"):
        text = draft.get(platform_key, {}).get("text") or draft.get(platform_key, {}).get("caption") or ""
        hits = _banned_phrase_hits(text)
        if hits:
            issues.append(f"{platform_key} contains banned absolute phrase(s): {hits}")

    hashtags = twitter.get("hashtags", [])
    if len(hashtags) > config.MAX_HASHTAGS:
        issues.append(f"twitter has {len(hashtags)} hashtags, cap is {config.MAX_HASHTAGS}")

    if header.get("satire") and not header.get("factAnchor"):
        issues.append("satire=true but factAnchor is empty")

    return issues


def pass_b(conn, task, draft, article):
    """Second Model Router call: does each platform's text assert anything
    the source doesn't support? Returns list of issue strings (empty = clean)."""
    issues = []
    source_snippet = article.get("snippet") or article.get("title") or ""

    for platform_key in ("twitter", "facebook"):
        text = draft.get(platform_key, {}).get("text", "")
        if not text:
            continue
        messages = prompt_reviewer.build_verify_messages(source_snippet, text, platform_key)
        try:
            raw, provider = model_router.call_llm(
                messages, temperature=0.0, max_tokens=400,
                conn=conn, task_id=task["id"], stage="reviewer_pass_b",
            )
        except model_router.AllProvidersExhausted as exc:
            issues.append(f"Pass B unavailable for {platform_key}: {exc}")
            continue

        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            issues.append(f"Pass B returned unparseable output for {platform_key}")
            continue
        try:
            verdict = json.loads(match.group(0))
        except json.JSONDecodeError:
            issues.append(f"Pass B returned invalid JSON for {platform_key}")
            continue

        if not verdict.get("supported", False):
            for i in verdict.get("issues", [f"{platform_key}: unsupported claim(s) per Pass B"]):
                issues.append(f"{platform_key}: {i}")

    return issues


def review(conn, task, draft, article, level, ministry_handle):
    """Runs Pass A then Pass B. Returns a ReviewResult."""
    issues = pass_a(draft, level, ministry_handle)
    if issues:
        store.log(conn, task["id"], "reviewer", f"Pass A bounced: {issues}", level="warn")
        return ReviewResult(approved=False, issues=issues)

    issues = pass_b(conn, task, draft, article)
    if issues:
        store.log(conn, task["id"], "reviewer", f"Pass B bounced: {issues}", level="warn")
        return ReviewResult(approved=False, issues=issues)

    store.log(conn, task["id"], "reviewer", "approved")
    return ReviewResult(approved=True)
