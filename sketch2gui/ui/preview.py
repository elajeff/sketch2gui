from __future__ import annotations

from PySide6.QtCore import Qt, QObject, QEvent, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import (
    QWidget, QPushButton, QLineEdit, QLabel, QCheckBox, QComboBox, QTableWidget,
    QTableWidgetItem, QFrame, QRadioButton, QAbstractItemView,
)

from ..models import DesignDocument, UIElement


class _ChartPreviewWidget(QWidget):
    """Simple line chart driven by the values configured in Properties."""
    def __init__(self, values: list[float], parent=None):
        super().__init__(parent)
        self.values = list(values)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("white"))
        left, right = 8, max(9, self.width() - 8)
        top, bottom = 8, max(9, self.height() - 8)
        painter.setPen(QPen(QColor("#E2E8F0"), 1))
        for level in (1, 2, 3):
            y = top + (bottom - top) * level / 4
            painter.drawLine(left, int(y), right, int(y))
        painter.setPen(QPen(QColor("#64748B"), 1.2))
        painter.drawLine(left, top, left, bottom)
        painter.drawLine(left, bottom, right, bottom)
        if len(self.values) < 2:
            painter.setPen(QColor("#64748B"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Add 2+ values in Properties")
            return
        low, high = min(self.values), max(self.values)
        span = high - low or 1.0
        points = [(left + (right-left)*index/(len(self.values)-1), bottom - (value-low)/span*(bottom-top))
                  for index, value in enumerate(self.values)]
        painter.setPen(QPen(QColor("#2563EB"), 2.2))
        for first, second in zip(points, points[1:]):
            painter.drawLine(round(first[0]), round(first[1]), round(second[0]), round(second[1]))
        painter.setBrush(QColor("#2563EB"))
        for x, y in points:
            painter.drawEllipse(round(x)-2, round(y)-2, 4, 4)


class _EllipsePreviewWidget(QWidget):
    """Transparent outline so original strokes inside an oval remain visible."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#64748B"), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(self.rect().adjusted(1, 1, -1, -1))


class _StrokePreviewLayer(QWidget):
    """Paint original sketch strokes below the interactive preview widgets."""

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def paintEvent(self, event):
        document = self.owner.document
        scale = min(
            self.width() / max(document.width, 1),
            self.height() / max(document.height, 1),
        )
        if scale <= 0:
            return

        rendered_width = int(document.width * scale)
        rendered_height = int(document.height * scale)
        offset_x = max(0, (self.width() - rendered_width) // 2)
        offset_y = max(0, (self.height() - rendered_height) // 2)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.save()
        painter.translate(offset_x, offset_y)
        painter.scale(scale, scale)
        painter.setClipRect(0, 0, document.width, document.height)
        for stroke in document.strokes:
            if len(stroke.points) < 2:
                continue
            path = QPainterPath(QPointF(*stroke.points[0]))
            for point in stroke.points[1:]:
                path.lineTo(QPointF(*point))
            # Keep freehand strokes clearly visible in a small preview while
            # preserving their relative width on larger previews.
            display_minimum = 4.0 / scale
            pen_width = max(float(stroke.width), display_minimum)
            painter.setPen(QPen(
                QColor("#202938"), pen_width, Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin,
            ))
            painter.drawPath(path)
        painter.restore()


class PreviewOverlay(QWidget):
    """Paint editor-only selection and review marks above real preview widgets."""
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.owner.paint_editor_overlays(painter)


class PreviewSurface(QWidget):
    element_selected = Signal(object)
    text_edit_finished = Signal(str, str)
    table_cell_changed = Signal(str, int, int, str)
    selection_toggled = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.document = DesignDocument()
        self.selected_id: str | None = None
        self.selected_ids: set[str] = set()
        self._widgets: list[QWidget] = []
        self._editing_widget: QLineEdit | None = None
        self._editing_original = ""
        self._scale = 1.0
        self._offset_x = 0
        self._offset_y = 0
        self._stroke_layer = _StrokePreviewLayer(self)
        self.overlay = PreviewOverlay(self)
        self.setStyleSheet("background: white;")
        self.setMinimumSize(320, 240)

    def set_design(self, document: DesignDocument, selected_id: str | None) -> None:
        self.document = document
        self.selected_id = selected_id
        self._editing_widget = None
        for widget in self._widgets:
            widget.removeEventFilter(self)
            if isinstance(widget, QTableWidget):
                widget.viewport().removeEventFilter(self)
            widget.hide()
            widget.deleteLater()
        self._widgets.clear()
        ordered = sorted(enumerate(document.elements), key=lambda pair: (pair[1].element_type != "panel", pair[1].y, pair[1].x, pair[0]))
        for _, element in ordered:
            widget = self._make_widget(element)
            widget.setProperty("element_id", element.element_id)
            widget.installEventFilter(self)
            widget.setCursor(Qt.CursorShape.PointingHandCursor)
            if isinstance(widget, QTableWidget):
                # Intercept table-body clicks for selection but leave the headers and scrollbars usable.
                widget.viewport().setProperty("element_id", element.element_id)
                widget.viewport().setProperty("is_table_viewport", True)
                widget.viewport().installEventFilter(self)
                widget.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
                widget.cellChanged.connect(
                    lambda row, column, element_id=element.element_id, table=widget:
                    self.table_cell_changed.emit(
                        element_id, row, column,
                        table.item(row, column).text() if table.item(row, column) else "",
                    )
                )
            self._widgets.append(widget)
        self._relayout()
        self.overlay.setGeometry(self.rect())
        self.overlay.raise_()
        self.overlay.update()
        self.update()

    def update_strokes(self) -> None:
        """Redraw original ink without rebuilding the interactive component widgets."""
        self._stroke_layer.update()
        self.update()

    def set_selected(self, selected_id: str | None) -> None:
        # Selection must not rebuild controls: doing so would interrupt inline text editing.
        self.selected_id = selected_id
        self.overlay.update()
        self.update()

    def set_selected_many(self, element_ids, primary: str | None = None) -> None:
        self.selected_ids = set(element_ids or ())
        self.selected_id = primary if primary in self.selected_ids else next(iter(self.selected_ids), None)
        self.overlay.update()
        self.update()

    def _make_widget(self, element: UIElement) -> QWidget:
        t = element.element_type
        if t == "button":
            widget = QPushButton(element.text or "Button", self)
            widget.setStyleSheet("QPushButton { background:#2563EB; color:white; border:0; border-radius:5px; padding:4px 9px; }")
        elif t in ("text_field", "search_field"):
            widget = QLineEdit(self)
            widget.setText(element.text)
            widget.setPlaceholderText(element.placeholder or ("Search..." if t == "search_field" else "Enter text..."))
            widget.setReadOnly(True)
            widget.editingFinished.connect(lambda current=widget: self._finish_inline_edit(current))
            widget.setStyleSheet("QLineEdit { border:1px solid #B8C1CF; border-radius:5px; padding:4px 8px; background:white; color:#172033; }")
        elif t == "label":
            widget = QLabel(element.text or "Label", self)
            widget.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            widget.setStyleSheet("color:#172033; background:transparent;")
        elif t == "checkbox":
            widget = QCheckBox(element.text or "Option", self)
        elif t == "dropdown":
            widget = QComboBox(self)
            widget.addItems(["Choose...", "Option 1", "Option 2"])
        elif t == "table":
            widget = QTableWidget(element.table_rows, element.table_columns, self)
            widget.setHorizontalHeaderLabels([f"Column {index + 1}" for index in range(element.table_columns)])
            widget.setVerticalHeaderLabels([str(index + 1) for index in range(element.table_rows)])
            for row in range(element.table_rows):
                for column in range(element.table_columns):
                    value = element.table_cells[row][column] if row < len(element.table_cells) and column < len(element.table_cells[row]) else ""
                    widget.setItem(row, column, QTableWidgetItem(value))
            widget.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed | QAbstractItemView.EditTrigger.AnyKeyPressed)
            widget.setStyleSheet("QTableWidget { gridline-color:#D7DDE5; background:white; }")
        elif t == "chart":
            widget = _ChartPreviewWidget(element.chart_values, self)
        elif t == "ellipse":
            widget = _EllipsePreviewWidget(self)
        elif t == "panel":
            widget = QFrame(self)
            widget.setFrameShape(QFrame.Shape.StyledPanel)
            widget.setStyleSheet("QFrame { border:1px solid #B8C1CF; border-radius:4px; background:rgba(242,245,249,90); }")
        elif t == "radio_button":
            widget = QRadioButton(element.text or "Option", self)
        else:  # line
            widget = QFrame(self)
            widget.setFrameShape(QFrame.Shape.VLine if element.height > element.width else QFrame.Shape.HLine)
            widget.setStyleSheet("QFrame { color:#9AA5B5; }")
        return widget

    def _relayout(self) -> None:
        sx = self.width() / max(self.document.width, 1)
        sy = self.height() / max(self.document.height, 1)
        self._scale = min(sx, sy)
        # Preserve the sketch's aspect ratio and center it in the preview surface.
        rendered_w = int(self.document.width * self._scale)
        rendered_h = int(self.document.height * self._scale)
        self._offset_x = max(0, (self.width() - rendered_w) // 2)
        self._offset_y = max(0, (self.height() - rendered_h) // 2)
        elements_by_id = {element.element_id: element for element in self.document.elements}
        for widget in self._widgets:
            element = elements_by_id.get(widget.property("element_id"))
            if element is None:
                widget.hide()
                continue
            x = self._offset_x + int(element.x * self._scale)
            y = self._offset_y + int(element.y * self._scale)
            w = max(12, int(element.width * self._scale))
            h = max(12, int(element.height * self._scale))
            widget.setGeometry(x, y, w, h)
            widget.setVisible(True)
        self._stroke_layer.setGeometry(self.rect())
        self._stroke_layer.lower()
        self._stroke_layer.update()
        self.overlay.setGeometry(self.rect())
        self.overlay.raise_()
        self.overlay.update()
        self.update()

    def resizeEvent(self, event):
        self._relayout()
        super().resizeEvent(event)

    def _finish_inline_edit(self, widget: QLineEdit) -> None:
        if self._editing_widget is not widget:
            return
        element_id = str(widget.property("element_id") or "")
        original = self._editing_original
        updated = widget.text()
        self._editing_widget = None
        widget.setReadOnly(True)
        if element_id and updated != original:
            self.text_edit_finished.emit(element_id, updated)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            element_id = watched.property("element_id")
            if element_id:
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self.selection_toggled.emit(str(element_id))
                else:
                    if self._editing_widget is not None and self._editing_widget is not watched:
                        self._finish_inline_edit(self._editing_widget)
                    self.element_selected.emit(str(element_id))
                if isinstance(watched, QLineEdit):
                    if self._editing_widget is not watched:
                        self._editing_widget = watched
                        self._editing_original = watched.text()
                    watched.setReadOnly(False)
                    watched.setFocus(Qt.FocusReason.MouseFocusReason)
                    return False
                if isinstance(watched, QTableWidget) or watched.property("is_table_viewport"):
                    return False
                return True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):
        self.element_selected.emit(None)
        super().mousePressEvent(event)

    def paint_editor_overlays(self, painter: QPainter) -> None:
        sx = self.width() / max(self.document.width, 1)
        sy = self.height() / max(self.document.height, 1)
        scale = min(sx, sy)
        rendered_w = int(self.document.width * scale)
        rendered_h = int(self.document.height * scale)
        offset_x = max(0, (self.width() - rendered_w) // 2)
        offset_y = max(0, (self.height() - rendered_h) // 2)
        for element in self.document.elements:
            x = offset_x + int(element.x * scale)
            y = offset_y + int(element.y * scale)
            w = int(element.width * scale)
            h = int(element.height * scale)
            if element.element_id == self.selected_id or element.element_id in self.selected_ids:
                painter.setPen(QPen(QColor("#2563EB"), 2, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(x - 3, y - 3, w + 6, h + 6, 5, 5)
            if element.needs_review:
                painter.setPen(QPen(Qt.PenStyle.NoPen))
                painter.setBrush(QColor("#D99A31"))
                painter.drawEllipse(x + w - 7, y - 4, 8, 8)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#F7F8FA"))
        sx = self.width() / max(self.document.width, 1)
        sy = self.height() / max(self.document.height, 1)
        scale = min(sx, sy)
        rendered_w = int(self.document.width * scale)
        rendered_h = int(self.document.height * scale)
        offset_x = max(0, (self.width() - rendered_w) // 2)
        offset_y = max(0, (self.height() - rendered_h) // 2)
        painter.fillRect(offset_x, offset_y, rendered_w, rendered_h, QColor("white"))
