"""Microsoft TrOCR Base Handwritten adapter using Transformers/PyTorch."""
from __future__ import annotations

import time
from typing import Any

from .base import OCRResult


class TrOCRBackend:
    name = "Microsoft TrOCR Base Handwritten"
    MODEL_ID = "microsoft/trocr-base-handwritten"

    def __init__(self) -> None:
        try:
            import torch
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel
        except ImportError as exc:
            raise RuntimeError(
                "TrOCR dependencies are not installed. Follow the optional installation steps in README.md."
            ) from exc
        self._torch = torch
        # The model is much larger than the mobile Paddle recognizer and downloads on first use.
        self._processor = TrOCRProcessor.from_pretrained(self.MODEL_ID)
        self._model = VisionEncoderDecoderModel.from_pretrained(self.MODEL_ID)
        self._model.eval()

    def recognize(self, image: Any) -> OCRResult:
        from PIL import Image
        start = time.perf_counter()
        if isinstance(image, Image.Image):
            pil_image = image.convert("RGB")
        else:
            pil_image = Image.open(image).convert("RGB")
        inputs = self._processor(images=pil_image, return_tensors="pt")
        with self._torch.inference_mode():
            generated = self._model.generate(**inputs, max_new_tokens=96)
        text = self._processor.batch_decode(generated, skip_special_tokens=True)[0].strip()
        # TrOCR's default generation path doesn't expose a calibrated confidence score.
        return OCRResult(text=text, confidence=None,
                         duration_ms=(time.perf_counter() - start) * 1000)
