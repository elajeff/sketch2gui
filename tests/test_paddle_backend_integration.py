"""Offline integration tests for the optional PaddleOCR adapter."""
from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from sketch2gui.ocr.paddle_backend import PaddleOCRBackend


class PaddleBackendIntegrationTests(unittest.TestCase):
    def test_backend_loads_expected_model_and_passes_binary_preprocessed_image(self):
        observed = {}

        class FakeTextRecognition:
            def __init__(self, *, model_name):
                observed["model_name"] = model_name

            def predict(self, *, input, batch_size):
                observed["batch_size"] = batch_size
                with Image.open(input) as prepared:
                    observed["mode"] = prepared.mode
                    observed["colors"] = set(prepared.convert("RGB").tobytes())
                    observed["size"] = prepared.size
                return [{"res": {"rec_text": "Search", "rec_score": 0.82}}]

        fake_module = types.ModuleType("paddleocr")
        fake_module.TextRecognition = FakeTextRecognition
        sample = Image.new("RGB", (80, 40), "white")
        ImageDraw.Draw(sample).line((24, 20, 54, 20), fill=(30, 30, 30), width=2)

        with patch.dict(sys.modules, {"paddleocr": fake_module}):
            backend = PaddleOCRBackend(preprocess=True)
            result = backend.recognize(sample)

        self.assertEqual(observed["model_name"], "en_PP-OCRv5_mobile_rec")
        self.assertEqual(observed["batch_size"], 1)
        self.assertEqual(observed["mode"], "RGB")
        self.assertTrue(observed["size"][0] > 30)
        self.assertTrue(observed["colors"].issubset({0, 255}))
        self.assertEqual(result.text, "Search")
        self.assertAlmostEqual(result.confidence, 0.82)
        self.assertGreaterEqual(result.duration_ms, 0)


if __name__ == "__main__":
    unittest.main()
