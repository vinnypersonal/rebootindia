import unittest

from src import worker


GOOD_DRAFT = {
    "problem": "Delayed highway project",
    "responsibleOffice": "",
    "solution": "Publish a public dashboard of milestone dates",
    "sourceUrl": "https://example.test/article",
    "ready": True,
    "readyReason": "",
    "header": {"domain": "Infrastructure", "level": "Central", "satire": False,
               "factAnchor": "", "imageUrl": ""},
    "twitter": {"text": "@TheDeshBhakt Highway project delayed 2 years. #RebootIndia",
                "charCount": 60, "hashtags": ["#RebootIndia"], "ready": True},
    "facebook": {"text": "Long form version.", "ready": True},
    "instagram": {"caption": "Short caption", "ready": False},
}


class ExtractJsonTests(unittest.TestCase):
    def test_extracts_between_markers(self):
        raw = "some preamble\n##REBOOT_START##\n{\"a\": 1}\n##REBOOT_END##\ntrailer"
        self.assertEqual(worker.extract_json(raw), {"a": 1})

    def test_raises_without_markers(self):
        with self.assertRaises(worker.WorkerError):
            worker.extract_json("no markers here")

    def test_raises_on_invalid_json(self):
        raw = "##REBOOT_START##not json##REBOOT_END##"
        with self.assertRaises(worker.WorkerError):
            worker.extract_json(raw)


class ValidateDraftTests(unittest.TestCase):
    def test_accepts_well_formed_draft(self):
        draft = worker.validate_draft(dict(GOOD_DRAFT))
        self.assertTrue(draft["ready"])

    def test_rejects_missing_keys(self):
        broken = {k: v for k, v in GOOD_DRAFT.items() if k != "twitter"}
        with self.assertRaises(worker.WorkerError):
            worker.validate_draft(broken)

    def test_rejects_satire_without_fact_anchor(self):
        draft = dict(GOOD_DRAFT)
        draft["header"] = dict(draft["header"], satire=True, factAnchor="")
        with self.assertRaises(worker.WorkerError):
            worker.validate_draft(draft)

    def test_rejects_oversized_tweet(self):
        draft = dict(GOOD_DRAFT)
        draft["twitter"] = dict(draft["twitter"], text="x" * 281)
        with self.assertRaises(worker.WorkerError):
            worker.validate_draft(draft)

    def test_forces_instagram_not_ready_without_image(self):
        draft = dict(GOOD_DRAFT)
        draft["instagram"] = dict(draft["instagram"], ready=True)
        draft["header"] = dict(draft["header"], imageUrl="")
        validated = worker.validate_draft(draft)
        self.assertFalse(validated["instagram"]["ready"])


if __name__ == "__main__":
    unittest.main()
