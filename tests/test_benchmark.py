import tempfile
import unittest
from pathlib import Path
from PIL import Image
from tools.ocr.benchmark_ocr import cer, edit_distance, discover_samples, normalized, raw_exact_match, normalized_exact_match


class BenchmarkHelpersTests(unittest.TestCase):
    def test_edit_distance(self):
        self.assertEqual(edit_distance("kitten", "sitting"), 3)
        self.assertEqual(edit_distance("Search", "Search"), 0)

    def test_cer_handles_exact_and_incorrect_text(self):
        self.assertEqual(cer("Login", "Login"), 0.0)
        self.assertGreater(cer("Login", "Logln"), 0)
        self.assertEqual(cer(" Search  Field ", "search field"), 0.0)

    def test_empty_reference(self):
        self.assertEqual(cer("", ""), 0.0)
        self.assertEqual(cer("", "abc"), 1.0)

    def test_discover_samples_requires_paired_text_truth(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            Image.new("RGB", (50, 20), "white").save(root / "one.png")
            (root / "one.txt").write_text("Search", encoding="utf-8")
            Image.new("RGB", (50, 20), "white").save(root / "unlabeled.png")
            self.assertEqual(len(discover_samples(root)), 1)
            self.assertEqual(discover_samples(root)[0][1], "Search")

    def test_normalized_exact_match_ignores_case_and_repeated_spaces(self):
        self.assertEqual(normalized(" SEARCH  FIELD "), normalized("search field"))

    def test_raw_exact_match_remains_distinct_from_normalized_match(self):
        truth = "Search  Field"
        prediction = "search field"
        self.assertFalse(raw_exact_match(truth, prediction))
        self.assertTrue(normalized_exact_match(truth, prediction))
