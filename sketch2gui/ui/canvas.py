from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QFont
from PySide6.QtWidgets import QWidget

from ..models import DesignDocument, Stroke


class DrawingCanvas(QWidget):
    stroke_added = Signal(object)
    element_selected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 260)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.document = DesignDocument()
        self.selected_id: str | None = None
        self.drawing_enabled = True
        self._current_points: list[tuple[float, float]] = []
        self._dragged = False

    def set_document(self, document: DesignDocument) -> None:
        self.document = document
        self.update()

    def set_selected(self, element_id: str | None) -> None:
        self.selected_id = element_id
        self.update()

    def _canvas_transform(self) -> tuple[float, float, float]:
        scale = min(
            self.width() / max(self.document.width, 1),
            self.height() / max(self.document.height, 1),
        )
        offset_x = (self.width() - self.document.width * scale) / 2
        offset_y = (self.height() - self.document.height * scale) / 2
        return scale, offset_x, offset_y

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.drawing_enabled:
            return super().mousePressEvent(event)
        pos = event.position()
        scale, offset_x, offset_y = self._canvas_transform()
        point = ((pos.x() - offset_x) / scale, (pos.y() - offset_y) / scale)
        if not (0 <= point[0] <= self.document.width and 0 <= point[1] <= self.document.height):
            self.element_selected.emit(None)
            self._current_points = []
            self.update()
            return super().mousePressEvent(event)
        # A click selects an existing component; dragging from that position can
        # still start a new freehand stroke (for example, a label inside a field).
        # Strokes are emitted only after the pointer has moved meaningfully, so a
        # simple selection click does not add a stray dot to the drawing.
        selected_element = None
        for element in reversed(self.document.elements):
            if element.x <= point[0] <= element.x + element.width and element.y <= point[1] <= element.y + element.height:
                selected_element = element
                break
        self.element_selected.emit(selected_element.element_id if selected_element else None)
        self._current_points = [point]
        self._dragged = False
        self.update()

    def mouseMoveEvent(self, event):
        if self._current_points and event.buttons() & Qt.MouseButton.LeftButton and self.drawing_enabled:
            pos = event.position()
            scale, offset_x, offset_y = self._canvas_transform()
            point = (
                min(float(self.document.width), max(0.0, (pos.x() - offset_x) / scale)),
                min(float(self.document.height), max(0.0, (pos.y() - offset_y) / scale)),
            )
            if not self._current_points or (abs(point[0]-self._current_points[-1][0]) + abs(point[1]-self._current_points[-1][1]) >= 1.5):
                self._current_points.append(point)
                start_x, start_y = self._current_points[0]
                self._dragged = self._dragged or math.hypot(point[0] - start_x, point[1] - start_y) >= 4.0
                self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
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
        scale, offset_x, offset_y = self._canvas_transform()
        painter.save()
        painter.translate(offset_x, offset_y)
        painter.scale(scale, scale)
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
        # Low-confidence marks are subtle: a small amber dot, never flashing.
        for element in self.document.elements:
            if element.element_id == self.selected_id:
                painter.setPen(QPen(QColor("#2563EB"), 2, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(int(element.x), int(element.y), int(element.width), int(element.height), 4, 4)
            if element.needs_review:
                painter.setPen(QPen(Qt.PenStyle.NoPen))
                painter.setBrush(QColor("#D99A31"))
                painter.drawEllipse(QPointF(element.x + element.width - 8, element.y + 8), 4, 4)
        painter.restore()
        painter.setPen(QColor("#687386"))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(10, self.height() - 10, "Draw freely · close a shape to suggest a component · click to select, drag to add strokes anywhere")
