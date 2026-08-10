import unittest
from unittest.mock import patch

from src import reviewer


BASE_DRAFT = {
    "problem": "Delayed highway project",
    "responsibleOffice": "",
    "solution": "Publish a public dashboard of milestone dates",
    "sourceUrl": "https://example.test/article",
    "header": {"domain": "Infrastructure", "level": "Central", "satire": False,
               "factAnchor": "", "imageUrl": ""},
    "twitter": {"text": "@TheDeshBhakt @narendramodi Highway delayed 2yr. #RebootIndia",
                "hashtags": ["#RebootIndia"]},
    "facebook": {"text": "Long form."},
    "instagram": {"caption": "Short caption", "ready": True},
}


class PassATests(unittest.TestCase):
    @patch("src.reviewer._url_resolves", return_value=True)
    def test_clean_draft_passes(self, _mock):
        issues = reviewer.pass_a(dict(BASE_DRAFT), level="Central", ministry_handle="")
        self.assertEqual(issues, [])

    @patch("src.reviewer._url_resolves", return_value=True)
    def test_flags_oversized_tweet(self, _mock):
        draft = dict(BASE_DRAFT)
        draft["twitter"] = dict(draft["twitter"], text="x" * 300)
        issues = reviewer.pass_a(draft, level="Central", ministry_handle="")
        self.assertTrue(any("chars" in i for i in issues))

    @patch("src.reviewer._url_resolves", return_value=True)
    def test_flags_missing_central_handle(self, _mock):
        draft = dict(BASE_DRAFT)
        draft["twitter"] = dict(draft["twitter"], text="@TheDeshBhakt only #RebootIndia")
        issues = reviewer.pass_a(draft, level="Central", ministry_handle="")
        self.assertTrue(any("narendramodi" in i for i in issues))

    @patch("src.reviewer._url_resolves", return_value=False)
    def test_flags_dead_source_url(self, _mock):
        issues = reviewer.pass_a(dict(BASE_DRAFT), level="Central", ministry_handle="")
        self.assertTrue(any("does not resolve" in i for i in issues))

    @patch("src.reviewer._url_resolves", return_value=True)
    def test_flags_banned_phrase(self, _mock):
        draft = dict(BASE_DRAFT)
        draft["twitter"] = dict(draft["twitter"], text="@TheDeshBhakt @narendramodi The minister is corrupt #RebootIndia")
        issues = reviewer.pass_a(draft, level="Central", ministry_handle="")
        self.assertTrue(any("banned absolute phrase" in i for i in issues))

    @patch("src.reviewer._url_resolves", return_value=True)
    def test_flags_satire_without_anchor(self, _mock):
        draft = dict(BASE_DRAFT)
        draft["header"] = dict(draft["header"], satire=True, factAnchor="")
        issues = reviewer.pass_a(draft, level="Central", ministry_handle="")
        self.assertTrue(any("factAnchor" in i for i in issues))

    @patch("src.reviewer._url_resolves", return_value=True)
    def test_forces_instagram_not_ready_without_image(self, _mock):
        draft = dict(BASE_DRAFT)
        draft["header"] = dict(draft["header"], imageUrl="")
        reviewer.pass_a(draft, level="Central", ministry_handle="")
        self.assertFalse(draft["instagram"]["ready"])


if __name__ == "__main__":
    unittest.main()
