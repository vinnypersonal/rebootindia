import time
import unittest
from pathlib import Path
from unittest.mock import patch

from src import config, growth, store


class ScoresToWeightsTests(unittest.TestCase):
    def test_below_min_sample_size_excluded(self):
        scores = {"a": 100, "b": 10}
        counts = {"a": 1, "b": 1}  # below GROWTH_MIN_SAMPLE_SIZE (3)
        self.assertEqual(growth._scores_to_weights(scores, counts), {})

    def test_above_average_scores_above_one(self):
        scores = {"a": 100, "b": 10}
        counts = {"a": 5, "b": 5}
        weights = growth._scores_to_weights(scores, counts)
        self.assertGreater(weights["a"], 1.0)
        self.assertLess(weights["b"], 1.0)

    def test_clamped_to_configured_bounds(self):
        scores = {"a": 100000, "b": 1}
        counts = {"a": 5, "b": 5}
        weights = growth._scores_to_weights(scores, counts)
        self.assertLessEqual(weights["a"], config.GROWTH_WEIGHT_MAX)
        self.assertGreaterEqual(weights["b"], config.GROWTH_WEIGHT_MIN)

    def test_zero_average_returns_empty(self):
        scores = {"a": 0, "b": 0}
        counts = {"a": 5, "b": 5}
        self.assertEqual(growth._scores_to_weights(scores, counts), {})


class CollectEngagementTests(unittest.TestCase):
    def setUp(self):
        self.db_path = Path(f"/tmp/reboot_test_growth_{time.time_ns()}.db")
        store.init_db(self.db_path)

    def tearDown(self):
        if self.db_path.exists():
            self.db_path.unlink()

    def test_records_metrics_for_fetchable_posts_and_skips_none(self):
        with store.connect(self.db_path) as conn:
            task_id = store.enqueue_task(conn, kind="national", domain_id="education",
                                          source_url="https://x.test/a")
            store.finish_task(conn, task_id, status="done")
            good_post = store.record_post(conn, task_id, "twitter", "text", ready=True)
            store.mark_posted(conn, good_post, "tw123")

            bad_post = store.record_post(conn, task_id, "facebook", "text", ready=True)
            store.mark_posted(conn, bad_post, "fb123")

            with patch("src.post_twitter.fetch_metrics", return_value={"likes": 5, "shares": 1, "comments": 2}), \
                 patch("src.post_facebook.fetch_metrics", return_value=None):
                fetched = growth.collect_engagement(conn)

            scores, counts = store.domain_engagement_scores(conn)

        self.assertEqual(fetched, 1, "only the twitter post returned metrics")
        self.assertEqual(scores["education"], 5 + 2 * 1 + 2)

    def test_compute_weights_end_to_end_below_threshold_stays_unweighted(self):
        with store.connect(self.db_path) as conn:
            task_id = store.enqueue_task(conn, kind="national", domain_id="farmers",
                                          source_url="https://x.test/b")
            store.finish_task(conn, task_id, status="done")
            post_id = store.record_post(conn, task_id, "twitter", "text", ready=True)
            store.mark_posted(conn, post_id, "tw999")
            store.record_engagement(conn, post_id, "twitter", likes=50, shares=10, comments=5)

            domain_weights, city_weights = growth.compute_weights(conn)
            persisted = store.get_weights(conn, "domain")

        # only 1 sample, below GROWTH_MIN_SAMPLE_SIZE -> no weight written
        self.assertNotIn("farmers", domain_weights)
        self.assertNotIn("farmers", persisted)


if __name__ == "__main__":
    unittest.main()
