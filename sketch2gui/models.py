"""Shared, serializable design model used by the canvas, preview, and code generator."""
from __future__ import annotations

from dataclasses import dataclass, field
import copy
from typing import Any
from uuid import uuid4

SUPPORTED_ELEMENT_TYPES = {
    "button", "text_field", "search_field", "label", "checkbox",
    "dropdown", "table", "panel", "radio_button", "line",
}


def new_id(prefix: str = "element") -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


@dataclass
class Stroke:
    points: list[tuple[float, float]]
    stroke_id: str = field(default_factory=lambda: new_id("stroke"))
    width: float = 3.0

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.stroke_id, "points": [[round(x, 2), round(y, 2)] for x, y in self.points], "width": self.width}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Stroke":
        if not isinstance(data, dict):
            raise ValueError("Each project stroke must be a JSON object")
        points = data.get("points", [])
        if not isinstance(points, list) or any(not isinstance(p, (list, tuple)) or len(p) != 2 for p in points):
            raise ValueError("Invalid stroke points")
        clean = [(float(p[0]), float(p[1])) for p in points]
        return cls(clean, str(data.get("id") or new_id("stroke")), max(0.5, min(20.0, float(data.get("width", 3.0)))))


@dataclass
class UIElement:
    element_type: str
    x: float
    y: float
    width: float
    height: float
    text: str = ""
    placeholder: str = ""
    element_id: str = field(default_factory=lambda: new_id())
    confidence: float = 1.0
    alternatives: list[str] = field(default_factory=list)
    confirmed: bool = False
    user_modified: bool = False
    source_stroke_ids: list[str] = field(default_factory=list)
    ocr_confidence: float | None = None

    def __post_init__(self) -> None:
        if self.element_type not in SUPPORTED_ELEMENT_TYPES:
            raise ValueError(f"Unsupported component type: {self.element_type}")
        self.x = float(self.x)
        self.y = float(self.y)
        self.width = max(8.0, float(self.width))
        self.height = max(8.0, float(self.height))
        self.confidence = max(0.0, min(1.0, float(self.confidence)))

    @property
    def needs_review(self) -> bool:
        return not self.confirmed and self.confidence < 0.68

    def set_type(self, element_type: str, *, user_confirmed: bool = True) -> None:
        if element_type not in SUPPORTED_ELEMENT_TYPES:
            raise ValueError(f"Unsupported component type: {element_type}")
        self.element_type = element_type
        if not self.placeholder and element_type == "search_field":
            self.placeholder = self.text or "Search..."
        elif not self.placeholder and element_type == "text_field":
            self.placeholder = self.text or "Enter text..."
        if user_confirmed:
            self.user_modified = True
            self.confirmed = True
            self.confidence = 1.0
            self.alternatives = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.element_id, "type": self.element_type,
            "bounds": {"x": self.x, "y": self.y, "width": self.width, "height": self.height},
            "text": self.text, "placeholder": self.placeholder,
            "confidence": self.confidence, "alternatives": list(self.alternatives),
            "confirmed": self.confirmed, "user_modified": self.user_modified, "source_stroke_ids": list(self.source_stroke_ids),
            "ocr_confidence": self.ocr_confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UIElement":
        if not isinstance(data, dict):
            raise ValueError("Each project element must be a JSON object")
        bounds = data.get("bounds") or data
        if not isinstance(bounds, dict):
            raise ValueError("Project element bounds must be a JSON object")
        alternatives = data.get("alternatives", [])
        if not isinstance(alternatives, list):
            raise ValueError("Project element alternatives must be a JSON array")
        return cls(
            element_type=str(data.get("type", "panel")),
            x=float(bounds.get("x", 0)), y=float(bounds.get("y", 0)),
            width=float(bounds.get("width", 100)), height=float(bounds.get("height", 40)),
            text=str(data.get("text", "")), placeholder=str(data.get("placeholder", "")),
            element_id=str(data.get("id") or new_id()), confidence=float(data.get("confidence", 1.0)),
            alternatives=[str(x) for x in alternatives if x in SUPPORTED_ELEMENT_TYPES],
            confirmed=bool(data.get("confirmed", False)), user_modified=bool(data.get("user_modified", False)),
            source_stroke_ids=[str(x) for x in data.get("source_stroke_ids", [])],
            ocr_confidence=(None if data.get("ocr_confidence") is None else float(data["ocr_confidence"])),
        )


def preserve_manual_edits(previous: list[UIElement], detected: list[UIElement]) -> list[UIElement]:
    """Keep user-touched components stable when the sketch is interpreted again.

    Matching uses the IDs of the original mouse strokes, not approximate geometry.
    Newly drawn/replaced strokes therefore get freshly recognized components.
    """
    saved = {
        frozenset(element.source_stroke_ids): element
        for element in previous
        if element.user_modified and element.source_stroke_ids
    }
    result: list[UIElement] = []
    for element in detected:
        old = saved.get(frozenset(element.source_stroke_ids)) if element.source_stroke_ids else None
        result.append(copy.deepcopy(old) if old is not None else element)
    return result


@dataclass
class DesignDocument:
    width: int = 800
    height: int = 600
    strokes: list[Stroke] = field(default_factory=list)
    elements: list[UIElement] = field(default_factory=list)
    name: str = "Untitled sketch"

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "sketch2gui", "version": 1, "name": self.name,
            "canvas": {"width": self.width, "height": self.height},
            "strokes": [s.to_dict() for s in self.strokes],
            "elements": [e.to_dict() for e in self.elements],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DesignDocument":
        if not isinstance(data, dict):
            raise ValueError("Project data must be a JSON object")
        if data.get("format") not in (None, "sketch2gui"):
            raise ValueError("This is not a Sketch2GUI project file")
        canvas = data.get("canvas", {})
        if not isinstance(canvas, dict):
            raise ValueError("Project canvas must be a JSON object")
        strokes_data = data.get("strokes", [])
        elements_data = data.get("elements", [])
        if not isinstance(strokes_data, list) or not isinstance(elements_data, list):
            raise ValueError("Project strokes and elements must be JSON arrays")
        if any(not isinstance(item, dict) for item in strokes_data + elements_data):
            raise ValueError("Each project stroke and element must be a JSON object")
        width = max(200, min(3000, int(canvas.get("width", 800))))
        height = max(200, min(3000, int(canvas.get("height", 600))))
        return cls(
            width=width, height=height, name=str(data.get("name", "Untitled sketch")),
            strokes=[Stroke.from_dict(s) for s in strokes_data],
            elements=[UIElement.from_dict(e) for e in elements_data],
        )
