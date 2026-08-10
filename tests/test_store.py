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


class EngagementAndWeightsTests(unittest.TestCase):
    def setUp(self):
        self.db_path = Path(f"/tmp/reboot_test_engagement_{time.time_ns()}.db")
        store.init_db(self.db_path)

    def tearDown(self):
        if self.db_path.exists():
            self.db_path.unlink()

    def _finished_task_with_post(self, conn, domain_id=None, city=None, url="https://x.test/p"):
        task_id = store.enqueue_task(conn, kind="national" if domain_id else "city",
                                      domain_id=domain_id, city=city, source_url=url)
        store.finish_task(conn, task_id, status="done")
        post_id = store.record_post(conn, task_id, "twitter", "text", ready=True)
        return task_id, post_id

    def test_domain_engagement_score_uses_latest_snapshot_only(self):
        with store.connect(self.db_path) as conn:
            _, post_id = self._finished_task_with_post(conn, domain_id="education")
            store.record_engagement(conn, post_id, "twitter", likes=1, shares=0, comments=0)
            store.record_engagement(conn, post_id, "twitter", likes=10, shares=2, comments=1)
            scores, counts = store.domain_engagement_scores(conn)
        self.assertEqual(scores["education"], 10 + 2 * 2 + 1)
        self.assertEqual(counts["education"], 1)

    def test_city_engagement_score(self):
        with store.connect(self.db_path) as conn:
            _, post_id = self._finished_task_with_post(conn, city="Pune, Maharashtra")
            store.record_engagement(conn, post_id, "twitter", likes=5, shares=1, comments=2)
            scores, counts = store.city_engagement_scores(conn)
        self.assertEqual(scores["Pune, Maharashtra"], 5 + 2 * 1 + 2)
        self.assertEqual(counts["Pune, Maharashtra"], 1)

    def test_domains_without_engagement_are_absent(self):
        with store.connect(self.db_path) as conn:
            self._finished_task_with_post(conn, domain_id="healthcare")
            # no engagement recorded
            scores, counts = store.domain_engagement_scores(conn)
        self.assertNotIn("healthcare", scores)

    def test_set_weight_roundtrip_and_update(self):
        with store.connect(self.db_path) as conn:
            store.set_weight(conn, "domain", "education", 1.5)
            weights = store.get_weights(conn, "domain")
            self.assertEqual(weights["education"], 1.5)

            store.set_weight(conn, "domain", "education", 0.8)
            weights = store.get_weights(conn, "domain")
        self.assertEqual(weights["education"], 0.8, "set_weight must update, not duplicate")

    def test_get_weights_scoped_by_scope(self):
        with store.connect(self.db_path) as conn:
            store.set_weight(conn, "domain", "education", 1.2)
            store.set_weight(conn, "city", "Pune, Maharashtra", 1.8)
            domain_weights = store.get_weights(conn, "domain")
            city_weights = store.get_weights(conn, "city")
        self.assertIn("education", domain_weights)
        self.assertNotIn("education", city_weights)
        self.assertIn("Pune, Maharashtra", city_weights)


if __name__ == "__main__":
    unittest.main()
