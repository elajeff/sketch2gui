from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QFont
from PySide6.QtWidgets import QWidget

from ..models import DesignDocument, Stroke, UIElement


DRAWING_FOOTER_HEIGHT = 28
DRAW_TOOL_NAMES = {
    "freehand": "Freehand",
    "select": "Select",
    "panel": "Box",
    "button": "Button",
    "text_field": "Text field",
    "label": "Label",
    "table": "Table",
    "chart": "Chart",
    "ellipse": "Ellipse",
    "line": "Line",
}


class DrawingCanvas(QWidget):
    stroke_added = Signal(object)
    element_added = Signal(object)
    element_selected = Signal(object)
    selection_toggled = Signal(object)
    element_geometry_changed = Signal(str, float, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 260)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.document = DesignDocument()
        self.selected_id: str | None = None
        self.selected_ids: set[str] = set()
        self.drawing_enabled = True
        self._current_points: list[tuple[float, float]] = []
        self._dragged = False
        self.active_tool = "freehand"
        self.snap_enabled = True
        self._component_drag_id: str | None = None
        self._component_drag_mode: str | None = None
        self._component_drag_start: tuple[float, float] | None = None
        self._component_drag_bounds: tuple[float, float, float, float] | None = None
        self._component_drag_current: tuple[float, float, float, float] | None = None
        self._component_dragged = False
        self._shape_start: tuple[float, float] | None = None
        self._shape_end: tuple[float, float] | None = None
        self._drag_tool: str | None = None

    def set_tool(self, tool: str) -> None:
        if tool not in DRAW_TOOL_NAMES:
            raise ValueError(f"Unsupported drawing tool: {tool}")
        self.active_tool = tool
        self._current_points = []
        self._shape_start = None
        self._shape_end = None
        self._drag_tool = None
        self.update()

    def set_selected_many(self, element_ids, primary: str | None = None) -> None:
        self.selected_ids = set(element_ids or ())
        self.selected_id = primary if primary in self.selected_ids else next(iter(self.selected_ids), None)
        self.update()

    def _snap_value(self, value: float) -> float:
        return round(value / 10.0) * 10.0 if self.snap_enabled else value

    def _widget_to_document(self, pos, *, clamp: bool = False) -> tuple[float, float]:
        scale_x, scale_y, offset_x, offset_y = self._canvas_transform()
        x = (float(pos.x()) - offset_x) / max(scale_x, 1e-9)
        y = (float(pos.y()) - offset_y) / max(scale_y, 1e-9)
        if clamp:
            x = min(float(self.document.width), max(0.0, x))
            y = min(float(self.document.height), max(0.0, y))
        return x, y

    def set_document(self, document: DesignDocument) -> None:
        self.document = document
        self.update()

    def _drawing_height(self) -> int:
        """Height of the drawable region, leaving the instruction footer clear."""
        return max(1, self.height() - DRAWING_FOOTER_HEIGHT)

    def _canvas_transform(self) -> tuple[float, float, float, float]:
        """Map document coordinates to the full drawable area as it is resized."""
        scale_x = self.width() / max(self.document.width, 1)
        scale_y = self._drawing_height() / max(self.document.height, 1)
        return scale_x, scale_y, 0.0, 0.0

    def _element_at(self, point: tuple[float, float]) -> UIElement | None:
        """Return the topmost component containing a document-space point."""
        x, y = point
        return next(
            (element for element in reversed(self.document.elements)
             if element.x <= x <= element.x + element.width
             and element.y <= y <= element.y + element.height),
            None,
        )

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.drawing_enabled:
            return super().mousePressEvent(event)
        pos = event.position()
        if pos.y() >= self._drawing_height():
            self.element_selected.emit(None)
            return super().mousePressEvent(event)
        point = self._widget_to_document(pos)
        if not (0 <= point[0] <= self.document.width and 0 <= point[1] < self.document.height):
            self.element_selected.emit(None)
            self._current_points = []
            self.update()
            return super().mousePressEvent(event)

        if self.active_tool == "select":
            hit = self._element_at(point)
            if hit is None:
                # Rounded widget coordinates can land just outside a corner.
                # Keep resize handles usable at those edges without making the
                # entire component hit box unnecessarily larger.
                resize_handle_tolerance = 12.0
                for element in reversed(self.document.elements):
                    corners = (
                        (element.x, element.y),
                        (element.x + element.width, element.y),
                        (element.x, element.y + element.height),
                        (element.x + element.width, element.y + element.height),
                    )
                    if any(
                        math.hypot(point[0] - cx, point[1] - cy) <= resize_handle_tolerance
                        for cx, cy in corners
                    ):
                        hit = element
                        break
            modifiers = event.modifiers()
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                self.selection_toggled.emit(hit.element_id if hit else None)
                return super().mousePressEvent(event)
            self.element_selected.emit(hit.element_id if hit else None)
            self._component_drag_id = None
            self._component_drag_mode = None
            self._component_drag_start = None
            self._component_drag_bounds = None
            self._component_drag_current = None
            self._component_dragged = False
            if hit is not None:
                self._component_drag_id = hit.element_id
                self._component_drag_start = point
                self._component_drag_bounds = (hit.x, hit.y, hit.width, hit.height)
                self._component_drag_current = self._component_drag_bounds
                x, y, w, h = hit.x, hit.y, hit.width, hit.height
                corners = {
                    "resize-tl": (x, y), "resize-tr": (x+w, y),
                    "resize-bl": (x, y+h), "resize-br": (x+w, y+h),
                }
                close_corner = min(corners, key=lambda key: math.hypot(point[0]-corners[key][0], point[1]-corners[key][1]))
                self._component_drag_mode = close_corner if math.hypot(point[0]-corners[close_corner][0], point[1]-corners[close_corner][1]) <= 12 else "move"
            self.update()
            return super().mousePressEvent(event)

        if self.active_tool != "freehand":
            self.element_selected.emit(None)
            self._shape_start = point
            self._shape_end = point
            self._drag_tool = self.active_tool
            self.update()
            return

        selected_element = self._element_at(point)
        self.element_selected.emit(selected_element.element_id if selected_element else None)
        self._current_points = [point]
        self._dragged = False
        self.update()

    def _update_component_drag(self, point: tuple[float, float]) -> None:
        """Apply a drag position once, including the final mouse-release position."""
        if not (
            self._component_drag_id
            and self._component_drag_start
            and self._component_drag_bounds
            and self._component_drag_mode
        ):
            return

        sx, sy = self._component_drag_start
        x, y, w, h = self._component_drag_bounds
        dx, dy = point[0] - sx, point[1] - sy
        mode = self._component_drag_mode
        if mode == "move":
            bounds = (x + dx, y + dy, w, h)
        else:
            left, top, right, bottom = x, y, x + w, y + h
            resize_left = mode in ("resize-tl", "resize-bl")
            resize_right = mode in ("resize-tr", "resize-br")
            resize_top = mode in ("resize-tl", "resize-tr")
            resize_bottom = mode in ("resize-bl", "resize-br")
            if resize_left:
                left = min(x + dx, right - 8)
            if resize_right:
                right = max(x + w + dx, left + 8)
            if resize_top:
                top = min(y + dy, bottom - 8)
            if resize_bottom:
                bottom = max(y + h + dy, top + 8)
            bounds = (left, top, right - left, bottom - top)
        self._component_drag_current = bounds
        self._component_dragged = self._component_dragged or math.hypot(dx, dy) >= 2
        self.update()

    def mouseMoveEvent(self, event):
        interaction_active = (
            self._component_drag_id is not None
            or (self._shape_start is not None and self._drag_tool is not None)
            or bool(self._current_points)
        )
        if self.drawing_enabled and interaction_active:
            pos = event.position()
            point = self._widget_to_document(pos, clamp=True)
            if self._component_drag_id and self._component_drag_start and self._component_drag_bounds and self._component_drag_mode:
                self._update_component_drag(point)
                return super().mouseMoveEvent(event)
            if self._shape_start is not None and self._drag_tool:
                self._shape_end = point
                self.update()
                return super().mouseMoveEvent(event)
            if self._current_points:
                if abs(point[0] - self._current_points[-1][0]) + abs(point[1] - self._current_points[-1][1]) >= 1.5:
                    self._current_points.append(point)
                    start_x, start_y = self._current_points[0]
                    self._dragged = self._dragged or math.hypot(point[0] - start_x, point[1] - start_y) >= 4.0
                    self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # Mouse release can be the only event carrying the final drag position.
        if event.button() == Qt.MouseButton.LeftButton and self.drawing_enabled:
            release_position = self._widget_to_document(event.position(), clamp=True)
            if self._component_drag_id:
                self._update_component_drag(release_position)
            if self._shape_start is not None and self._drag_tool:
                self._shape_end = release_position

        # Qt may deliver a release at a new position without an intermediate move event.
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.active_tool == "freehand"
            and self._current_points
            and event.position().y() < self._drawing_height()
        ):
            release_point = self._widget_to_document(event.position(), clamp=True)
            last_x, last_y = self._current_points[-1]
            if math.hypot(release_point[0] - last_x, release_point[1] - last_y) >= 1.0:
                self._current_points.append(release_point)

            # Do not rely on mouseMoveEvent to recognise a drag.
            start_x, start_y = self._current_points[0]
            self._dragged = self._dragged or (
                math.hypot(release_point[0] - start_x, release_point[1] - start_y) >= 4.0
            )

        if event.button() == Qt.MouseButton.LeftButton and self._component_drag_id:
            element_id = self._component_drag_id
            bounds = self._component_drag_current
            moved = self._component_dragged
            self._component_drag_id = None
            self._component_drag_mode = None
            self._component_drag_start = None
            self._component_drag_bounds = None
            self._component_drag_current = None
            self._component_dragged = False
            if moved and bounds:
                x, y, width, height = bounds
                if self.snap_enabled:
                    x, y, width, height = (self._snap_value(v) for v in (x, y, width, height))
                    width, height = max(8.0, width), max(8.0, height)
                x = min(max(0.0, x), max(0.0, self.document.width-width))
                y = min(max(0.0, y), max(0.0, self.document.height-height))
                width = min(width, float(self.document.width)-x)
                height = min(height, float(self.document.height)-y)
                self.element_geometry_changed.emit(element_id, x, y, width, height)
            self.update()
            return super().mouseReleaseEvent(event)

        if event.button() == Qt.MouseButton.LeftButton and self._shape_start is not None and self._drag_tool:
            start = self._shape_start
            end = self._shape_end or start
            tool = self._drag_tool
            self._shape_start = None
            self._shape_end = None
            self._drag_tool = None
            if self.snap_enabled:
                start = (self._snap_value(start[0]), self._snap_value(start[1]))
                end = (self._snap_value(end[0]), self._snap_value(end[1]))
            x, y = min(start[0], end[0]), min(start[1], end[1])
            width, height = abs(end[0] - start[0]), abs(end[1] - start[1])
            if tool == "line":
                dx, dy = end[0] - start[0], end[1] - start[1]
                if math.hypot(dx, dy) >= 18:
                    if abs(dx) >= abs(dy):
                        line_x, line_y = min(start[0], end[0]), (start[1] + end[1]) / 2
                        line_width, line_height = max(8.0, abs(dx)), 8.0
                    else:
                        line_x, line_y = (start[0] + end[0]) / 2, min(start[1], end[1])
                        line_width, line_height = 8.0, max(8.0, abs(dy))
                    self.element_added.emit(UIElement(
                        "line", line_x, line_y, line_width, line_height,
                        confidence=1.0, confirmed=True, user_modified=True,
                    ))
                self.update()
                return super().mouseReleaseEvent(event)

            min_width, min_height = (50, 40) if tool in ("table", "chart") else (18, 16)
            if width >= min_width and height >= min_height:
                defaults = {
                    "button": {"text": "Button"},
                    "text_field": {"placeholder": "Enter text..."},
                    "label": {"text": "Label"},
                }
                element = UIElement(
                    tool, x, y, width, height,
                    text=defaults.get(tool, {}).get("text", ""),
                    placeholder=defaults.get(tool, {}).get("placeholder", ""),
                    confidence=1.0, confirmed=True, user_modified=True,
                )
                self.element_added.emit(element)
            self.update()
            return super().mouseReleaseEvent(event)

        if event.button() == Qt.MouseButton.LeftButton and self._current_points:
            if len(self._current_points) >= 2 and self._dragged:
                self.stroke_added.emit(Stroke(points=list(self._current_points)))
            self._current_points = []
            self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale_x, scale_y, offset_x, offset_y = self._canvas_transform()
        painter.save()
        painter.translate(offset_x, offset_y)
        painter.scale(scale_x, scale_y)
        painter.setClipRect(0, 0, self.document.width, self.document.height)
        grid_pen = QPen(QColor("#EEF1F5"), 1)
        painter.setPen(grid_pen)
        for x in range(0, self.document.width, 25):
            painter.drawLine(x, 0, x, self.document.height)
        for y in range(0, self.document.height, 25):
            painter.drawLine(0, y, self.document.width, y)
        # Original strokes remain visible as the provenance of recognition.
        pen = QPen(QColor("#202938"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        for stroke in self.document.strokes:
            if not stroke.points:
                continue
            path = QPainterPath(QPointF(*stroke.points[0]))
            for point in stroke.points[1:]:
                path.lineTo(QPointF(*point))
            pen.setWidthF(stroke.width)
            painter.setPen(pen)
            painter.drawPath(path)
        if self._current_points:
            path = QPainterPath(QPointF(*self._current_points[0]))
            for point in self._current_points[1:]:
                path.lineTo(QPointF(*point))
            painter.setPen(QPen(QColor("#2563EB"), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(path)
        if self._shape_start is not None and self._shape_end is not None:
            x1, y1 = self._shape_start
            x2, y2 = self._shape_end
            painter.setPen(QPen(QColor("#2563EB"), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if self._drag_tool == "line":
                if abs(x2 - x1) >= abs(y2 - y1):
                    middle_y = (y1 + y2) / 2
                    painter.drawLine(int(min(x1, x2)), int(middle_y), int(max(x1, x2)), int(middle_y))
                else:
                    middle_x = (x1 + x2) / 2
                    painter.drawLine(int(middle_x), int(min(y1, y2)), int(middle_x), int(max(y1, y2)))
            else:
                painter.drawRect(int(min(x1, x2)), int(min(y1, y2)), int(abs(x2-x1)), int(abs(y2-y1)))

        # Tool-created components are explicit model objects, not approximate ink.
        for element in self.document.elements:
            if element.source_stroke_ids:
                continue
            x, y, w, h = element.x, element.y, element.width, element.height
            painter.setPen(QPen(QColor("#2563EB" if element.element_id == self.selected_id else "#5B6473"), 2 if element.element_id == self.selected_id else 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if element.element_type == "ellipse":
                painter.drawEllipse(int(x), int(y), int(w), int(h))
            elif element.element_type == "chart":
                painter.drawRect(int(x), int(y), int(w), int(h))
                for level in range(1, 4):
                    yy = y + h * level / 4
                    painter.drawLine(int(x + 8), int(yy), int(x + w - 8), int(yy))
                if len(element.chart_values) < 2:
                    painter.setPen(QColor("#64748B"))
                    painter.drawText(int(x + 4), int(y + 4), max(1, int(w - 8)), max(1, int(h - 8)), Qt.AlignmentFlag.AlignCenter, "Add values in Properties")
                else:
                    magnitude = max(abs(value) for value in element.chart_values) or 1.0
                    values = [value / magnitude for value in element.chart_values]
                    low, high = min(values), max(values)
                    span = high - low or 1.0
                    pts = [(x + w * 0.10 + (w * 0.80) * index / (len(values) - 1),
                            y + h * 0.90 - ((value - low) / span) * (h * 0.75))
                           for index, value in enumerate(values)]
                    painter.setPen(QPen(QColor("#2563EB"), 2.2))
                    for first, second in zip(pts, pts[1:]):
                        painter.drawLine(int(first[0]), int(first[1]), int(second[0]), int(second[1]))
                    painter.setBrush(QColor("#2563EB"))
                    for px, py in pts:
                        painter.drawEllipse(int(px)-2, int(py)-2, 4, 4)
            elif element.element_type == "table":
                painter.drawRect(int(x), int(y), int(w), int(h))
                for col in (1, 2):
                    painter.drawLine(int(x+w*col/3), int(y), int(x+w*col/3), int(y+h))
                for row in (1, 2):
                    painter.drawLine(int(x), int(y+h*row/3), int(x+w), int(y+h*row/3))
            elif element.element_type == "button":
                painter.drawRoundedRect(int(x), int(y), int(w), int(h), 5, 5)
                painter.drawText(int(x), int(y), int(w), int(h), Qt.AlignmentFlag.AlignCenter, element.text or "Button")
            elif element.element_type == "text_field":
                painter.drawRoundedRect(int(x), int(y), int(w), int(h), 4, 4)
                painter.drawText(int(x+8), int(y), max(0, int(w-16)), int(h), Qt.AlignmentFlag.AlignVCenter, element.placeholder or "Enter text...")
            elif element.element_type == "panel":
                painter.drawRect(int(x), int(y), int(w), int(h))
            elif element.element_type == "label":
                painter.setPen(QColor("#202938"))
                painter.drawText(int(x), int(y), int(w), int(h), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, element.text or "Label")
            elif element.element_type == "line":
                if h > w:
                    painter.drawLine(int(x+w/2), int(y), int(x+w/2), int(y+h))
                else:
                    painter.drawLine(int(x), int(y+h/2), int(x+w), int(y+h/2))
        if self._component_drag_current is not None:
            x, y, width, height = self._component_drag_current
            painter.setPen(QPen(QColor("#2563EB"), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(int(x), int(y), int(width), int(height))

        # Low-confidence marks are subtle: a small amber dot, never flashing.
        for element in self.document.elements:
            if element.element_id == self.selected_id or element.element_id in self.selected_ids:
                painter.setPen(QPen(QColor("#2563EB"), 2, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(int(element.x), int(element.y), int(element.width), int(element.height), 4, 4)
                if self.active_tool == "select":
                    painter.setPen(QPen(QColor("#2563EB"), 1))
                    painter.setBrush(QColor("white"))
                    for hx, hy in ((element.x, element.y), (element.x+element.width, element.y),
                                   (element.x, element.y+element.height), (element.x+element.width, element.y+element.height)):
                        painter.drawRect(int(hx)-4, int(hy)-4, 8, 8)
            if element.needs_review:
                painter.setPen(QPen(Qt.PenStyle.NoPen))
                painter.setBrush(QColor("#D99A31"))
                painter.drawEllipse(QPointF(element.x + element.width - 8, element.y + 8), 4, 4)
        painter.restore()
        footer_top = self._drawing_height()
        painter.fillRect(0, footer_top, self.width(), self.height() - footer_top, QColor("#FFFFFF"))
        painter.setPen(QPen(QColor("#E5E7EB"), 1))
        painter.drawLine(0, footer_top, self.width(), footer_top)
        painter.setPen(QColor("#687386"))
        painter.setFont(QFont("Segoe UI", 9))
        hints = {
            "freehand": "Freehand: draw anything · strokes also appear in the preview",
            "panel": "Drag to place a box",
            "button": "Drag to place a button",
            "text_field": "Drag to place a text field",
            "table": "Drag to place a table",
            "chart": "Drag to place a chart",
            "ellipse": "Drag to place an ellipse",
            "line": "Drag to place a horizontal or vertical line",
        }
        painter.drawText(10, self.height() - 10, hints.get(self.active_tool, "Draw on the canvas"))
