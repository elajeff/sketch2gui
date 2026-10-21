"""Shared, serializable design model used by the canvas, preview, and code generator."""
from __future__ import annotations

from dataclasses import dataclass, field
import copy
import math
from typing import Any
from uuid import uuid4

SUPPORTED_ELEMENT_TYPES = {
    "button", "text_field", "search_field", "label", "checkbox",
    "dropdown", "table", "panel", "radio_button", "line", "chart", "ellipse",
}

DEFAULT_DROPDOWN_OPTIONS = ("Choose...", "Option 1", "Option 2")

MAX_PROJECT_STROKES = 2_000
MAX_PROJECT_ELEMENTS = 2_000
MAX_STROKE_POINTS = 25_000
MAX_PROJECT_POINTS = 250_000


def new_id(prefix: str = "element") -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


@dataclass
class Stroke:
    points: list[tuple[float, float]]
    stroke_id: str = field(default_factory=lambda: new_id("stroke"))
    width: float = 3.0

    def __post_init__(self) -> None:
        try:
            width = float(self.width)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Stroke width must be a finite number") from exc
        if not math.isfinite(width):
            raise ValueError("Stroke width must be a finite number")
        self.width = min(20.0, max(0.5, width))

        if not isinstance(self.points, (list, tuple)):
            raise ValueError("Stroke points must be a list of coordinate pairs")
        normalized_points: list[tuple[float, float]] = []
        for point in self.points:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise ValueError("Invalid stroke points")
            try:
                x, y = float(point[0]), float(point[1])
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Stroke coordinates must be finite numbers") from exc
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError("Stroke coordinates must be finite numbers")
            normalized_points.append((x, y))
        self.points = normalized_points

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.stroke_id,
            "points": [[round(x, 2), round(y, 2)] for x, y in self.points],
            "width": self.width,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Stroke":
        if not isinstance(data, dict):
            raise ValueError("Each project stroke must be a JSON object")
        points = data.get("points", [])
        if not isinstance(points, list) or any(not isinstance(p, (list, tuple)) or len(p) != 2 for p in points):
            raise ValueError("Invalid stroke points")
        return cls(points, str(data.get("id") or new_id("stroke")), data.get("width", 3.0))


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
    chart_values: list[float] = field(default_factory=list)
    table_rows: int = 3
    table_columns: int = 3
    table_cells: list[list[str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.element_type not in SUPPORTED_ELEMENT_TYPES:
            raise ValueError(f"Unsupported component type: {self.element_type}")
        try:
            self.x, self.y, self.width, self.height = (
                float(value) for value in (self.x, self.y, self.width, self.height)
            )
            confidence = float(self.confidence)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Component geometry and confidence must be finite numbers") from exc
        if not all(math.isfinite(value) for value in (self.x, self.y, self.width, self.height, confidence)):
            raise ValueError("Component geometry and confidence must be finite numbers")
        self.width = max(8.0, self.width)
        self.height = max(8.0, self.height)
        self.confidence = max(0.0, min(1.0, confidence))
        if self.ocr_confidence is not None:
            try:
                ocr_confidence = float(self.ocr_confidence)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("OCR confidence must be a finite number or None") from exc
            if not math.isfinite(ocr_confidence):
                raise ValueError("OCR confidence must be a finite number or None")
            self.ocr_confidence = max(0.0, min(1.0, ocr_confidence))
        if not isinstance(self.chart_values, list) or len(self.chart_values) > 100:
            raise ValueError("Chart values must be a list containing at most 100 numbers")
        clean_values = []
        for value in self.chart_values:
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Chart values must be finite numbers") from exc
            if not math.isfinite(number):
                raise ValueError("Chart values must be finite numbers")
            clean_values.append(number)
        self.chart_values = clean_values
        try:
            self.table_rows = max(1, min(20, int(self.table_rows)))
            self.table_columns = max(1, min(20, int(self.table_columns)))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Table dimensions must be integers between 1 and 20") from exc
        if self.element_type != "table":
            self.table_cells = []
        else:
            if not isinstance(self.table_cells, list):
                raise ValueError("Table cells must be a list of rows")
            normalized_cells: list[list[str]] = []
            for row_index in range(self.table_rows):
                row = self.table_cells[row_index] if row_index < len(self.table_cells) else []
                if not isinstance(row, list):
                    raise ValueError("Each table row must be a list")
                normalized_cells.append([str(row[col])[:500] if col < len(row) else ""
                                         for col in range(self.table_columns)])
            self.table_cells = normalized_cells

    @property
    def needs_review(self) -> bool:
        return not self.confirmed and self.confidence < 0.68

    def mark_user_modified(self) -> None:
        """Mark a deliberate edit as confirmed and clear recognition alternatives."""
        self.user_modified = True
        self.confirmed = True
        self.confidence = 1.0
        self.alternatives = []

    def set_type(self, element_type: str, *, user_confirmed: bool = True) -> None:
        if element_type not in SUPPORTED_ELEMENT_TYPES:
            raise ValueError(f"Unsupported component type: {element_type}")
        previous_type = self.element_type
        if element_type == "table" and previous_type != "table":
            self.table_cells = [
                ["" for _ in range(self.table_columns)]
                for _ in range(self.table_rows)
            ]
        elif previous_type == "table" and element_type != "table":
            self.table_cells = []
        self.element_type = element_type
        if not self.placeholder and element_type == "search_field":
            self.placeholder = self.text or "Search..."
        elif not self.placeholder and element_type == "text_field":
            self.placeholder = self.text or "Enter text..."
        if user_confirmed:
            self.mark_user_modified()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.element_id, "type": self.element_type,
            "bounds": {"x": self.x, "y": self.y, "width": self.width, "height": self.height},
            "text": self.text, "placeholder": self.placeholder,
            "confidence": self.confidence, "alternatives": list(self.alternatives),
            "confirmed": self.confirmed,
            "user_modified": self.user_modified,
            "source_stroke_ids": list(self.source_stroke_ids),
            "ocr_confidence": self.ocr_confidence,
            "chart_values": list(self.chart_values),
            "table_rows": self.table_rows,
            "table_columns": self.table_columns,
            "table_cells": [list(row) for row in self.table_cells],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UIElement":
        if not isinstance(data, dict):
            raise ValueError("Each project element must be a JSON object")
        bounds = data.get("bounds") or data
        if not isinstance(bounds, dict):
            raise ValueError("Project element bounds must be a JSON object")
        alternatives = data.get("alternatives", [])
        source_stroke_ids = data.get("source_stroke_ids", [])
        chart_values_data = data.get("chart_values", [])
        table_cells_data = data.get("table_cells", [])
        if not isinstance(source_stroke_ids, list):
            raise ValueError("Project source stroke IDs must be a JSON array")
        if not isinstance(table_cells_data, list) or any(not isinstance(row, list) for row in table_cells_data):
            raise ValueError("Project table cells must be an array of row arrays")
        try:
            table_rows = int(data.get("table_rows", 3))
            table_columns = int(data.get("table_columns", 3))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Project table dimensions must be integers between 1 and 20") from exc
        if not 1 <= table_rows <= 20 or not 1 <= table_columns <= 20:
            raise ValueError("Project table dimensions must be between 1 and 20")
        if len(table_cells_data) > 20 or any(len(row) > 20 for row in table_cells_data):
            raise ValueError("Project table cells cannot exceed 20 rows or columns")
        if not isinstance(chart_values_data, list) or len(chart_values_data) > 100:
            raise ValueError("Project chart values must be an array containing at most 100 numbers")
        if not isinstance(alternatives, list):
            raise ValueError("Project element alternatives must be a JSON array")
        try:
            chart_values = [float(value) for value in chart_values_data]
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Project chart values must be finite numbers") from exc
        return cls(
            element_type=str(data.get("type", "panel")),
            x=float(bounds.get("x", 0)), y=float(bounds.get("y", 0)),
            width=float(bounds.get("width", 100)), height=float(bounds.get("height", 40)),
            text=str(data.get("text", "")), placeholder=str(data.get("placeholder", "")),
            element_id=str(data.get("id") or new_id()), confidence=float(data.get("confidence", 1.0)),
            alternatives=[str(x) for x in alternatives if x in SUPPORTED_ELEMENT_TYPES],
            confirmed=bool(data.get("confirmed", False)), user_modified=bool(data.get("user_modified", False)),
            source_stroke_ids=[str(x) for x in source_stroke_ids],
            ocr_confidence=(None if data.get("ocr_confidence") is None else float(data["ocr_confidence"])),
            chart_values=chart_values,
            table_rows=table_rows, table_columns=table_columns,
            table_cells=[[str(value)[:500] for value in row[:table_columns]]
                          for row in table_cells_data[:table_rows]],
        )


def preserve_manual_edits(previous: list[UIElement], detected: list[UIElement]) -> list[UIElement]:
    """Retain manual edits while replacing only the recognition results."""
    saved = {
        frozenset(element.source_stroke_ids): element
        for element in previous
        if element.user_modified and element.source_stroke_ids
    }
    manual_elements = [
        element for element in previous
        if element.user_modified and not element.source_stroke_ids
    ]

    def overlaps_manual(candidate: UIElement, manual: UIElement) -> bool:
        intersection = (
            max(0.0, min(manual.x + manual.width, candidate.x + candidate.width)
                - max(manual.x, candidate.x))
            * max(0.0, min(manual.y + manual.height, candidate.y + candidate.height)
                  - max(manual.y, candidate.y))
        )
        smaller_area = min(manual.width * manual.height, candidate.width * candidate.height)
        larger_area = max(manual.width * manual.height, candidate.width * candidate.height)
        return (
            smaller_area > 0 and larger_area > 0
            and smaller_area / larger_area >= 0.50
            and intersection / smaller_area >= 0.72
        )

    # Suppress only fresh detections; never filter preserved user elements.
    candidates = [
        candidate for candidate in detected
        if not any(overlaps_manual(candidate, manual) for manual in manual_elements)
    ]
    result: list[UIElement] = []
    matched: set[frozenset[str]] = set()
    for candidate in candidates:
        source_ids = frozenset(candidate.source_stroke_ids)
        if source_ids and source_ids in saved:
            result.append(copy.deepcopy(saved[source_ids]))
            matched.add(source_ids)
        else:
            result.append(candidate)

    result.extend(copy.deepcopy(element) for key, element in saved.items() if key not in matched)
    result.extend(copy.deepcopy(element) for element in manual_elements)
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
        version = data.get("version", 1)
        if isinstance(version, bool) or version != 1:
            raise ValueError(f"Unsupported Sketch2GUI project version: {version!r}")
        canvas = data.get("canvas", {})
        if not isinstance(canvas, dict):
            raise ValueError("Project canvas must be a JSON object")
        strokes_data = data.get("strokes", [])
        elements_data = data.get("elements", [])
        if not isinstance(strokes_data, list) or not isinstance(elements_data, list):
            raise ValueError("Project strokes and elements must be JSON arrays")
        if len(strokes_data) > MAX_PROJECT_STROKES:
            raise ValueError(f"Project has more than {MAX_PROJECT_STROKES} strokes")
        if len(elements_data) > MAX_PROJECT_ELEMENTS:
            raise ValueError(f"Project has more than {MAX_PROJECT_ELEMENTS} components")
        if any(not isinstance(item, dict) for item in strokes_data + elements_data):
            raise ValueError("Each project stroke and element must be a JSON object")
        total_points = 0
        for stroke_data in strokes_data:
            points = stroke_data.get("points", [])
            if isinstance(points, list):
                if len(points) > MAX_STROKE_POINTS:
                    raise ValueError(f"A stroke has more than {MAX_STROKE_POINTS} points")
                total_points += len(points)
                if total_points > MAX_PROJECT_POINTS:
                    raise ValueError(f"Project has more than {MAX_PROJECT_POINTS} stroke points")
        try:
            width = max(200, min(3000, int(canvas.get("width", 800))))
            height = max(200, min(3000, int(canvas.get("height", 600))))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Project canvas dimensions must be integers between 200 and 3000") from exc
        strokes = [Stroke.from_dict(stroke) for stroke in strokes_data]
        for stroke in strokes:
            if any(
                x < 0 or y < 0 or x > width or y > height
                for x, y in stroke.points
            ):
                raise ValueError("Project stroke coordinates must lie within canvas bounds")

        elements = [UIElement.from_dict(element) for element in elements_data]
        # A finite number can still be far outside the canvas. Normalize saved
        # bounds before the UI turns them into native Qt widget geometries.
        for element in elements:
            element.width = min(element.width, float(width))
            element.height = min(element.height, float(height))
            element.x = min(max(0.0, element.x), float(width) - element.width)
            element.y = min(max(0.0, element.y), float(height) - element.height)

        if len({stroke.stroke_id for stroke in strokes}) != len(strokes):
            raise ValueError("Project contains duplicate stroke IDs")
        if len({element.element_id for element in elements}) != len(elements):
            raise ValueError("Project contains duplicate component IDs")

        return cls(
            width=width, height=height, name=str(data.get("name", "Untitled sketch")),
            strokes=strokes,
            elements=elements,
        )
