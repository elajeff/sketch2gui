"""Readable, deterministic Python source generation from the shared model."""
from __future__ import annotations

import keyword
import re

from .models import DesignDocument, Stroke, UIElement


def _safe_identifier(value: str, fallback: str) -> str:
    cleaned = re.sub(r"\W+", "_", value).strip("_")
    if not cleaned or cleaned[0].isdigit() or keyword.iskeyword(cleaned):
        cleaned = fallback
    return cleaned


def _format_stroke_assignment(strokes: list[Stroke]) -> list[str]:
    """Format stroke coordinates readably in generated Python source."""
    if not strokes:
        return ["        self._sketch_strokes = []"]

    lines = ["        self._sketch_strokes = ["]
    for stroke in strokes:
        lines.extend(["            (", "                ["])
        for offset in range(0, len(stroke.points), 2):
            points = stroke.points[offset:offset + 2]
            rendered_points = ", ".join(
                f"({x!r}, {y!r})" for x, y in points
            )
            lines.append(f"                    {rendered_points},")
        lines.extend([
            "                ],",
            f"                {float(stroke.width)!r},",
            "            ),",
        ])
    lines.append("        ]")
    return lines


def generate_python(document: DesignDocument, class_name: str = "GeneratedWindow") -> str:
    """Generate a standalone PySide6 QWidget program using absolute coordinates."""
    class_name = _safe_identifier(class_name, "GeneratedWindow")
    class_name = "".join(part[:1].upper() + part[1:] for part in class_name.split("_")) or "GeneratedWindow"
    element_types = {element.element_type for element in document.elements}
    has_strokes = bool(document.strokes)
    has_chart = "chart" in element_types
    has_ellipse = "ellipse" in element_types
    needs_qt = has_strokes or has_chart or has_ellipse

    imports = ["import sys"]
    if needs_qt:
        core_names = (["QPointF"] if has_strokes else []) + ["Qt"]
        imports.append(f"from PySide6.QtCore import {', '.join(core_names)}")
    gui_names = ["QColor", "QPainter"]
    if has_strokes:
        gui_names.extend(("QPainterPath", "QPen"))
    elif needs_qt:
        gui_names.append("QPen")
    imports.append(f"from PySide6.QtGui import {', '.join(gui_names)}")

    widget_imports = ["QApplication", "QWidget"]
    for element_type, names in (
        ("button", ("QPushButton",)),
        ("text_field", ("QLineEdit",)),
        ("search_field", ("QLineEdit",)),
        ("label", ("QLabel",)),
        ("checkbox", ("QCheckBox",)),
        ("dropdown", ("QComboBox",)),
        ("table", ("QTableWidget", "QTableWidgetItem")),
        ("panel", ("QFrame",)),
        ("line", ("QFrame",)),
        ("radio_button", ("QRadioButton",)),
    ):
        if element_type in element_types:
            for name in names:
                if name not in widget_imports:
                    widget_imports.append(name)
    if widget_imports:
        imports.extend(["from PySide6.QtWidgets import (", *(f"    {name}," for name in widget_imports), ")"])
    imports.extend(("", ""))

    helper_classes: list[str] = []
    if has_chart:
        helper_classes.extend([
            "class ChartWidget(QWidget):",
            "    def __init__(self, values, parent=None):",
            "        super().__init__(parent)",
            "        self.values = list(values)",
            "",
            "    def paintEvent(self, event):",
            "        painter = QPainter(self)",
            "        painter.setRenderHint(QPainter.RenderHint.Antialiasing)",
            "        painter.fillRect(self.rect(), QColor('white'))",
            "        left, right = 8, max(9, self.width() - 8)",
            "        top, bottom = 8, max(9, self.height() - 8)",
            "        painter.setPen(QPen(QColor('#E2E8F0'), 1))",
            "        for level in (1, 2, 3):",
            "            y = top + (bottom - top) * level / 4",
            "            painter.drawLine(left, int(y), right, int(y))",
            "        painter.setPen(QPen(QColor('#64748B'), 1.2))",
            "        painter.drawLine(left, top, left, bottom)",
            "        painter.drawLine(left, bottom, right, bottom)",
            "        if len(self.values) < 2:",
            "            painter.setPen(QColor('#64748B'))",
            "            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Add 2+ values in Properties')",
            "            return",
            "        magnitude = max((abs(value) for value in self.values), default=0.0) or 1.0",
            "        values = [value / magnitude for value in self.values]",
            "        low, high = min(values), max(values)",
            "        span = high - low or 1.0",
            "        points = [",
            "            (left + (right - left) * index / (len(values) - 1),",
            "             bottom - (value - low) / span * (bottom - top))",
            "            for index, value in enumerate(values)",
            "        ]",
            "        painter.setPen(QPen(QColor('#2563EB'), 2.2))",
            "        for first, second in zip(points, points[1:]):",
            "            painter.drawLine(round(first[0]), round(first[1]), round(second[0]), round(second[1]))",
            "        painter.setBrush(QColor('#2563EB'))",
            "        for x, y in points:",
            "            painter.drawEllipse(round(x) - 2, round(y) - 2, 4, 4)",
            "",
            "",
        ])
    if has_ellipse:
        helper_classes.extend([
            "class EllipseWidget(QWidget):",
            "    def paintEvent(self, event):",
            "        painter = QPainter(self)",
            "        painter.setRenderHint(QPainter.RenderHint.Antialiasing)",
            "        painter.setPen(QPen(QColor('#64748B'), 1.5))",
            "        painter.setBrush(Qt.BrushStyle.NoBrush)",
            "        painter.drawEllipse(self.rect().adjusted(1, 1, -1, -1))",
            "",
            "",
        ])

    ordered = sorted(
        enumerate(document.elements),
        key=lambda pair: (pair[1].element_type != "panel", pair[1].y, pair[1].x, pair[0]),
    )
    widget_initialization: list[str] = []
    for index, (_, element) in enumerate(ordered, start=1):
        widget_initialization.extend(_element_code(element, index))

    class_lines = [
        f"class {class_name}(QWidget):",
        "    def __init__(self):",
        "        super().__init__()",
        f"        self.setWindowTitle({document.name!r})",
        f"        self.resize({document.width}, {document.height})",
        "        self.setMinimumSize(240, 180)",
    ]
    if has_strokes:
        class_lines.extend(_format_stroke_assignment(document.strokes))
    class_lines.extend(widget_initialization)
    class_lines.extend([
        "",
        "    def paintEvent(self, event):",
        "        painter = QPainter(self)",
        "        painter.setRenderHint(QPainter.RenderHint.Antialiasing)",
        "        painter.fillRect(self.rect(), QColor('white'))",
    ])
    if has_strokes:
        class_lines.extend([
            "        for points, width in self._sketch_strokes:",
            "            if len(points) < 2:",
            "                continue",
            "            path = QPainterPath(QPointF(*points[0]))",
            "            for point in points[1:]:",
            "                path.lineTo(QPointF(*point))",
            "            painter.setPen(QPen(QColor('#202938'), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))",
            "            painter.drawPath(path)",
        ])

    tail = [
        "",
        "",
        "if __name__ == '__main__':",
        "    app = QApplication(sys.argv)",
        f"    window = {class_name}()",
        "    window.show()",
        "    sys.exit(app.exec())",
        "",
    ]
    return "\n".join(imports + helper_classes + class_lines + tail)
def _element_code(element: UIElement, index: int) -> list[str]:
    x, y, w, h = [max(0, int(round(v))) for v in (element.x, element.y, element.width, element.height)]
    widget = f"widget_{index}"
    t = element.element_type
    lines: list[str] = []
    if t == "button":
        lines.append(f"        {widget} = QPushButton({element.text or 'Button'!r}, self)")
    elif t in ("text_field", "search_field"):
        lines.append(f"        {widget} = QLineEdit(self)")
        if element.text:
            lines.append(f"        {widget}.setText({element.text!r})")
        placeholder = element.placeholder or ("Search..." if t == "search_field" else "Enter text...")
        lines.append(f"        {widget}.setPlaceholderText({placeholder!r})")
    elif t == "label":
        lines.append(f"        {widget} = QLabel({element.text or 'Label'!r}, self)")
    elif t == "checkbox":
        lines.append(f"        {widget} = QCheckBox({element.text or 'Option'!r}, self)")
    elif t == "dropdown":
        lines.append(f"        {widget} = QComboBox(self)")
        lines.append(f"        {widget}.addItems(['Option 1', 'Option 2', 'Option 3'])")
    elif t == "table":
        lines.append(f"        {widget} = QTableWidget({element.table_rows}, {element.table_columns}, self)")
        table_headers = [f"Column {i + 1}" for i in range(element.table_columns)]
        lines.append(f"        {widget}.setHorizontalHeaderLabels({table_headers!r})")
        lines.append(f"        {widget}.setVerticalHeaderLabels({[str(i + 1) for i in range(element.table_rows)]!r})")
        for row_index, row in enumerate(element.table_cells):
            for column_index, value in enumerate(row):
                if value:
                    lines.append(f"        {widget}.setItem({row_index}, {column_index}, QTableWidgetItem({value!r}))")
    elif t == "chart":
        lines.append(f"        {widget} = ChartWidget({element.chart_values!r}, self)")
    elif t == "ellipse":
        lines.append(f"        {widget} = EllipseWidget(self)")
    elif t == "panel":
        lines.append(f"        {widget} = QFrame(self)")
        lines.append(f"        {widget}.setFrameShape(QFrame.Shape.StyledPanel)")
    elif t == "radio_button":
        lines.append(f"        {widget} = QRadioButton({element.text or 'Option'!r}, self)")
    elif t == "line":
        lines.append(f"        {widget} = QFrame(self)")
        orientation = "VLine" if element.height > element.width else "HLine"
        lines.append(f"        {widget}.setFrameShape(QFrame.Shape.{orientation})")
    else:
        raise ValueError(f"Unsupported element type: {t}")
    lines.append(f"        {widget}.setGeometry({x}, {y}, {w}, {h})")
    if t == "search_field":
        lines.append(f"        {widget}.setStyleSheet('QLineEdit {{ padding-left: 8px; }}')")
    lines.append("")
    return lines
