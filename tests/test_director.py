import time
import unittest
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
