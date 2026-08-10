"""Trend Scout (CLAUDE.md §3, §4): hourly, code-only, ₹0.

Two free signal sources:
  1. Google Trends India daily RSS — official, no key.
  2. GDELT article-volume timeline per tracked domain keyword — spike =
     latest point far above the rolling average, pure math on data GDELT
     already serves for free.

Both feed store.record_trend(); trend_seen_recently() handles the 24h dedup
so the same trend doesn't spawn a task on every hourly run.
"""
import xml.etree.ElementTree as ET

import requests

from . import config, store

# CLAUDE.md §4 names the old /trends/trendingsearches/daily/rss path; Google retired that
# URL (verified 404 at build time) and moved trending RSS to /trending/rss. Same feed shape.
GOOGLE_TRENDS_RSS = "https://trends.google.com/trending/rss?geo=IN"
GDELT_TIMELINE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
REQUEST_TIMEOUT = 15
SPIKE_RATIO_THRESHOLD = 2.0  # latest point must be >= 2x the rolling average to count as a spike


def fetch_google_trends_india():
    """Returns a list of trending search terms (strings), most significant first."""
    resp = requests.get(GOOGLE_TRENDS_RSS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    terms = []
    for item in root.findall(".//item"):
        title = item.findtext("title")
        if title:
            terms.append(title.strip())
    return terms


def gdelt_spike_score(keyword, timespan="24h"):
    """Volume-intensity timeline for `keyword`; returns (is_spike, ratio) where
    ratio = latest_value / avg(previous_values). None values are skipped."""
    params = {
        "query": f"{keyword} sourcecountry:IN",
        "mode": "timelinevol",
        "format": "json",
        "timespan": timespan,
    }
    resp = requests.get(GDELT_TIMELINE_URL, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        return False, 0.0

    series = data.get("timeline", [])
    if not series:
        return False, 0.0
    points = [p.get("value", 0) for p in series[0].get("data", [])]
    if len(points) < 4:
        return False, 0.0

    latest = points[-1]
    baseline = points[:-1]
    avg = sum(baseline) / len(baseline) if baseline else 0
    if avg <= 0:
        return False, 0.0
    ratio = latest / avg
    return ratio >= SPIKE_RATIO_THRESHOLD, ratio


def scan_and_enqueue(conn):
    """Hourly entry point: pulls Google Trends + runs GDELT spike check on
    every tracked domain keyword, inserts deduped HIGH-priority trend tasks."""
    inserted = 0

    try:
        trending_terms = fetch_google_trends_india()
    except Exception as exc:
        store.log(conn, None, "trend_scout", f"Google Trends RSS failed: {exc}", level="warn")
        trending_terms = []

    for term in trending_terms:
        if store.trend_seen_recently(conn, term, hours=24):
            continue
        if store.record_trend(conn, term, "google_trends"):
            store.enqueue_task(conn, kind="trend", priority="high", trend_keyword=term)
            inserted += 1

    for domain in config.load_domains():
        for kw in domain.get("keywords", []):
            if store.trend_seen_recently(conn, kw, hours=24):
                continue
            try:
                is_spike, ratio = gdelt_spike_score(kw)
            except Exception as exc:
                store.log(conn, None, "trend_scout", f"GDELT spike check failed for '{kw}': {exc}",
                           level="warn")
                continue
            if is_spike:
                store.record_trend(conn, kw, "gdelt_spike", score=ratio)
                store.enqueue_task(conn, kind="trend", domain_id=domain["id"],
                                    priority="high", trend_keyword=kw)
                inserted += 1

    store.log(conn, None, "trend_scout", f"scan complete, {inserted} trend task(s) enqueued")
    return inserted
