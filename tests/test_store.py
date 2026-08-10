import time
import unittest
from pathlib import Path

from src import store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.db_path = Path(f"/tmp/reboot_test_{time.time_ns()}.db")
        store.init_db(self.db_path)

    def tearDown(self):
        if self.db_path.exists():
            self.db_path.unlink()

    def test_enqueue_and_claim_idempotent(self):
        with store.connect(self.db_path) as conn:
            first = store.enqueue_task(conn, kind="national", source_url="https://x.test/a")
            second = store.enqueue_task(conn, kind="national", source_url="https://x.test/a")
            self.assertIsNotNone(first)
            self.assertIsNone(second, "duplicate source_url+kind must be a dedup no-op")

    def test_claim_marks_processing_and_is_not_reclaimed(self):
        with store.connect(self.db_path) as conn:
            store.enqueue_task(conn, kind="city", source_url="https://x.test/b")
            claimed_first = store.claim_next_tasks(conn, limit=5)
            claimed_second = store.claim_next_tasks(conn, limit=5)
        self.assertEqual(len(claimed_first), 1)
        self.assertEqual(len(claimed_second), 0, "a claimed task must not be claimable again")

    def test_priority_ordering(self):
        with store.connect(self.db_path) as conn:
            store.enqueue_task(conn, kind="city", priority="low", source_url="https://x.test/low")
            store.enqueue_task(conn, kind="national", priority="high", source_url="https://x.test/high")
            claimed = store.claim_next_tasks(conn, limit=1)
        self.assertEqual(claimed[0]["priority"], "high")

    def test_trend_dedup_window(self):
        with store.connect(self.db_path) as conn:
            first = store.record_trend(conn, "budget 2026", "google_trends")
            seen = store.trend_seen_recently(conn, "budget 2026", hours=24)
            self.assertTrue(first)
            self.assertTrue(seen)


if __name__ == "__main__":
    unittest.main()
