"""SQLite state store: tasks, logs, trends, posts, followups.

Zero-cost persistence — a single file committed back by the GitHub Action
(CLAUDE.md §4, §5). All writes are idempotent: a task claimed 'processing'
by one run is never picked up again, including across overlapping schedules.
"""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,               -- 'national' | 'city' | 'trend' | 'followup'
    domain_id TEXT,
    city TEXT,
    priority TEXT NOT NULL DEFAULT 'normal',  -- 'high' | 'normal' | 'low'
    status TEXT NOT NULL DEFAULT 'pending',   -- 'pending'|'processing'|'done'|'skipped'|'failed'
    source_url TEXT,
    article_json TEXT,
    trend_keyword TEXT,
    created_at REAL NOT NULL,
    claimed_at REAL,
    finished_at REAL,
    UNIQUE(source_url, kind)
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    ts REAL NOT NULL,
    stage TEXT NOT NULL,              -- 'trend_scout'|'news'|'worker'|'reviewer'|'poster'|'director'
    level TEXT NOT NULL DEFAULT 'info',
    llm_provider TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    source TEXT NOT NULL,             -- 'google_trends' | 'gdelt_spike'
    score REAL,
    detected_at REAL NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    UNIQUE(keyword, source, detected_at)
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    platform TEXT NOT NULL,           -- 'twitter'|'facebook'|'instagram'
    text TEXT,
    ready INTEGER NOT NULL DEFAULT 0,
    satire INTEGER NOT NULL DEFAULT 0,
    posted INTEGER NOT NULL DEFAULT 0,
    platform_post_id TEXT,
    skip_reason TEXT,
    created_at REAL NOT NULL,
    posted_at REAL
);

CREATE TABLE IF NOT EXISTS followups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_task_id INTEGER NOT NULL,
    due_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending'|'done'|'skipped'
    created_at REAL NOT NULL
);
"""


def _ensure_parent():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def connect(db_path: Path = None):
    _ensure_parent()
    conn = sqlite3.connect(str(db_path or config.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path = None):
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


def log(conn, task_id, stage, message, level="info", llm_provider=None):
    conn.execute(
        "INSERT INTO logs (task_id, ts, stage, level, llm_provider, message) VALUES (?,?,?,?,?,?)",
        (task_id, time.time(), stage, level, llm_provider, message),
    )


def enqueue_task(conn, kind, domain_id=None, city=None, priority="normal",
                  source_url=None, article=None, trend_keyword=None):
    """Insert a new task. Returns the row id, or None if it's a dedup no-op
    (same source_url+kind already queued/processed — idempotency, CLAUDE.md §10)."""
    try:
        cur = conn.execute(
            """INSERT INTO tasks (kind, domain_id, city, priority, source_url,
                                   article_json, trend_keyword, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (kind, domain_id, city, priority, source_url,
             json.dumps(article) if article else None, trend_keyword, time.time()),
        )
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None


def claim_next_tasks(conn, kind=None, limit=1):
    """Atomically claim up to `limit` pending tasks (highest priority first).
    Claimed tasks move to 'processing' so a concurrent/overlapping run can't
    double-pick them."""
    priority_order = "CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END"
    where = "status = 'pending'"
    params = []
    if kind:
        where += " AND kind = ?"
        params.append(kind)
    rows = conn.execute(
        f"SELECT * FROM tasks WHERE {where} ORDER BY {priority_order}, created_at ASC LIMIT ?",
        (*params, limit),
    ).fetchall()
    claimed = []
    for row in rows:
        cur = conn.execute(
            "UPDATE tasks SET status='processing', claimed_at=? WHERE id=? AND status='pending'",
            (time.time(), row["id"]),
        )
        if cur.rowcount == 1:
            claimed.append(dict(row))
    return claimed


def finish_task(conn, task_id, status="done"):
    conn.execute(
        "UPDATE tasks SET status=?, finished_at=? WHERE id=?",
        (status, time.time(), task_id),
    )


def record_trend(conn, keyword, source, score=None):
    try:
        conn.execute(
            "INSERT INTO trends (keyword, source, score, detected_at) VALUES (?,?,?,?)",
            (keyword, source, score, time.time()),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def trend_seen_recently(conn, keyword, hours=24):
    row = conn.execute(
        "SELECT 1 FROM trends WHERE keyword=? AND detected_at > ? LIMIT 1",
        (keyword, time.time() - hours * 3600),
    ).fetchone()
    return row is not None


def record_post(conn, task_id, platform, text, ready, satire=False, skip_reason=None):
    cur = conn.execute(
        """INSERT INTO posts (task_id, platform, text, ready, satire, skip_reason, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (task_id, platform, text, int(ready), int(satire), skip_reason, time.time()),
    )
    return cur.lastrowid


def mark_posted(conn, post_id, platform_post_id):
    conn.execute(
        "UPDATE posts SET posted=1, posted_at=?, platform_post_id=? WHERE id=?",
        (time.time(), platform_post_id, post_id),
    )


def schedule_followup(conn, task_id, due_in_days=7):
    conn.execute(
        "INSERT INTO followups (original_task_id, due_at, created_at) VALUES (?,?,?)",
        (task_id, time.time() + due_in_days * 86400, time.time()),
    )


def due_followups(conn):
    rows = conn.execute(
        "SELECT * FROM followups WHERE status='pending' AND due_at <= ?", (time.time(),)
    ).fetchall()
    return [dict(r) for r in rows]


def daily_post_count(conn, since_hours=24):
    row = conn.execute(
        "SELECT COUNT(*) c FROM posts WHERE posted=1 AND posted_at > ?",
        (time.time() - since_hours * 3600,),
    ).fetchone()
    return row["c"]


def daily_campaign_count(conn, since_hours=24):
    row = conn.execute(
        "SELECT COUNT(*) c FROM tasks WHERE status='done' AND finished_at > ?",
        (time.time() - since_hours * 3600,),
    ).fetchone()
    return row["c"]


def daily_satire_count(conn, since_hours=24):
    row = conn.execute(
        "SELECT COUNT(*) c FROM posts WHERE posted=1 AND satire=1 AND posted_at > ?",
        (time.time() - since_hours * 3600,),
    ).fetchone()
    return row["c"]
