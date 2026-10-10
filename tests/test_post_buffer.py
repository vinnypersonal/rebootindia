import os
import unittest
from unittest.mock import Mock, patch

from src import post_buffer


class PostTests(unittest.TestCase):
    def test_dry_run_makes_no_network_call(self):
        with patch("src.post_buffer.requests.post") as mock_post:
            posted, post_id, detail = post_buffer.post("hello", dry_run=True)
        mock_post.assert_not_called()
        self.assertFalse(posted)
        self.assertIsNone(post_id)
        self.assertIn("dry-run", detail)

    def test_skips_gracefully_when_channel_id_missing(self):
        env = dict(os.environ, BUFFER_API_KEY="k")
        env.pop("BUFFER_X_CHANNEL_ID", None)
        with patch.dict(os.environ, env, clear=True), \
             patch("src.post_buffer.requests.post") as mock_post:
            posted, post_id, detail = post_buffer.post("hello", dry_run=False)
        mock_post.assert_not_called()
        self.assertFalse(posted)
        self.assertIn("BUFFER_X_CHANNEL_ID", detail)

    def test_skips_gracefully_when_api_key_missing(self):
        env = dict(os.environ, BUFFER_X_CHANNEL_ID="chan123")
        env.pop("BUFFER_API_KEY", None)
        with patch.dict(os.environ, env, clear=True), \
             patch("src.post_buffer.requests.post") as mock_post:
            posted, post_id, detail = post_buffer.post("hello", dry_run=False)
        mock_post.assert_not_called()
        self.assertFalse(posted)
        self.assertIn("BUFFER_API_KEY", detail)

    def test_success_parses_post_id(self):
        env = dict(os.environ, BUFFER_API_KEY="k", BUFFER_X_CHANNEL_ID="chan123")
        mock_resp = Mock(status_code=200)
        mock_resp.json.return_value = {
            "data": {"createPost": {"post": {"id": "post_abc", "text": "hello", "dueAt": "2026-01-01T00:00:10.000Z"}}}
        }
        with patch.dict(os.environ, env, clear=True), \
             patch("src.post_buffer.requests.post", return_value=mock_resp) as mock_post:
            posted, post_id, detail = post_buffer.post("hello", dry_run=False)
        mock_post.assert_called_once()
        self.assertTrue(posted)
        self.assertEqual(post_id, "post_abc")

    def test_mutation_error_is_not_posted(self):
        env = dict(os.environ, BUFFER_API_KEY="k", BUFFER_X_CHANNEL_ID="chan123")
        mock_resp = Mock(status_code=200)
        mock_resp.json.return_value = {"data": {"createPost": {"message": "Text is required"}}}
        with patch.dict(os.environ, env, clear=True), \
             patch("src.post_buffer.requests.post", return_value=mock_resp):
            posted, post_id, detail = post_buffer.post("hello", dry_run=False)
        self.assertFalse(posted)
        self.assertIn("Text is required", detail)

    def test_top_level_graphql_error_is_not_posted(self):
        env = dict(os.environ, BUFFER_API_KEY="k", BUFFER_X_CHANNEL_ID="chan123")
        mock_resp = Mock(status_code=200)
        mock_resp.json.return_value = {
            "data": None,
            "errors": [{"message": "Not authorized", "extensions": {"code": "UNAUTHORIZED"}}],
        }
        with patch.dict(os.environ, env, clear=True), \
             patch("src.post_buffer.requests.post", return_value=mock_resp):
            posted, post_id, detail = post_buffer.post("hello", dry_run=False)
        self.assertFalse(posted)
        self.assertIn("Not authorized", detail)

    def test_due_at_is_a_few_seconds_in_the_future(self):
        env = dict(os.environ, BUFFER_API_KEY="k", BUFFER_X_CHANNEL_ID="chan123")
        mock_resp = Mock(status_code=200)
        mock_resp.json.return_value = {"data": {"createPost": {"post": {"id": "x", "dueAt": "irrelevant"}}}}
        with patch.dict(os.environ, env, clear=True), \
             patch("src.post_buffer.requests.post", return_value=mock_resp) as mock_post:
            post_buffer.post("hello", dry_run=False)
        _, kwargs = mock_post.call_args
        due_at = kwargs["json"]["variables"]["dueAt"]
        self.assertTrue(due_at.endswith("Z"))


class FetchMetricsTests(unittest.TestCase):
    def test_returns_none_when_not_configured(self):
        env = dict(os.environ)
        env.pop("BUFFER_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            self.assertIsNone(post_buffer.fetch_metrics("post_abc"))

    def test_maps_normalized_metric_types(self):
        env = dict(os.environ, BUFFER_API_KEY="k")
        mock_resp = Mock(status_code=200)
        mock_resp.json.return_value = {
            "data": {
                "post": {
                    "id": "post_abc",
                    "metrics": [
                        {"type": "reactions", "name": "Likes", "value": 12.0, "unit": "count"},
                        {"type": "reposts", "name": "Reposts", "value": 3.0, "unit": "count"},
                        {"type": "comments", "name": "Replies", "value": 1.0, "unit": "count"},
                        {"type": "impressions", "name": "Impressions", "value": 500.0, "unit": "count"},
                    ],
                }
            }
        }
        with patch.dict(os.environ, env, clear=True), \
             patch("src.post_buffer.requests.post", return_value=mock_resp):
            metrics = post_buffer.fetch_metrics("post_abc")
        self.assertEqual(metrics, {"likes": 12, "shares": 3, "comments": 1})

    def test_missing_metrics_default_to_zero_not_none(self):
        env = dict(os.environ, BUFFER_API_KEY="k")
        mock_resp = Mock(status_code=200)
        mock_resp.json.return_value = {"data": {"post": {"id": "post_abc", "metrics": []}}}
        with patch.dict(os.environ, env, clear=True), \
             patch("src.post_buffer.requests.post", return_value=mock_resp):
            metrics = post_buffer.fetch_metrics("post_abc")
        self.assertEqual(metrics, {"likes": 0, "shares": 0, "comments": 0})

    def test_graphql_errors_return_none(self):
        env = dict(os.environ, BUFFER_API_KEY="k")
        mock_resp = Mock(status_code=200)
        mock_resp.json.return_value = {"data": None, "errors": [{"message": "Not found"}]}
        with patch.dict(os.environ, env, clear=True), \
             patch("src.post_buffer.requests.post", return_value=mock_resp):
            self.assertIsNone(post_buffer.fetch_metrics("post_abc"))


if __name__ == "__main__":
    unittest.main()
