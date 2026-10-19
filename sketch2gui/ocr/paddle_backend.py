"""PaddleOCR PP-OCRv5 mobile English text-line recognizer adapter."""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from .base import OCRResult


def _find_text_and_score(value: Any) -> tuple[str, float | None]:
    """Handle the result shapes returned by PaddleOCR's result wrappers."""
    if hasattr(value, "json"):
        value = value.json
    if callable(value):
        try:
            value = value()
        except Exception:
            pass
    if isinstance(value, str):
        import json
        try:
            value = json.loads(value)
        except Exception:
            return value, None
    if isinstance(value, dict):
        # Text recognition module uses rec_text / rec_score in its result payload.
        text = value.get("rec_text", value.get("rec_texts", value.get("text")))
        score = value.get("rec_score", value.get("rec_scores", value.get("score", value.get("confidence"))))
        if isinstance(text, list):
            if isinstance(score, list):
                numeric = []
                for item in score:
                    try:
                        numeric.append(float(item))
                    except (TypeError, ValueError):
                        pass
                score = (sum(numeric) / len(numeric)) if numeric else None
            text = " ".join(map(str, text))
        if text is not None:
            try:
                score = float(score) if score is not None else None
            except (TypeError, ValueError):
                score = None
            return str(text), score
        for child in value.values():
            result = _find_text_and_score(child)
            if result[0]:
                return result
    elif isinstance(value, (list, tuple)):
        collected = [_find_text_and_score(item) for item in value]
        texts = [item[0] for item in collected if item[0]]
        scores = [item[1] for item in collected if item[1] is not None]
        if texts:
            return " ".join(texts), (sum(scores) / len(scores) if scores else None)
    return "", None


def preprocess_for_paddle(image: Image.Image) -> Image.Image:
    """Apply the binary text-line preprocessing that performed best in our small trial.

    The original 19-crop experiment found binary preprocessing tied with tight-pad
    cropping on exact match and CER, while being about 1 ms faster at the median.
    This is a practical default, not a claim of generally accurate handwriting OCR.
    """
    rgb = image.convert("RGB")
    gray = ImageOps.grayscale(rgb)

    # Crop around dark ink (including antialiased edges), then add a small white margin.
    ink_mask = gray.point(lambda value: 255 if value < 245 else 0)
    bbox = ink_mask.getbbox()
    if bbox is not None:
        cropped = rgb.crop(bbox)
        width, height = cropped.size
        pad_x = max(10, round(width * 0.12))
        pad_y = max(10, round(height * 0.30))
        padded = Image.new("RGB", (width + 2 * pad_x, height + 2 * pad_y), "white")
        padded.paste(cropped, (pad_x, pad_y))
    else:
        padded = rgb.copy()

    # Match the tested binary variant: dark pixels below 200 become black, others white.
    binary = ImageOps.grayscale(padded).point(lambda value: 0 if value < 200 else 255)
    return Image.merge("RGB", (binary, binary, binary))


class PaddleOCRBackend:
    name = "PaddleOCR PP-OCRv5 mobile English"

    def __init__(self, *, preprocess: bool = True) -> None:
        self.use_preprocessing = preprocess
        try:
            from paddleocr import TextRecognition
        except ImportError as exc:
            raise RuntimeError(
                "PaddleOCR is not installed. Follow the optional installation steps in README.md."
            ) from exc
        # Lazy model construction makes startup light; first use may download model files.
        self._model = TextRecognition(model_name="en_PP-OCRv5_mobile_rec")

    def recognize(self, image: Any) -> OCRResult:
        from PIL import Image
        start = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="sketch2gui-ocr-") as folder:
            path = Path(folder) / "text-line.png"
            if isinstance(image, Image.Image):
                source_image = image.copy()
            else:
                with Image.open(image) as opened:
                    source_image = opened.copy()
            prepared = preprocess_for_paddle(source_image) if self.use_preprocessing else source_image.convert("RGB")
            prepared.save(path)
            output = self._model.predict(input=str(path), batch_size=1)
        text, score = _find_text_and_score(output)
        return OCRResult(text=text.strip(), confidence=score,
                         duration_ms=(time.perf_counter() - start) * 1000)
