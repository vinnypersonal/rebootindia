"""Worker (CLAUDE.md §3): one Model Router call, 4 personas, one JSON draft out.

extract_json() pulls the payload from between ##REBOOT_START##/##REBOOT_END##
markers and validate_draft() enforces the schema + satire/factAnchor rule
before anything reaches the Reviewer.
"""
import json
import re

from . import config, model_router, prompt_worker, store

MARKER_RE = re.compile(r"##REBOOT_START##(.*?)##REBOOT_END##", re.DOTALL)

REQUIRED_TOP_KEYS = {"problem", "solution", "sourceUrl", "ready", "header", "twitter", "facebook", "instagram"}


class WorkerError(Exception):
    pass


def extract_json(raw_text):
    match = MARKER_RE.search(raw_text)
    if not match:
        raise WorkerError("no ##REBOOT_START##/##REBOOT_END## markers found in model output")
    payload = match.group(1).strip()
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise WorkerError(f"invalid JSON between markers: {exc}") from exc


def validate_draft(draft):
    """Structural + satire-guardrail validation. Raises WorkerError on failure."""
    missing = REQUIRED_TOP_KEYS - draft.keys()
    if missing:
        raise WorkerError(f"draft missing required keys: {missing}")

    header = draft.get("header", {})
    if header.get("satire"):
        if not header.get("factAnchor"):
            raise WorkerError("satire=true but factAnchor is empty (§8 guardrail)")

    twitter_text = draft.get("twitter", {}).get("text", "")
    if len(twitter_text) > config.TWITTER_CHAR_LIMIT:
        raise WorkerError(
            f"twitter.text is {len(twitter_text)} chars, exceeds {config.TWITTER_CHAR_LIMIT}"
        )

    if not header.get("imageUrl"):
        draft.setdefault("instagram", {})["ready"] = False

    return draft


def run(conn, task, article, domain, level, city, trend_keyword,
        ministry_handle, satire_allowed, retry_issues=None):
    """Generates (and validates) one campaign draft for `task`. Returns the
    draft dict plus the provider that served it. Raises WorkerError /
    model_router.AllProvidersExhausted on unrecoverable failure — caller is
    responsible for dropping the campaign and logging."""
    handles = config.load_handles()
    core_handle = handles["core"]["always_tag"]
    central_handle = handles["core"]["central_level_tag"] if level == "Central" else ""

    messages = prompt_worker.build_messages(
        article=article,
        domain=domain,
        level=level,
        city=city,
        trend_keyword=trend_keyword,
        ministry_handle=ministry_handle,
        core_handle=core_handle,
        central_handle=central_handle,
        satire_allowed=satire_allowed,
        retry_issues=retry_issues,
    )

    raw_text, provider = model_router.call_llm(
        messages, conn=conn, task_id=task["id"], stage="worker"
    )
    draft = extract_json(raw_text)
    draft = validate_draft(draft)

    store.log(conn, task["id"], "worker",
              f"draft generated (ready={draft.get('ready')})", llm_provider=provider)
    return draft, provider
