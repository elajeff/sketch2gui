import sys
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from sketch2gui.ocr import load_backend
from sketch2gui.ocr.paddle_backend import _find_text_and_score, preprocess_for_paddle


class OptionalOCRBackendTests(unittest.TestCase):
    def test_missing_paddle_package_has_install_guidance(self):
        with patch.dict(sys.modules, {"paddleocr": None}):
            with self.assertRaisesRegex(RuntimeError, "PaddleOCR is not installed"):
                load_backend("paddle")

    def test_unknown_engine_is_reported_without_loading_a_model(self):
        with self.assertRaisesRegex(ValueError, "Unknown OCR backend"):
            load_backend("not-an-engine")


    def test_nested_paddle_result_is_parsed(self):
        text, score = _find_text_and_score({"result": {"rec_text": "Search", "rec_score": 0.84}})
        self.assertEqual(text, "Search")
        self.assertAlmostEqual(score, 0.84)

    def test_paddle_preprocessing_crops_and_binarizes_ink(self):
        image = Image.new("RGB", (100, 50), "white")
        ImageDraw.Draw(image).rectangle((40, 15, 50, 25), fill="black")

        prepared = preprocess_for_paddle(image)

        self.assertEqual(prepared.mode, "RGB")
        self.assertLess(prepared.width, image.width)
        self.assertLess(prepared.height, image.height)
        channel_extrema = (channel.getextrema() for channel in prepared.split())
        self.assertTrue(all(extrema == (0, 255) for extrema in channel_extrema))


if __name__ == "__main__":
    unittest.main()
