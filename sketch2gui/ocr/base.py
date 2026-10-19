"""Small interface and lazy loading for optional OCR backends."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class OCRResult:
    text: str
    confidence: float | None = None
    duration_ms: float | None = None


class OCRBackend(Protocol):
    name: str
    def recognize(self, image: Any) -> OCRResult: ...


def load_backend(name: str, *, paddle_preprocess: bool = True) -> OCRBackend:
    normalized = name.strip().lower()
    if normalized in ("paddle", "paddleocr"):
        from .paddle_backend import PaddleOCRBackend
        return PaddleOCRBackend(preprocess=paddle_preprocess)
    if normalized in ("trocr", "microsoft-trocr"):
        from .trocr_backend import TrOCRBackend
        return TrOCRBackend()
    raise ValueError(f"Unknown OCR backend: {name!r}. Choose 'paddle' or 'trocr'.")
