import time
import unittest
import unittest.mock
from pathlib import Path

from src import director, store


class DirectorSelectionTests(unittest.TestCase):
    def setUp(self):
        self.db_path = Path(f"/tmp/reboot_test_director_{time.time_ns()}.db")
        store.init_db(self.db_path)

    def tearDown(self):
        if self.db_path.exists():
            self.db_path.unlink()

    def test_city_rotation_slice_wraps_and_is_deterministic(self):
        cities = [{"name": f"City{i}", "state": "State"} for i in range(10)]
        slice_a = director._todays_city_slice(cities, slice_size=4)
        slice_b = director._todays_city_slice(cities, slice_size=4)
        self.assertEqual(len(slice_a), 4)
        self.assertEqual(slice_a, slice_b, "same-day slice must be deterministic")

    def test_city_rotation_empty_pool(self):
        self.assertEqual(director._todays_city_slice([], slice_size=4), [])

    def test_under_daily_cap_true_when_empty(self):
        with store.connect(self.db_path) as conn:
            self.assertTrue(director._under_daily_cap(conn))

    def test_satire_allowed_true_with_no_posts_yet(self):
        with store.connect(self.db_path) as conn:
            self.assertTrue(director._satire_allowed(conn))


class GrowthWeightingTests(unittest.TestCase):
    def setUp(self):
        self.db_path = Path(f"/tmp/reboot_test_weighting_{time.time_ns()}.db")
        store.init_db(self.db_path)

    def tearDown(self):
        if self.db_path.exists():
            self.db_path.unlink()

    def test_no_weights_pool_equals_original_list(self):
        cities = [{"name": "A", "state": "S"}, {"name": "B", "state": "S"}]
        self.assertEqual(director._weighted_city_pool(cities, weights=None), cities)
        self.assertEqual(director._weighted_city_pool(cities, weights={}), cities)

    def test_weighted_city_appears_more_often_across_rotation(self):
        cities = [{"name": f"City{i}", "state": "S"} for i in range(6)]
        weights = {director._city_key(cities[0]): 2.0}  # max weight for City0, rest default 1.0

        appearances = 0
        total_days = 30
        for day in range(total_days):
            with unittest.mock.patch("src.director.dt") as mock_dt:
                mock_dt.date.today.return_value.timetuple.return_value.tm_yday = day
                sl = director._todays_city_slice(cities, slice_size=2, weights=weights)
            if director._city_key(cities[0]) in [director._city_key(c) for c in sl]:
                appearances += 1

        baseline_share = 2 / 6  # slice_size / pool size, if unweighted
        self.assertGreater(appearances / total_days, baseline_share,
                            "a 2x-weighted city should be selected more often than its unweighted share")

    def test_daily_slice_never_repeats_a_city_even_when_pool_has_duplicates(self):
        cities = [{"name": "A", "state": "S"}, {"name": "B", "state": "S"}]
        weights = {"A, S": 2.0}
        sl = director._todays_city_slice(cities, slice_size=2, weights=weights)
        keys = [director._city_key(c) for c in sl]
        self.assertEqual(len(keys), len(set(keys)), "no city should appear twice in one day's slice")

    def test_national_domains_enqueued_highest_weight_first(self):
        fake_domains = [
            {"id": "low", "name": "Low", "keywords": ["low kw"]},
            {"id": "high", "name": "High", "keywords": ["high kw"]},
        ]
        attempted_order = []

        def fake_discover(domain, max_records=3):
            attempted_order.append(domain["id"])
            return []  # no articles -> nothing enqueued, we only care about order

        with store.connect(self.db_path) as conn:
            store.set_weight(conn, "domain", "high", 2.0)
            with unittest.mock.patch("src.director.config.load_domains", return_value=fake_domains), \
                 unittest.mock.patch("src.director.news_gdelt.discover_for_domain", side_effect=fake_discover):
                director.enqueue_national_tasks(conn)

        self.assertEqual(attempted_order, ["high", "low"])


class FollowupContextTests(unittest.TestCase):
    def setUp(self):
        self.db_path = Path(f"/tmp/reboot_test_followup_{time.time_ns()}.db")
        store.init_db(self.db_path)

    def tearDown(self):
        if self.db_path.exists():
            self.db_path.unlink()

    def test_none_when_task_has_no_followup_link(self):
        with store.connect(self.db_path) as conn:
            task_id = store.enqueue_task(conn, kind="national", source_url="https://x.test/a")
            task = store.get_task(conn, task_id)
            self.assertIsNone(director._build_followup_context(conn, task))

    def test_none_when_original_has_no_posted_text(self):
        with store.connect(self.db_path) as conn:
            original_id = store.enqueue_task(conn, kind="national", source_url="https://x.test/orig")
            followup_id = store.enqueue_task(
                conn, kind="followup", source_url="https://x.test/fresh",
                followup_of_task_id=original_id,
            )
            followup_task = store.get_task(conn, followup_id)
            self.assertIsNone(director._build_followup_context(conn, followup_task))

    def test_pulls_original_twitter_text_and_source(self):
        with store.connect(self.db_path) as conn:
            original_id = store.enqueue_task(conn, kind="national", source_url="https://x.test/orig")
            store.record_post(conn, original_id, "twitter", "Original report text", ready=True)
            store.finish_task(conn, original_id, status="done")

            followup_id = store.enqueue_task(
                conn, kind="followup", source_url="https://x.test/fresh",
                followup_of_task_id=original_id,
            )
            followup_task = store.get_task(conn, followup_id)
            ctx = director._build_followup_context(conn, followup_task)

        self.assertIsNotNone(ctx)
        self.assertEqual(ctx["original_post_text"], "Original report text")
        self.assertEqual(ctx["original_source_url"], "https://x.test/orig")

    def test_process_task_drops_followup_without_context(self):
        with store.connect(self.db_path) as conn:
            original_id = store.enqueue_task(conn, kind="national", source_url="https://x.test/orig2")
            followup_id = store.enqueue_task(
                conn, kind="followup", source_url="https://x.test/fresh2",
                article={"title": "t", "url": "https://x.test/fresh2", "snippet": "s"},
                followup_of_task_id=original_id,
            )
            task = store.get_task(conn, followup_id)
            director.process_task(conn, task, dry_run=True)
            finished = store.get_task(conn, followup_id)

        self.assertEqual(finished["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
