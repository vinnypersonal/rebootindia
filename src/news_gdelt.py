"""News discovery: GDELT DOC API (primary) + Google News RSS (fallback).

Both are free, keyless, public APIs (CLAUDE.md §4). Returns a normalized
article dict: {title, url, snippet, image_url, source_domain, seen_at}.
"""
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote

import requests

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
REQUEST_TIMEOUT = 15


def _og_image(url):
    """Best-effort og:image scrape for articles GDELT didn't give us a socialimage for."""
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT,
                             headers={"User-Agent": "Mozilla/5.0 (RebootIndiaBot)"})
        match = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            resp.text, re.IGNORECASE,
        )
        return match.group(1) if match else None
    except Exception:
        return None


def fetch_gdelt(keyword, max_records=10, country="IN"):
    """Query GDELT DOC API for a keyword, restricted to India-sourced coverage."""
    query = f"{keyword} sourcecountry:{country}"
    params = {
        "query": query,
        "mode": "ArtList",
        "maxrecords": max_records,
        "format": "json",
        "sort": "DateDesc",
    }
    resp = requests.get(GDELT_DOC_URL, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        return []  # GDELT sometimes returns empty/non-JSON on no results

    articles = []
    for a in data.get("articles", []):
        articles.append({
            "title": a.get("title"),
            "url": a.get("url"),
            "snippet": a.get("title"),  # DOC API doesn't return body snippets, title is the anchor
            "image_url": a.get("socialimage") or None,
            "source_domain": a.get("domain"),
            "seen_at": a.get("seendate"),
        })
    return articles


def fetch_google_news_rss(keyword, country="IN", lang="en", max_records=10):
    """Fallback when GDELT returns nothing usable. The feed itself returns as
    many as Google wants (often 100); truncate to max_records so callers get
    the same bounded shape as fetch_gdelt()."""
    q = quote(keyword)
    url = f"{GOOGLE_NEWS_RSS}?q={q}&hl={lang}-{country}&gl={country}&ceid={country}:{lang}"
    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)

    articles = []
    for item in root.findall(".//item")[:max_records]:
        title = item.findtext("title")
        link = item.findtext("link")
        pub_date = item.findtext("pubDate")
        source_el = item.find("source")
        source = source_el.text if source_el is not None else None
        articles.append({
            "title": title,
            "url": link,
            "snippet": title,
            "image_url": None,  # RSS has no image; caller can og:image-scrape if needed
            "source_domain": source,
            "seen_at": pub_date,
        })
    return articles


def discover(keyword, max_records=10, fill_missing_images=True):
    """Primary GDELT, fallback to Google News RSS on empty/error.
    Optionally backfills missing images via og:image (bounded — only for the
    top article, to keep this cheap)."""
    articles = []
    try:
        articles = fetch_gdelt(keyword, max_records=max_records)
    except Exception:
        articles = []

    if not articles:
        try:
            articles = fetch_google_news_rss(keyword, max_records=max_records)
        except Exception:
            articles = []

    if fill_missing_images and articles and not articles[0].get("image_url"):
        articles[0]["image_url"] = _og_image(articles[0]["url"]) if articles[0].get("url") else None

    return articles


def discover_for_domain(domain, max_records=5):
    """Run discover() across all keywords configured for a national domain
    (data/domains.yaml), returning the freshest deduped article list."""
    seen_urls = set()
    combined = []
    for kw in domain.get("keywords", []):
        for article in discover(kw, max_records=max_records):
            if article["url"] and article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                combined.append(article)
    return combined


def discover_for_city(city_name, state, max_records=5):
    keyword = f"{city_name} {state}"
    return discover(keyword, max_records=max_records)
