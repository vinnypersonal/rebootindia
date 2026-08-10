import os
import unittest
from unittest.mock import Mock, patch

from src import publish_website


SAMPLE_DRAFT = {
    "problem": "Delayed highway project",
    "responsibleOffice": "Ministry of Road Transport",
    "solution": "Publish a public dashboard of milestone dates",
    "sourceUrl": "https://example.test/article",
    "header": {"domain": "Infrastructure", "level": "Central", "satire": False,
               "factAnchor": "", "imageUrl": "https://example.test/img.jpg"},
    "twitter": {"text": "tweet text"},
    "facebook": {"text": "fb text"},
    "instagram": {"caption": "ig caption"},
}
SAMPLE_TASK = {"id": 42, "kind": "national", "city": None}


class BuildPayloadTests(unittest.TestCase):
    def test_shape_matches_contract(self):
        payload = publish_website.build_payload(SAMPLE_TASK, SAMPLE_DRAFT)
        self.assertEqual(payload["taskId"], 42)
        self.assertEqual(payload["kind"], "national")
        self.assertEqual(payload["domain"], "Infrastructure")
        self.assertEqual(payload["level"], "Central")
        self.assertIsNone(payload["city"])
        self.assertEqual(payload["problem"], "Delayed highway project")
        self.assertEqual(payload["posts"], {
            "twitter": "tweet text", "facebook": "fb text", "instagram": "ig caption",
        })
        self.assertIn("publishedAt", payload)

    def test_missing_optional_fields_become_none_not_missing_keys(self):
        draft = dict(SAMPLE_DRAFT)
        draft["header"] = dict(draft["header"], imageUrl="", factAnchor="")
        draft["facebook"] = {}
        payload = publish_website.build_payload(SAMPLE_TASK, draft)
        self.assertIsNone(payload["imageUrl"])
        self.assertIsNone(payload["factAnchor"])
        self.assertIsNone(payload["posts"]["facebook"])


class PublishTests(unittest.TestCase):
    def test_dry_run_makes_no_network_call(self):
        with patch("src.publish_website.requests.post") as mock_post:
            published, remote_id, detail = publish_website.publish({"problem": "x"}, dry_run=True)
        mock_post.assert_not_called()
        self.assertFalse(published)
        self.assertIsNone(remote_id)
        self.assertIn("dry-run", detail)

    def test_skips_gracefully_when_not_configured(self):
        env = dict(os.environ)
        env.pop("WEBSITE_PUBLISH_URL", None)
        with patch.dict(os.environ, env, clear=True), \
             patch("src.publish_website.requests.post") as mock_post:
            published, remote_id, detail = publish_website.publish({"problem": "x"}, dry_run=False)
        mock_post.assert_not_called()
        self.assertFalse(published)
        self.assertIn("not configured", detail)

    def test_success_parses_id_from_response(self):
        env = dict(os.environ, WEBSITE_PUBLISH_URL="https://site.test/api/campaigns")
        mock_resp = Mock(status_code=201)
        mock_resp.json.return_value = {"id": "abc123"}
        with patch.dict(os.environ, env, clear=True), \
             patch("src.publish_website.requests.post", return_value=mock_resp) as mock_post:
            published, remote_id, detail = publish_website.publish({"problem": "x"}, dry_run=False)
        mock_post.assert_called_once()
        self.assertTrue(published)
        self.assertEqual(remote_id, "abc123")

    def test_sends_bearer_header_when_api_key_set(self):
        env = dict(os.environ, WEBSITE_PUBLISH_URL="https://site.test/api/campaigns",
                    WEBSITE_PUBLISH_API_KEY="secret-key")
        mock_resp = Mock(status_code=200)
        mock_resp.json.return_value = {}
        with patch.dict(os.environ, env, clear=True), \
             patch("src.publish_website.requests.post", return_value=mock_resp) as mock_post:
            publish_website.publish({"problem": "x"}, dry_run=False)
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret-key")

    def test_error_status_reported_not_raised(self):
        env = dict(os.environ, WEBSITE_PUBLISH_URL="https://site.test/api/campaigns")
        mock_resp = Mock(status_code=500, text="server error")
        with patch.dict(os.environ, env, clear=True), \
             patch("src.publish_website.requests.post", return_value=mock_resp):
            published, remote_id, detail = publish_website.publish({"problem": "x"}, dry_run=False)
        self.assertFalse(published)
        self.assertIn("500", detail)


if __name__ == "__main__":
    unittest.main()
