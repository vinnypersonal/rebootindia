"""Growth Tracker — Phase 2 (CLAUDE.md §3, §9, §11 T13). NOT active in v2 launch.

Intent once built: read back likes/shares/comments via the free X/Graph read
endpoints and nudge future domain/city selection (director.enqueue_*) toward
what resonates. Needs the free-tier *read* metrics availability confirmed
first (§9) — don't assume it's unlimited just because posting is free.

Left as a stub so director.py's growth-review cron has something to call
without crashing; it intentionally does not change any scheduling weights yet.
"""
from . import store


def review(conn):
    store.log(conn, None, "growth",
              "growth-review stub: engagement read-back not yet implemented (Phase 2)")
