import os
import unittest
from unittest.mock import patch

from src import list_buffer_channels


class LooksLikeXTests(unittest.TestCase):
    def test_matches_twitter_and_x_case_insensitively(self):
        self.assertTrue(list_buffer_channels._looks_like_x("twitter"))
        self.assertTrue(list_buffer_channels._looks_like_x("Twitter"))
        self.assertTrue(list_buffer_channels._looks_like_x("x"))
        self.assertTrue(list_buffer_channels._looks_like_x("X"))

    def test_does_not_match_other_services(self):
        self.assertFalse(list_buffer_channels._looks_like_x("instagram"))
        self.assertFalse(list_buffer_channels._looks_like_x("facebook"))
        self.assertFalse(list_buffer_channels._looks_like_x(None))


class MainTests(unittest.TestCase):
    def test_exits_cleanly_when_not_configured(self):
        env = dict(os.environ)
        env.pop("BUFFER_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(list_buffer_channels.main(), 1)


if __name__ == "__main__":
    unittest.main()
