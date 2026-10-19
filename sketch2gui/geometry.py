"""Deterministic first-pass freehand geometry and component recognition."""
from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from .models import DesignDocument, Stroke, UIElement

OCRCallable = Callable[[Any], Any]


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def stroke_bounds(stroke: Stroke) -> tuple[float, float, float, float]:
    xs = [p[0] for p in stroke.points]
    ys = [p[1] for p in stroke.points]
    return min(xs), min(ys), max(xs), max(ys)


def _is_closed(stroke: Stroke) -> bool:
    if len(stroke.points) < 8:
        return False
    x1, y1, x2, y2 = stroke_bounds(stroke)
    diagonal = math.hypot(x2 - x1, y2 - y1)
    return diagonal >= 12 and _distance(stroke.points[0], stroke.points[-1]) <= max(15.0, diagonal * 0.10)


def _line_straightness(stroke: Stroke) -> float:
    if len(stroke.points) < 2:
        return 0.0
    direct = _distance(stroke.points[0], stroke.points[-1])
    travel = sum(_distance(a, b) for a, b in zip(stroke.points, stroke.points[1:]))
    return direct / max(travel, 1e-6)


def _ellipse_error(stroke: Stroke) -> float:
    x1, y1, x2, y2 = stroke_bounds(stroke)
    rx, ry = max((x2 - x1) / 2, 1), max((y2 - y1) / 2, 1)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    values = [abs(math.sqrt(((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2) - 1) for x, y in stroke.points]
    return sum(values) / len(values)


def classify_stroke(stroke: Stroke) -> tuple[str, float] | None:
    """Return (shape, confidence) for a single stroke; unknown strokes return None."""
    if len(stroke.points) < 2:
        return None
    x1, y1, x2, y2 = stroke_bounds(stroke)
    width, height = x2 - x1, y2 - y1
    if width < 3 and height < 3:
        return None
    if _is_closed(stroke):
        if width < 14 or height < 14:
            return None
        ellipse_error = _ellipse_error(stroke)
        if ellipse_error < 0.13:
            return "ellipse", max(0.55, min(0.92, 0.92 - ellipse_error * 1.8))
        confidence = 0.88 if ellipse_error > 0.20 else 0.70
        return "rectangle", confidence
    if _line_straightness(stroke) >= 0.88 and max(width, height) >= 24:
        return "line", min(0.97, 0.70 + _line_straightness(stroke) * 0.28)
    return None


def _contains(bounds: tuple[float, float, float, float], inner: tuple[float, float, float, float], margin: float = 1) -> bool:
    x1, y1, x2, y2 = bounds
    a, b, c, d = inner
    return a >= x1 + margin and b >= y1 + margin and c <= x2 - margin and d <= y2 - margin


def _horizontal_rule(stroke: Stroke, bounds: tuple[float, float, float, float]) -> bool:
    x1, y1, x2, y2 = stroke_bounds(stroke)
    outer_w, outer_h = bounds[2] - bounds[0], bounds[3] - bounds[1]
    return (x2 - x1 >= outer_w * 0.35 and (y2 - y1) <= max(6, outer_h * 0.09)
            and x1 > bounds[0] and x2 < bounds[2] and y1 > bounds[1] and y2 < bounds[3])


def _interior_image(strokes: list[Stroke], bounds: tuple[float, float, float, float], scale: float = 2.0):
    """Render non-outline strokes inside bounds to a white PIL image for line OCR."""
    from PIL import Image, ImageDraw
    x1, y1, x2, y2 = bounds
    candidates = [s for s in strokes if len(s.points) >= 2 and _contains(bounds, stroke_bounds(s), margin=1)]
    if not candidates:
        return None
    # Table rules are not text; don't send them to OCR.
    if sum(_horizontal_rule(s, bounds) for s in candidates) >= 2:
        return None
    points = [p for s in candidates for p in s.points]
    left, top = min(p[0] for p in points), min(p[1] for p in points)
    right, bottom = max(p[0] for p in points), max(p[1] for p in points)
    if right - left < 4 or bottom - top < 4:
        return None
    pad = 8
    scale = min(scale, 1180 / max(right - left + pad * 2, 1), 280 / max(bottom - top + pad * 2, 1))
    w, h = max(32, int((right - left + pad * 2) * scale)), max(24, int((bottom - top + pad * 2) * scale))
    image = Image.new("RGB", (min(w, 1200), min(h, 300)), "white")
    draw = ImageDraw.Draw(image)
    for s in candidates:
        coords = [((x - left + pad) * scale, (y - top + pad) * scale) for x, y in s.points]
        if len(coords) >= 2:
            draw.line(coords, fill="black", width=2, joint="curve")
    return image



def _render_strokes(strokes: list[Stroke], scale: float = 3.0):
    """Render a group of freehand strokes as a padded image for line OCR."""
    from PIL import Image, ImageDraw
    points = [point for stroke in strokes for point in stroke.points]
    if not points:
        return None
    left, top = min(p[0] for p in points), min(p[1] for p in points)
    right, bottom = max(p[0] for p in points), max(p[1] for p in points)
    if right - left < 5 or bottom - top < 4:
        return None
    pad = 10
    scale = min(scale, 1380 / max(right - left + 2 * pad, 1), 300 / max(bottom - top + 2 * pad, 1))
    width = max(32, int((right - left + 2 * pad) * scale))
    height = max(28, int((bottom - top + 2 * pad) * scale))
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    for stroke in strokes:
        coords = [((x - left + pad) * scale, (y - top + pad) * scale) for x, y in stroke.points]
        if len(coords) >= 2:
            draw.line(coords, fill="black", width=3, joint="curve")
    return image


def _cluster_text_strokes(strokes: list[Stroke], excluded_ids: set[str]) -> list[list[Stroke]]:
    """Group nearby non-container strokes into rough handwritten text lines."""
    candidates = [s for s in strokes if s.stroke_id not in excluded_ids and len(s.points) >= 2]
    candidates.sort(key=lambda s: (stroke_bounds(s)[1], stroke_bounds(s)[0]))
    groups: list[list[Stroke]] = []
    group_bounds: list[list[float]] = []
    for stroke in candidates:
        box = stroke_bounds(stroke)
        x1, y1, x2, y2 = box
        matched = None
        for i, group_box in enumerate(group_bounds):
            gx1, gy1, gx2, gy2 = group_box
            height = max(y2 - y1, gy2 - gy1, 8)
            vertical_gap = max(0.0, max(gy1, y1) - min(gy2, y2))
            horizontal_gap = max(0.0, max(gx1, x1) - min(gx2, x2))
            if vertical_gap <= max(15, height * 0.75) and horizontal_gap <= max(30, height * 2.0):
                matched = i
                break
        if matched is None:
            groups.append([stroke])
            group_bounds.append([x1, y1, x2, y2])
        else:
            groups[matched].append(stroke)
            b = group_bounds[matched]
            b[0], b[1], b[2], b[3] = min(b[0], x1), min(b[1], y1), max(b[2], x2), max(b[3], y2)
    # Do not treat one bare line as a word. Two or more pen strokes are a safer minimum.
    return [group for group in groups if len(group) >= 2]


def recognize_sketch(document: DesignDocument, ocr: OCRCallable | None = None) -> list[UIElement]:
    """Convert freehand strokes into candidate GUI elements, with honest uncertainty."""
    strokes = document.strokes
    shape_strokes: list[tuple[Stroke, str, float, tuple[float, float, float, float]]] = []
    for stroke in strokes:
        result = classify_stroke(stroke)
        if result:
            shape_strokes.append((stroke, result[0], result[1], stroke_bounds(stroke)))

    rectangles = [item for item in shape_strokes if item[1] == "rectangle"]
    rectangle_ids = {item[0].stroke_id for item in rectangles}
    elements: list[UIElement] = []
    used_strokes: set[str] = set()

    for shape_stroke, _shape, shape_conf, bounds in sorted(rectangles, key=lambda item: ((item[3][2]-item[3][0])*(item[3][3]-item[3][1])), reverse=True):
        x1, y1, x2, y2 = bounds
        width, height = x2 - x1, y2 - y1
        nested = [item for item in rectangles
                  if item[0].stroke_id != shape_stroke.stroke_id
                  and _contains(bounds, item[3], margin=2)
                  and (item[3][2] - item[3][0]) * (item[3][3] - item[3][1]) < width * height * 0.95]
        nested_bounds = [item[3] for item in nested]
        contained = [s for s in strokes if len(s.points) >= 2 and s.stroke_id != shape_stroke.stroke_id
                     and s.stroke_id not in rectangle_ids
                     and _contains(bounds, stroke_bounds(s), margin=1)
                     and not any(_contains(inner, stroke_bounds(s), margin=0) for inner in nested_bounds)]
        rules = [s for s in contained if _horizontal_rule(s, bounds)]
        text = ""
        ocr_confidence = None
        element_type = "panel"
        confidence = 0.53
        alternatives: list[str] = ["button", "text_field", "table"]
        ratio = width / max(height, 1)

        if nested:
            element_type, confidence, alternatives = "panel", 0.86, ["panel", "button"]
        elif len(rules) >= 2:
            element_type, confidence, alternatives = "table", 0.82, ["panel", "search_field"]
        elif contained:
            result = None
            if ocr:
                crop = _interior_image(contained, bounds)
                if crop is not None:
                    try:
                        result = ocr(crop)
                    except Exception:
                        result = None
            if result is not None:
                text = str(getattr(result, "text", "") or "").strip()
                ocr_confidence = getattr(result, "confidence", None)
                normal = " ".join(text.lower().replace("_", " ").split())
                if any(term in normal for term in ("search", "find", "filter")) and ratio > 2.0:
                    element_type, confidence, alternatives = "search_field", 0.90, ["text_field", "button"]
                elif any(term in normal for term in ("email", "password", "username", "enter text")) and ratio > 2.0:
                    element_type, confidence, alternatives = "text_field", 0.86, ["search_field", "button"]
                elif text:
                    element_type, confidence, alternatives = "button", 0.78, ["label", "text_field"]
                else:
                    element_type, confidence, alternatives = "button", 0.58, ["text_field", "search_field"]
            elif ratio >= 3.4:
                element_type, confidence, alternatives = "text_field", 0.59, ["search_field", "button"]
            else:
                element_type, confidence, alternatives = "button", 0.58, ["text_field", "panel"]
        elif ratio > 3.8 and height <= 60:
            element_type, confidence, alternatives = "text_field", 0.56, ["search_field", "button"]
        else:
            # Empty rectangles are commonly panels, but may be unfinished controls.
            element_type, confidence, alternatives = "panel", 0.60, ["button", "text_field"]

        children_ids = [s.stroke_id for s in contained]
        used_strokes.add(shape_stroke.stroke_id)
        used_strokes.update(children_ids)
        placeholder = (text or "Search...") if element_type == "search_field" else ((text or "Enter text...") if element_type == "text_field" else "")
        elements.append(UIElement(
            element_type, x1, y1, width, height, text=text, placeholder=placeholder,
            confidence=min(confidence, shape_conf + 0.12), alternatives=alternatives,
            confirmed=False, source_stroke_ids=[shape_stroke.stroke_id, *children_ids],
            ocr_confidence=ocr_confidence,
        ))

    # OCR may also find labels drawn outside any enclosing control.
    if ocr:
        enclosed_ids = set(used_strokes) | rectangle_ids
        text_groups = _cluster_text_strokes(strokes, enclosed_ids)
        recognized_text_ids: set[str] = set()
        for group in text_groups:
            image = _render_strokes(group)
            if image is None:
                continue
            try:
                result = ocr(image)
            except Exception:
                continue
            text = str(getattr(result, "text", "") or "").strip()
            if not text:
                continue
            points = [p for s in group for p in s.points]
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            elements.append(UIElement(
                "label", min(xs), min(ys), max(24, max(xs)-min(xs)), max(18, max(ys)-min(ys)),
                text=text, confidence=0.84, alternatives=[], confirmed=False,
                source_stroke_ids=[s.stroke_id for s in group],
                ocr_confidence=getattr(result, "confidence", None),
            ))
            recognized_text_ids.update(s.stroke_id for s in group)
        used_strokes.update(recognized_text_ids)
        if recognized_text_ids:
            # Don't display a recognized word's individual straight strokes as separate dividers.
            elements = [e for e in elements if not (e.element_type == "line" and any(sid in recognized_text_ids for sid in e.source_stroke_ids))]

    # Keep standalone lines/circles so the user can still see and correct simple marks.
    for stroke, shape, confidence, bounds in shape_strokes:
        if stroke.stroke_id in used_strokes:
            continue
        x1, y1, x2, y2 = bounds
        if shape == "line":
            elements.append(UIElement("line", x1, y1, max(8, x2-x1), max(8, y2-y1), confidence=confidence,
                                       alternatives=["panel"], source_stroke_ids=[stroke.stroke_id]))
        elif shape == "ellipse":
            elements.append(UIElement("radio_button", x1, y1, max(18, x2-x1), max(18, y2-y1), confidence=0.62,
                                       alternatives=["checkbox", "label"], source_stroke_ids=[stroke.stroke_id]))

    # No useful shape was found: offer a low-confidence box around the strokes instead of losing them.
    if not elements and strokes:
        points = [p for stroke in strokes for p in stroke.points]
        if points:
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            elements.append(UIElement("panel", min(xs), min(ys), max(30, max(xs)-min(xs)), max(24, max(ys)-min(ys)),
                                      confidence=0.32, alternatives=["button", "label", "text_field"],
                                      source_stroke_ids=[s.stroke_id for s in strokes]))
    return elements
