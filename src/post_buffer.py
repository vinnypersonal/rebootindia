"""X (Twitter) posting via Buffer, not X's own API.

X's API moved to pay-per-use pricing with no free tier in Feb 2026 (~$0.015
per post created, no free monthly allocation) — see CLAUDE.md Prime
Directive 1 (zero variable cost). `post_twitter.py` (direct X API) is kept
in the codebase but is dormant; this module replaces it in the posting path
because Buffer's flat-rate plan posts to an already-connected X channel
without per-post API billing.

Buffer's current API is GraphQL at https://api.buffer.com, authenticated
with a Bearer API key (generate one at
https://publish.buffer.com/settings/api). The old REST API
(api.bufferapp.com) was closed to new apps in 2019 — don't use it.

Buffer's API has no "publish right now" mode: only `addToQueue` (next open
queue slot — timing not in our control) or `customScheduled` (an exact
`dueAt`). We use `customScheduled` with `dueAt` a few seconds in the future,
which is as close to immediate as the API supports.

Env vars required to actually post:
  BUFFER_API_KEY        -- from https://publish.buffer.com/settings/api
  BUFFER_X_CHANNEL_ID    -- the Buffer channel id for the connected X profile;
                             find it with `python -m src.list_buffer_channels`
"""
import datetime
import os

import requests

API_URL = "https://api.buffer.com"
REQUEST_TIMEOUT = 15
PUBLISH_DELAY_SECONDS = 10  # soonest Buffer's API supports is a near-future dueAt, not "now"

CREATE_POST_MUTATION = """
mutation CreatePost($channelId: String!, $text: String!, $dueAt: DateTime!) {
  createPost(input: {
    channelId: $channelId,
    text: $text,
    schedulingType: automatic,
    mode: customScheduled,
    dueAt: $dueAt
  }) {
    ... on PostActionSuccess {
      post { id text dueAt }
    }
    ... on MutationError {
      message
    }
  }
}
"""

POST_METRICS_QUERY = """
query GetPostMetrics($id: String!) {
  post(input: { id: $id }) {
    id
    metrics { type name value unit }
    metricsUpdatedAt
  }
}
"""


class PosterNotConfigured(Exception):
    pass


def graphql_request(query, variables=None):
    """POSTs a GraphQL query/mutation to Buffer and returns the parsed JSON
    body. Raises PosterNotConfigured if no API key is set, or
    requests.RequestException/HTTPError on transport failure. Buffer always
    returns HTTP 200 for GraphQL-level errors, so callers must still check
    the body for a top-level 'errors' array or a MutationError-shaped
    result — this function does not do that itself, so it's reusable by
    both posting and read-only queries (e.g. list_buffer_channels.py)."""
    api_key = os.environ.get("BUFFER_API_KEY")
    if not api_key:
        raise PosterNotConfigured("BUFFER_API_KEY not set in environment")

    resp = requests.post(
        API_URL,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        json={"query": query, "variables": variables or {}},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def post(text, dry_run=True):
    """Returns (posted: bool, platform_post_id_or_None, detail: str)."""
    if dry_run:
        return False, None, f"[dry-run] would post to X via Buffer ({len(text)} chars): {text[:80]}..."

    channel_id = os.environ.get("BUFFER_X_CHANNEL_ID")
    if not channel_id:
        return False, None, "BUFFER_X_CHANNEL_ID not configured"

    due_at = (
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=PUBLISH_DELAY_SECONDS)
    ).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    try:
        data = graphql_request(
            CREATE_POST_MUTATION,
            {"channelId": channel_id, "text": text, "dueAt": due_at},
        )
    except PosterNotConfigured as exc:
        return False, None, str(exc)
    except requests.RequestException as exc:
        return False, None, f"Buffer request failed: {exc}"

    top_errors = data.get("errors")
    if top_errors:
        return False, None, f"Buffer error: {top_errors[0].get('message', top_errors)}"

    result = (data.get("data") or {}).get("createPost") or {}
    post_obj = result.get("post")
    if not post_obj:
        # MutationError shape: {"message": "..."} with no "post" key
        return False, None, f"Buffer rejected post: {result.get('message', data)}"

    return True, post_obj.get("id"), f"scheduled via Buffer, due {post_obj.get('dueAt', due_at)}"


def fetch_metrics(post_id):
    """Returns {'likes','shares','comments'} or None on any failure —
    including "not available yet": Buffer refreshes metrics about once a
    day, so a just-published post legitimately has none. Also requires a
    personal API key per Buffer's docs (App Client keys can't read metrics);
    growth.py treats None as no signal either way, never a crash."""
    try:
        data = graphql_request(POST_METRICS_QUERY, {"id": post_id})
    except (PosterNotConfigured, requests.RequestException):
        return None

    if data.get("errors"):
        return None

    post_obj = (data.get("data") or {}).get("post")
    if not post_obj:
        return None

    counts = {"reactions": 0, "reposts": 0, "comments": 0}
    for metric in post_obj.get("metrics") or []:
        mtype = metric.get("type")
        if mtype in counts and metric.get("unit") == "count":
            counts[mtype] = metric.get("value") or 0

    return {
        "likes": int(counts["reactions"]),
        "shares": int(counts["reposts"]),
        "comments": int(counts["comments"]),
    }
