from __future__ import annotations

from PySide6.QtCore import Qt, QObject, QEvent, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget, QPushButton, QLineEdit, QLabel, QCheckBox, QComboBox, QTableWidget,
    QTableWidgetItem, QFrame, QRadioButton,
)

from ..models import DesignDocument, UIElement


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.document = DesignDocument()
        self.selected_id: str | None = None
        self._widgets: list[QWidget] = []
        self._scale = 1.0
        self._offset_x = 0
        self._offset_y = 0
        self.overlay = PreviewOverlay(self)
        self.setStyleSheet("background: white;")
        self.setMinimumSize(320, 240)

    def set_design(self, document: DesignDocument, selected_id: str | None) -> None:
        self.document = document
        self.selected_id = selected_id
        for widget in self._widgets:
            widget.removeEventFilter(self)
            if isinstance(widget, QTableWidget):
                widget.viewport().removeEventFilter(self)
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
                widget.viewport().installEventFilter(self)
                widget.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
            self._widgets.append(widget)
        self._relayout()
        self.overlay.setGeometry(self.rect())
        self.overlay.raise_()
        self.overlay.update()
        self.update()

    def _make_widget(self, element: UIElement) -> QWidget:
        t = element.element_type
        if t == "button":
            widget = QPushButton(element.text or "Button", self)
            widget.setStyleSheet("QPushButton { background:#2563EB; color:white; border:0; border-radius:5px; padding:4px 9px; }")
        elif t in ("text_field", "search_field"):
            widget = QLineEdit(self)
            widget.setPlaceholderText(element.placeholder or ("Search..." if t == "search_field" else "Enter text..."))
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
            widget = QTableWidget(3, 3, self)
            widget.setHorizontalHeaderLabels(["Column 1", "Column 2", "Column 3"])
            widget.setVerticalHeaderLabels(["1", "2", "3"])
            for r in range(3):
                for c in range(3):
                    widget.setItem(r, c, QTableWidgetItem(""))
            widget.setStyleSheet("QTableWidget { gridline-color:#D7DDE5; background:white; }")
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
        for widget in self._widgets:
            element = next((e for e in self.document.elements if e.element_id == widget.property("element_id")), None)
            if element is None:
                widget.hide()
                continue
            x = self._offset_x + int(element.x * self._scale)
            y = self._offset_y + int(element.y * self._scale)
            w = max(12, int(element.width * self._scale))
            h = max(12, int(element.height * self._scale))
            widget.setGeometry(x, y, w, h)
            widget.setVisible(True)
        self.overlay.setGeometry(self.rect())
        self.overlay.raise_()
        self.overlay.update()
        self.update()

    def resizeEvent(self, event):
        self._relayout()
        super().resizeEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            element_id = watched.property("element_id")
            if element_id:
                self.element_selected.emit(str(element_id))
                return True  # Preview is for selection, not for activating generated controls.
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
            if element.element_id == self.selected_id:
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
