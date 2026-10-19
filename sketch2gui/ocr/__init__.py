"""Optional OCR engines. Core geometry recognition does not require these extras."""
from .base import OCRResult, load_backend

__all__ = ["OCRResult", "load_backend"]
