import sys
import unittest
from unittest.mock import patch

from sketch2gui.ocr import load_backend


class OptionalOCRBackendTests(unittest.TestCase):
    def test_missing_paddle_package_has_install_guidance(self):
        with patch.dict(sys.modules, {"paddleocr": None}):
            with self.assertRaisesRegex(RuntimeError, "PaddleOCR is not installed"):
                load_backend("paddle")

    def test_unknown_engine_is_reported_without_loading_a_model(self):
        with self.assertRaisesRegex(ValueError, "Unknown OCR backend"):
            load_backend("not-an-engine")


if __name__ == "__main__":
    unittest.main()
