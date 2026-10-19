import unittest
from sketch2gui.ocr.paddle_backend import _find_text_and_score


class PaddleResultParserTests(unittest.TestCase):
    def test_parses_nested_single_line_result(self):
        self.assertEqual(_find_text_and_score({"res": {"rec_text": "Search", "rec_score": 0.87}}), ("Search", 0.87))

    def test_parses_plural_text_and_score_lists(self):
        text, score = _find_text_and_score({"rec_texts": ["Search", "Users"], "rec_scores": [0.9, 0.8]})
        self.assertEqual(text, "Search Users")
        self.assertAlmostEqual(score, 0.85)

    def test_invalid_score_is_treated_as_unavailable(self):
        self.assertEqual(_find_text_and_score({"rec_text": "Login", "rec_score": "not-a-number"}), ("Login", None))

    def test_plain_string_can_be_returned_when_not_json(self):
        self.assertEqual(_find_text_and_score("raw output"), ("raw output", None))

    def test_empty_structure_returns_empty_result(self):
        self.assertEqual(_find_text_and_score({"unexpected": []}), ("", None))
