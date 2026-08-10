"""Growth Tracker — Phase 2 (CLAUDE.md §3, §9, §11 T13).

Reads back likes/shares/comments for recently posted campaigns via the same
free X/Graph read endpoints used for posting, scores each domain/city by
average engagement, and turns that into weight multipliers director.py uses
to bias future selection order/frequency.

This is a nudge, never a gate: national domain cadence stays guaranteed
(§7) and every city still cycles through rotation regardless of weight —
low performers are never excluded, they just surface less often relative to
what resonates.

Free-tier *read* availability is not guaranteed just because posting is free
(§9 explicitly flags this as unconfirmed) — every fetch call degrades to
"no signal this run" on any failure rather than raising, so a provider
outage or a locked-down read tier never crashes the growth-review cron.
"""
from . import config, post_facebook, post_instagram, post_twitter, store

# Module references, not bound functions — .fetch_metrics is looked up at
# call time so tests (and any future hot-patching) can mock
# post_twitter.fetch_metrics etc. after this module has already been imported.
_FETCHER_MODULES = {
    "twitter": post_twitter,
    "facebook": post_facebook,
    "instagram": post_instagram,
}


def collect_engagement(conn):
    """Re-checks engagement for every posted campaign still inside the
    lookback window and appends a fresh snapshot per post. Returns the count
    of successful fetches."""
    posts = store.posts_for_engagement_refresh(
        conn, since_days=config.GROWTH_ENGAGEMENT_LOOKBACK_DAYS
    )
    fetched = 0
    for post in posts:
        module = _FETCHER_MODULES.get(post["platform"])
        if not module:
            continue
        fetch = module.fetch_metrics
        metrics = fetch(post["platform_post_id"])
        if metrics is None:
            continue
        store.record_engagement(
            conn, post["id"], post["platform"],
            likes=metrics.get("likes", 0),
            shares=metrics.get("shares", 0),
            comments=metrics.get("comments", 0),
        )
        fetched += 1

    store.log(conn, None, "growth",
              f"engagement collected for {fetched}/{len(posts)} eligible post(s)")
    return fetched


def _scores_to_weights(scores, counts):
    """Converts raw avg-engagement scores into clamped multipliers relative
    to the cross-group average. Groups below GROWTH_MIN_SAMPLE_SIZE stay
    unweighted (no signal yet, not "underperforming")."""
    eligible = {k: v for k, v in scores.items() if counts.get(k, 0) >= config.GROWTH_MIN_SAMPLE_SIZE}
    if not eligible:
        return {}
    avg = sum(eligible.values()) / len(eligible)
    if avg <= 0:
        return {}
    return {
        key: max(config.GROWTH_WEIGHT_MIN, min(config.GROWTH_WEIGHT_MAX, score / avg))
        for key, score in eligible.items()
    }


def compute_weights(conn):
    """Aggregates the latest engagement snapshot per domain/city and persists
    weight multipliers for director.py to read. Returns (domain_weights, city_weights)."""
    domain_scores, domain_counts = store.domain_engagement_scores(
        conn, since_days=config.GROWTH_SCORE_LOOKBACK_DAYS
    )
    city_scores, city_counts = store.city_engagement_scores(
        conn, since_days=config.GROWTH_SCORE_LOOKBACK_DAYS
    )

    domain_weights = _scores_to_weights(domain_scores, domain_counts)
    city_weights = _scores_to_weights(city_scores, city_counts)

    for domain_id, weight in domain_weights.items():
        store.set_weight(conn, "domain", domain_id, weight)
    for city, weight in city_weights.items():
        store.set_weight(conn, "city", city, weight)

    store.log(conn, None, "growth",
              f"weights updated: {len(domain_weights)} domain(s), {len(city_weights)} city/cities")
    return domain_weights, city_weights


def review(conn):
    """Entry point for the daily growth-review cron."""
    collect_engagement(conn)
    compute_weights(conn)
