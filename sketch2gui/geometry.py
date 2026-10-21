"""Deterministic first-pass freehand geometry and component recognition."""
from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from .models import DesignDocument, Stroke, UIElement

OCRCallable = Callable[[Any], Any]


def _limit_confidence_with_ocr(base_confidence: float, ocr_confidence: Any) -> float:
    """Cap suggestion confidence when the OCR score is weak or unavailable.

    OCR scores are model-specific and uncalibrated. This simple mapping is a
    conservative review heuristic, not a probability of correctness.
    """
    score = _normalize_ocr_confidence(ocr_confidence)
    if score is None:
        return min(base_confidence, 0.55)
    return min(base_confidence, 0.35 + 0.5 * score)

def _normalize_ocr_confidence(value: Any) -> float | None:
    """Return a finite OCR score in [0, 1], or None when the engine omits it."""
    try:
        score = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(score):
        return None
    return min(1.0, max(0.0, score))


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


def _vertical_rule(stroke: Stroke, bounds: tuple[float, float, float, float]) -> bool:
    """Return whether a stroke looks like an internal vertical table divider."""
    x1, y1, x2, y2 = stroke_bounds(stroke)
    outer_w, outer_h = bounds[2] - bounds[0], bounds[3] - bounds[1]
    return (y2 - y1 >= outer_h * 0.20 and (x2 - x1) <= max(6, outer_w * 0.09)
            and x1 > bounds[0] and x2 < bounds[2] and y1 > bounds[1] and y2 < bounds[3])


def _axis_line_kind(stroke: Stroke) -> str | None:
    """Classify a long, nearly horizontal/vertical stroke for grid grouping."""
    if len(stroke.points) < 2 or _line_straightness(stroke) < 0.72:
        return None
    x1, y1, x2, y2 = stroke_bounds(stroke)
    width, height = x2 - x1, y2 - y1
    if width >= 32 and height <= max(10.0, width * 0.10):
        return "horizontal"
    if height >= 32 and width <= max(10.0, height * 0.10):
        return "vertical"
    return None


def _distinct_coordinates(values: list[float], tolerance: float) -> list[float]:
    """Merge near-identical coordinates caused by double-traced freehand lines."""
    centers: list[float] = []
    for value in sorted(values):
        if not centers or value - centers[-1] > tolerance:
            centers.append(value)
        else:
            centers[-1] = (centers[-1] + value) / 2
    return centers


def _detect_multistroke_tables(strokes: list[Stroke]) -> tuple[list[UIElement], set[str]]:
    """Recognize a simple table drawn as separate horizontal/vertical strokes.

    Requires a rectangular pair of horizontal edges, matching vertical sides,
    and at least one internal row/column divider. This stays geometry-based.
    """
    horizontal: list[tuple[Stroke, tuple[float, float, float, float]]] = []
    vertical: list[tuple[Stroke, tuple[float, float, float, float]]] = []
    for stroke in strokes:
        kind = _axis_line_kind(stroke)
        if kind == "horizontal":
            horizontal.append((stroke, stroke_bounds(stroke)))
        elif kind == "vertical":
            vertical.append((stroke, stroke_bounds(stroke)))

    # Pairing every rule with every other rule becomes expensive on dense sketches.
    if len(horizontal) + len(vertical) > 120:
        return [], set()

    candidates: list[tuple[float, UIElement, set[str]]] = []
    for i, (_first, a) in enumerate(horizontal):
        for _second, b in horizontal[i + 1:]:
            ya, yb = (a[1] + a[3]) / 2, (b[1] + b[3]) / 2
            if ya == yb:
                continue
            top_box, bottom_box = (a, b) if ya < yb else (b, a)
            top_y = (top_box[1] + top_box[3]) / 2
            bottom_y = (bottom_box[1] + bottom_box[3]) / 2
            height = bottom_y - top_y
            if height < 30:
                continue
            shorter_width = min(top_box[2] - top_box[0], bottom_box[2] - bottom_box[0])
            overlap = min(top_box[2], bottom_box[2]) - max(top_box[0], bottom_box[0])
            if shorter_width <= 0 or overlap / shorter_width < 0.68:
                continue

            left = (top_box[0] + bottom_box[0]) / 2
            right = (top_box[2] + bottom_box[2]) / 2
            width = right - left
            if width < 55:
                continue
            tolerance = max(10.0, min(22.0, min(width, height) * 0.10))

            member_h = []
            for stroke, box in horizontal:
                cy = (box[1] + box[3]) / 2
                span = min(right, box[2]) - max(left, box[0])
                if (top_y - tolerance <= cy <= bottom_y + tolerance
                        and span >= width * 0.68
                        and box[0] <= left + tolerance and box[2] >= right - tolerance):
                    member_h.append((stroke, box))

            member_v = []
            for stroke, box in vertical:
                cx = (box[0] + box[2]) / 2
                span = min(bottom_y, box[3]) - max(top_y, box[1])
                if (left - tolerance <= cx <= right + tolerance
                        and span >= height * 0.68
                        and box[1] <= top_y + tolerance and box[3] >= bottom_y - tolerance):
                    member_v.append((stroke, box))

            v_xs = [(box[0] + box[2]) / 2 for _, box in member_v]
            if not (any(abs(x - left) <= tolerance for x in v_xs)
                    and any(abs(x - right) <= tolerance for x in v_xs)):
                continue
            h_levels = _distinct_coordinates(
                [(box[1] + box[3]) / 2 for _, box in member_h], max(6.0, height * 0.035)
            )
            v_levels = _distinct_coordinates(v_xs, max(6.0, width * 0.025))
            if len(h_levels) < 2 or len(v_levels) < 2:
                continue
            if len(h_levels) < 3 and len(v_levels) < 3:
                continue

            member_ids = {stroke.stroke_id for stroke, _ in (*member_h, *member_v)}
            element = UIElement(
                "table", left, top_y, width, height,
                confidence=0.84, alternatives=["panel"], confirmed=False,
                source_stroke_ids=[s.stroke_id for s in strokes if s.stroke_id in member_ids],
            )
            candidates.append((width * height, element, member_ids))

    # Prefer a whole table over smaller candidate grids formed by adjacent rows.
    candidates.sort(key=lambda candidate: candidate[0], reverse=True)
    accepted: list[tuple[float, UIElement, set[str]]] = []
    for candidate in candidates:
        _, element, _ = candidate
        x1, y1 = element.x, element.y
        x2, y2 = x1 + element.width, y1 + element.height
        duplicate = False
        for _, existing, _ in accepted:
            ex1, ey1 = existing.x, existing.y
            ex2, ey2 = ex1 + existing.width, ey1 + existing.height
            intersection = max(0.0, min(x2, ex2) - max(x1, ex1)) * max(0.0, min(y2, ey2) - max(y1, ey1))
            smaller_area = min(element.width * element.height, existing.width * existing.height)
            if smaller_area > 0 and intersection / smaller_area >= 0.65:
                duplicate = True
                break
        if not duplicate:
            accepted.append(candidate)

    elements = [element for _, element, _ in accepted]
    used_ids = set().union(*(ids for _, _, ids in accepted)) if accepted else set()
    return elements, used_ids


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


def _detect_multistroke_rectangles(strokes: list[Stroke], excluded_ids: set[str]) -> tuple[list[UIElement], set[str]]:
    """Group four separate axis-aligned strokes into a low-confidence box candidate."""
    horizontal = []
    vertical = []
    for stroke in strokes:
        if stroke.stroke_id in excluded_ids:
            continue
        kind = _axis_line_kind(stroke)
        if kind == "horizontal":
            horizontal.append((stroke, stroke_bounds(stroke)))
        elif kind == "vertical":
            vertical.append((stroke, stroke_bounds(stroke)))

    if len(horizontal) + len(vertical) > 120:
        return [], set()

    candidates = []
    for index, (top_stroke, top_box) in enumerate(horizontal):
        top_y = (top_box[1] + top_box[3]) / 2
        top_width = top_box[2] - top_box[0]
        if top_width < 35:
            continue
        for bottom_stroke, bottom_box in horizontal[index + 1:]:
            bottom_y = (bottom_box[1] + bottom_box[3]) / 2
            height = abs(bottom_y - top_y)
            if height < 25:
                continue
            upper, lower = (top_box, bottom_box) if top_y < bottom_y else (bottom_box, top_box)
            top_y2 = (upper[1] + upper[3]) / 2
            bottom_y2 = (lower[1] + lower[3]) / 2
            short_width = min(upper[2] - upper[0], lower[2] - lower[0])
            overlap = min(upper[2], lower[2]) - max(upper[0], lower[0])
            if short_width <= 0 or overlap / short_width < 0.78:
                continue
            left = (upper[0] + lower[0]) / 2
            right = (upper[2] + lower[2]) / 2
            width = right - left
            if width < 35:
                continue
            tolerance = max(8.0, min(18.0, min(width, height) * 0.09))
            side_candidates = []
            for x_expected in (left, right):
                matches = []
                for stroke, box in vertical:
                    cx = (box[0] + box[2]) / 2
                    span = min(bottom_y2, box[3]) - max(top_y2, box[1])
                    if (abs(cx - x_expected) <= tolerance and span >= height * 0.72
                            and box[1] <= top_y2 + tolerance and box[3] >= bottom_y2 - tolerance):
                        matches.append((abs(cx - x_expected), stroke, box))
                if not matches:
                    side_candidates = []
                    break
                side_candidates.append(min(matches, key=lambda item: item[0]))
            if len(side_candidates) != 2 or side_candidates[0][1].stroke_id == side_candidates[1][1].stroke_id:
                continue
            ids = {top_stroke.stroke_id, bottom_stroke.stroke_id,
                   side_candidates[0][1].stroke_id, side_candidates[1][1].stroke_id}
            element = UIElement("panel", left, top_y2, width, bottom_y2-top_y2,
                                confidence=0.56, alternatives=["button", "text_field"],
                                confirmed=False, source_stroke_ids=[top_stroke.stroke_id, bottom_stroke.stroke_id, side_candidates[0][1].stroke_id, side_candidates[1][1].stroke_id])
            candidates.append((width * height, element, ids))

    candidates.sort(key=lambda candidate: candidate[0], reverse=True)
    accepted = []
    for candidate in candidates:
        _, element, _ = candidate
        x1, y1, x2, y2 = element.x, element.y, element.x + element.width, element.y + element.height
        duplicate = False
        for _, existing, _ in accepted:
            ex1, ey1, ex2, ey2 = existing.x, existing.y, existing.x + existing.width, existing.y + existing.height
            intersection = max(0.0, min(x2, ex2) - max(x1, ex1)) * max(0.0, min(y2, ey2) - max(y1, ey1))
            smaller = min(element.width * element.height, existing.width * existing.height)
            if smaller > 0 and intersection / smaller >= 0.82:
                duplicate = True
                break
        if not duplicate:
            accepted.append(candidate)
    elements = [element for _, element, _ in accepted]
    used = set().union(*(ids for _, _, ids in accepted)) if accepted else set()
    return elements, used


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
    table_elements, table_stroke_ids = _detect_multistroke_tables(strokes)
    box_elements, box_stroke_ids = _detect_multistroke_rectangles(strokes, table_stroke_ids)
    elements: list[UIElement] = [*table_elements, *box_elements]
    used_strokes: set[str] = set(table_stroke_ids) | set(box_stroke_ids)

    for shape_stroke, _shape, shape_conf, bounds in sorted(rectangles, key=lambda item: ((item[3][2]-item[3][0])*(item[3][3]-item[3][1])), reverse=True):
        if shape_stroke.stroke_id in used_strokes:
            continue
        x1, y1, x2, y2 = bounds
        width, height = x2 - x1, y2 - y1
        nested = [item for item in rectangles
                  if item[0].stroke_id != shape_stroke.stroke_id
                  and _contains(bounds, item[3], margin=2)
                  and (item[3][2] - item[3][0]) * (item[3][3] - item[3][1]) < width * height * 0.95]
        nested_bounds = [item[3] for item in nested]
        contained = [s for s in strokes if len(s.points) >= 2 and s.stroke_id != shape_stroke.stroke_id
                     and s.stroke_id not in rectangle_ids
                     and s.stroke_id not in used_strokes
                     and _contains(bounds, stroke_bounds(s), margin=1)
                     and not any(_contains(inner, stroke_bounds(s), margin=0) for inner in nested_bounds)]
        rules = [s for s in contained if _horizontal_rule(s, bounds)]
        vertical_rules = [s for s in contained if _vertical_rule(s, bounds)]
        text = ""
        ocr_confidence = None
        element_type = "panel"
        confidence = 0.53
        alternatives: list[str] = ["button", "text_field", "table"]
        ratio = width / max(height, 1)

        if nested:
            element_type, confidence, alternatives = "panel", 0.86, ["panel", "button"]
        elif len(rules) >= 2 or len(vertical_rules) >= 2 or (rules and vertical_rules):
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
                ocr_confidence = _normalize_ocr_confidence(getattr(result, "confidence", None))
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

        if text:
            confidence = _limit_confidence_with_ocr(confidence, ocr_confidence)

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
            ocr_confidence = _normalize_ocr_confidence(getattr(result, "confidence", None))
            elements.append(UIElement(
                "label", min(xs), min(ys), max(24, max(xs)-min(xs)), max(18, max(ys)-min(ys)),
                text=text, confidence=_limit_confidence_with_ocr(0.84, ocr_confidence), alternatives=[], confirmed=False,
                source_stroke_ids=[s.stroke_id for s in group],
                ocr_confidence=ocr_confidence,
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
            # A closed oval is geometry, not automatically a radio control. Keeping
            # it as a transparent outline lets face details and other ink remain visible.
            elements.append(UIElement("ellipse", x1, y1, max(18, x2-x1), max(18, y2-y1), confidence=0.78,
                                       alternatives=["panel", "radio_button"], source_stroke_ids=[stroke.stroke_id]))

    # Unrecognized ink remains as editable artwork; do not invent a fake panel.
    return elements
