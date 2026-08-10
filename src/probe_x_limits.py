"""T4b: probe X API's actual current free-tier write cap.

X does not expose a read-only "how many posts do I have left" endpoint for
the free tier — the only reliable signal is the rate-limit response headers
X returns on an actual write call (CLAUDE.md §4/§11 T4b). So this script:

  1. posts ONE short, obviously-a-probe test tweet,
  2. reads back the rate-limit headers X returns on that response,
  3. deletes the test tweet immediately,
  4. prints what it found so a human can update config.DAILY_CAMPAIGN_CAP.

This is a real, if brief, write to the connected X account — visible to
anyone watching the timeline in the seconds before it's deleted. It is NOT
wired into any GitHub Actions workflow and is NOT something Claude Code runs
on its own; it requires a human to run it with live credentials AND pass
--yes. Re-verify the limit periodically — CLAUDE.md §3a notes these free-tier
numbers move without notice.

Usage (requires the same env vars as post_twitter.py):
    python -m src.probe_x_limits --yes
"""
import argparse
import sys
import time

import requests

from . import config, post_twitter

TEST_TEXT_PREFIX = "RebootIndia cap probe (auto-deleted, please ignore)"


def extract_rate_limit_headers(headers):
    """Pulls out the subset of response headers that carry rate-limit info.
    Pure function, no I/O — kept separate so it's unit-testable without
    hitting the network or posting anything."""
    return {k: v for k, v in headers.items() if "limit" in k.lower() or "rate" in k.lower()}


def run(confirmed):
    if not confirmed:
        print("Refusing to run without --yes: this posts one real (if brief) tweet to the")
        print("connected X account and deletes it immediately. Re-run with --yes to proceed.")
        return 1

    try:
        auth = post_twitter._auth()
    except post_twitter.PosterNotConfigured as exc:
        print(f"Cannot probe: {exc}")
        return 1

    text = f"{TEST_TEXT_PREFIX} {int(time.time())}"
    print("Posting one throwaway test tweet to read X's rate-limit headers...")
    resp = requests.post(
        post_twitter.TWEET_URL, auth=auth, json={"text": text},
        timeout=post_twitter.REQUEST_TIMEOUT,
    )

    rate_headers = extract_rate_limit_headers(resp.headers)
    print(f"Response status: {resp.status_code}")
    print("Rate-limit headers:")
    for k, v in sorted(rate_headers.items()):
        print(f"  {k}: {v}")

    if resp.status_code >= 300:
        print(f"Post failed: {resp.text[:300]}")
        print("A 403/429 here is itself informative — the headers above may still show the cap.")
        return 0

    tweet_id = resp.json().get("data", {}).get("id")
    if tweet_id:
        print(f"Test tweet posted ({tweet_id}), deleting it now...")
        del_resp = requests.delete(
            f"{post_twitter.TWEET_URL}/{tweet_id}", auth=auth,
            timeout=post_twitter.REQUEST_TIMEOUT,
        )
        print(f"Delete status: {del_resp.status_code}"
              + ("" if del_resp.status_code < 300 else f" — {del_resp.text[:200]}"))

    print()
    print(f"Current config.DAILY_CAMPAIGN_CAP default: {config.DAILY_CAMPAIGN_CAP}")
    print("If the 24-hour write limit shown above is lower than that, set")
    print("REBOOT_DAILY_CAMPAIGN_CAP in GitHub Actions Secrets/Variables (or lower the")
    print("default in src/config.py) to match before enabling REBOOT_LIVE_POSTING.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true",
                         help="Confirm you understand this posts and deletes one real test tweet.")
    args = parser.parse_args()
    sys.exit(run(confirmed=args.yes))


if __name__ == "__main__":
    main()
