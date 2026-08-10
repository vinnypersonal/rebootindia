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


if __name__ == "__main__":
    unittest.main()
