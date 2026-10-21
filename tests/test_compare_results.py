import unittest
from tools.ocr.compare_ocr_results import sample_truths


class CompareReportsTests(unittest.TestCase):
    def test_sample_truths_extracts_labeled_sample_set(self):
        data = {"engines": {"paddle": {"samples": [
            {"image": "a.png", "truth": "Search"},
            {"image": "b.png", "truth": "Login"},
        ]}}}
        self.assertEqual(sample_truths(data), {"a.png": "Search", "b.png": "Login"})

    def test_sample_truths_empty_for_report_without_results(self):
        self.assertEqual(sample_truths({"engines": {"trocr": {"error": "no model"}}}), {})
