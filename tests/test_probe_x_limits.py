import unittest
from unittest.mock import patch

from src import probe_x_limits


class ExtractRateLimitHeadersTests(unittest.TestCase):
    def test_picks_out_limit_and_rate_headers_case_insensitively(self):
        headers = {
            "x-app-limit-24hour-limit": "17",
            "x-app-limit-24hour-remaining": "16",
            "X-Rate-Limit-Reset": "1234567890",
            "Content-Type": "application/json",
            "Server": "tsa_b",
        }
        result = probe_x_limits.extract_rate_limit_headers(headers)
        self.assertIn("x-app-limit-24hour-limit", result)
        self.assertIn("X-Rate-Limit-Reset", result)
        self.assertNotIn("Content-Type", result)
        self.assertNotIn("Server", result)

    def test_empty_headers_returns_empty(self):
        self.assertEqual(probe_x_limits.extract_rate_limit_headers({}), {})


class RunConfirmationGateTests(unittest.TestCase):
    def test_refuses_without_confirmation_and_makes_no_network_call(self):
        with patch("src.probe_x_limits.requests.post") as mock_post:
            exit_code = probe_x_limits.run(confirmed=False)
        mock_post.assert_not_called()
        self.assertEqual(exit_code, 1)

    def test_refuses_when_credentials_missing_even_if_confirmed(self):
        with patch("src.post_twitter._auth", side_effect=probe_x_limits.post_twitter.PosterNotConfigured("no creds")), \
             patch("src.probe_x_limits.requests.post") as mock_post:
            exit_code = probe_x_limits.run(confirmed=True)
        mock_post.assert_not_called()
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
