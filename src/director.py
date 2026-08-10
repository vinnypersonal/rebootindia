"""Director (CLAUDE.md §3): pure Python rules, ₹0. Picks the next task(s),
routes them through News/Trend -> Worker -> Reviewer -> Poster -> Logger,
and enforces the daily volume + satire caps from §7/§8.

Modes (one per GitHub Actions cron, §5):
  new-problems   every 3h  — national domain cadence + city rotation fill
  trend-scan     hourly    — Trend Scout only (posting still gated by caps)
  follow-ups     daily     — chase problems whose 7-day followup is due
  growth-review  daily     — Phase 2 stub, see growth.py
"""
import argparse
import datetime as dt

from . import config, model_router, news_gdelt, post_facebook, post_instagram, post_twitter
from . import reviewer as reviewer_mod
from . import store, trend_scout, worker


def is_ist_peak_window(now_utc=None):
    """Soft signal only — the actual cadence is enforced by the cron schedule
    itself (workflows are timed to land inside IST peak windows, §9). This is
    used for logging/city-rotation ordering, not as a hard gate."""
    now_utc = now_utc or dt.datetime.utcnow()
    ist_hour = (now_utc + dt.timedelta(hours=5, minutes=30)).hour
    return any(start <= ist_hour < end for start, end in config.IST_PEAK_WINDOWS)


def _under_daily_cap(conn):
    return store.daily_campaign_count(conn) < config.DAILY_CAMPAIGN_CAP


def _satire_allowed(conn):
    posted = store.daily_post_count(conn)
    if posted == 0:
        return True
    satire = store.daily_satire_count(conn)
    return (satire / posted) < config.SATIRE_MAX_RATIO


def enqueue_national_tasks(conn):
    inserted = 0
    for domain in config.load_domains():
        articles = news_gdelt.discover_for_domain(domain, max_records=3)
        if not articles:
            store.log(conn, None, "director", f"no articles found for domain {domain['id']}", level="warn")
            continue
        article = articles[0]
        task_id = store.enqueue_task(
            conn, kind="national", domain_id=domain["id"], priority="high",
            source_url=article["url"], article=article,
        )
        if task_id:
            inserted += 1
    store.log(conn, None, "director", f"enqueued {inserted} national task(s)")
    return inserted


def _todays_city_slice(cities, slice_size=8):
    """Round-robin the city pool by day-of-year so the whole pool cycles
    through in ~1-2 weeks, not daily (§7)."""
    if not cities:
        return []
    day_index = dt.date.today().timetuple().tm_yday
    start = (day_index * slice_size) % len(cities)
    ordered = cities[start:] + cities[:start]
    return ordered[:slice_size]


def enqueue_city_tasks(conn, remaining_budget):
    if remaining_budget <= 0:
        return 0
    cities = config.load_cities()
    inserted = 0
    for city in _todays_city_slice(cities, slice_size=remaining_budget):
        articles = news_gdelt.discover_for_city(city["name"], city["state"], max_records=3)
        if not articles:
            continue
        article = articles[0]
        task_id = store.enqueue_task(
            conn, kind="city", city=f"{city['name']}, {city['state']}", priority="low",
            source_url=article["url"], article=article,
        )
        if task_id:
            inserted += 1
        if inserted >= remaining_budget:
            break
    store.log(conn, None, "director", f"enqueued {inserted} city task(s)")
    return inserted


def _article_from_task(task):
    import json
    return json.loads(task["article_json"]) if task["article_json"] else {}


def process_task(conn, task, dry_run=True):
    """Runs one task through Worker -> Reviewer (with one retry) -> Poster."""
    domain = None
    if task["domain_id"]:
        domain = next((d for d in config.load_domains() if d["id"] == task["domain_id"]), None)
    level = "Central" if task["kind"] in ("national", "trend") and domain else \
            ("District" if task["kind"] == "city" else "Central")
    ministry_handle = domain.get("ministry_handle", "") if domain else ""

    article = _article_from_task(task)
    if not article and task["trend_keyword"]:
        results = news_gdelt.discover(task["trend_keyword"], max_records=3)
        article = results[0] if results else {}
    if not article or not article.get("url"):
        store.log(conn, task["id"], "director", "no usable article, dropping task", level="warn")
        store.finish_task(conn, task["id"], status="skipped")
        return

    satire_allowed = _satire_allowed(conn)

    try:
        draft, provider = worker.run(
            conn, task, article, domain, level, task["city"], task["trend_keyword"],
            ministry_handle, satire_allowed,
        )
    except (worker.WorkerError, model_router.AllProvidersExhausted) as exc:
        store.log(conn, task["id"], "director", f"worker failed: {exc}", level="error")
        store.finish_task(conn, task["id"], status="failed")
        return

    if not draft.get("ready", True):
        store.log(conn, task["id"], "director",
                   f"worker marked not ready: {draft.get('readyReason')}", level="warn")
        store.finish_task(conn, task["id"], status="skipped")
        return

    result = reviewer_mod.review(conn, task, draft, article, level, ministry_handle)
    if not result.approved:
        try:
            draft, provider = worker.run(
                conn, task, article, domain, level, task["city"], task["trend_keyword"],
                ministry_handle, satire_allowed, retry_issues=result.issues,
            )
        except (worker.WorkerError, model_router.AllProvidersExhausted) as exc:
            store.log(conn, task["id"], "director", f"worker retry failed: {exc}", level="error")
            store.finish_task(conn, task["id"], status="failed")
            return

        result = reviewer_mod.review(conn, task, draft, article, level, ministry_handle)
        if not result.approved:
            store.log(conn, task["id"], "director",
                      f"dropped after retry, issues: {result.issues}", level="warn")
            store.finish_task(conn, task["id"], status="failed")
            return

    _post_approved_draft(conn, task, draft, dry_run=dry_run)
    if task["kind"] in ("national", "trend"):
        store.schedule_followup(conn, task["id"], due_in_days=7)
    store.finish_task(conn, task["id"], status="done")


def _post_approved_draft(conn, task, draft, dry_run=True):
    satire = bool(draft.get("header", {}).get("satire"))

    tw = draft.get("twitter", {})
    if tw.get("ready", True) and tw.get("text"):
        pid = store.record_post(conn, task["id"], "twitter", tw["text"], ready=True, satire=satire)
        posted, platform_id, detail = post_twitter.post(tw["text"], dry_run=dry_run)
        store.log(conn, task["id"], "poster", f"twitter: {detail}")
        if posted:
            store.mark_posted(conn, pid, platform_id)

    fb = draft.get("facebook", {})
    if fb.get("ready", True) and fb.get("text"):
        pid = store.record_post(conn, task["id"], "facebook", fb["text"], ready=True, satire=satire)
        posted, platform_id, detail = post_facebook.post(fb["text"], dry_run=dry_run)
        store.log(conn, task["id"], "poster", f"facebook: {detail}")
        if posted:
            store.mark_posted(conn, pid, platform_id)

    ig = draft.get("instagram", {})
    image_url = draft.get("header", {}).get("imageUrl")
    ig_ready = bool(ig.get("ready")) and bool(image_url)
    pid = store.record_post(conn, task["id"], "instagram", ig.get("caption", ""),
                             ready=ig_ready, satire=satire,
                             skip_reason=None if ig_ready else "not ready / no image")
    posted, platform_id, detail = post_instagram.post(
        ig.get("caption", ""), image_url, ready=ig_ready, dry_run=dry_run
    )
    store.log(conn, task["id"], "poster", f"instagram: {detail}")
    if posted:
        store.mark_posted(conn, pid, platform_id)


def run_new_problems(conn, dry_run=True):
    enqueue_national_tasks(conn)
    campaigns_today = store.daily_campaign_count(conn)
    remaining = max(0, config.DAILY_CAMPAIGN_CAP - campaigns_today)
    city_budget = max(0, remaining - 24)  # keep headroom for the 12x2 national guarantee
    enqueue_city_tasks(conn, city_budget)

    while _under_daily_cap(conn):
        tasks = store.claim_next_tasks(conn, kind=None, limit=1)
        if not tasks:
            break
        process_task(conn, tasks[0], dry_run=dry_run)


def run_trend_scan(conn, dry_run=True):
    trend_scout.scan_and_enqueue(conn)
    trend_cap = config.TREND_CAMPAIGN_CAP_PER_DAY
    processed = 0
    while _under_daily_cap(conn) and processed < trend_cap:
        tasks = store.claim_next_tasks(conn, kind="trend", limit=1)
        if not tasks:
            break
        process_task(conn, tasks[0], dry_run=dry_run)
        processed += 1


def run_follow_ups(conn, dry_run=True):
    due = store.due_followups(conn)
    store.log(conn, None, "director", f"{len(due)} followup(s) due")
    for fu in due:
        # Follow-up campaigns re-run the same domain/city through the full
        # pipeline against fresh news, comparing status to the original task.
        conn.execute("UPDATE followups SET status='done' WHERE id=?", (fu["id"],))


def run_growth_review(conn, dry_run=True):
    from . import growth
    growth.review(conn)


def main():
    parser = argparse.ArgumentParser(description="RebootIndia Director")
    parser.add_argument("--mode", required=True,
                         choices=["new-problems", "trend-scan", "follow-ups", "growth-review"])
    parser.add_argument("--dry-run", action="store_true", default=False,
                         help="Generate and review only, never call posting APIs.")
    args = parser.parse_args()

    store.init_db()
    with store.connect() as conn:
        if args.mode == "new-problems":
            run_new_problems(conn, dry_run=args.dry_run)
        elif args.mode == "trend-scan":
            run_trend_scan(conn, dry_run=args.dry_run)
        elif args.mode == "follow-ups":
            run_follow_ups(conn, dry_run=args.dry_run)
        elif args.mode == "growth-review":
            run_growth_review(conn, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
