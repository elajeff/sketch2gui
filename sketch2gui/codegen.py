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
    stroke_assignment = _format_stroke_assignment(document.strokes)
    imports = [
        "import sys",
        "from PySide6.QtCore import Qt, QPointF",
        "from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen",
        "from PySide6.QtWidgets import (",
        "    QApplication, QWidget, QPushButton, QLineEdit, QLabel,",
        "    QCheckBox, QComboBox, QTableWidget, QTableWidgetItem,",
        "    QFrame, QRadioButton,",
        ")",
        "",
        "",
    ]
    if any(element.element_type == "chart" for element in document.elements):
        imports.extend([
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
            "        low, high = min(self.values), max(self.values)",
            "        span = high - low or 1.0",
            "        points = [(left + (right-left)*index/(len(self.values)-1), bottom - (value-low)/span*(bottom-top)) for index, value in enumerate(self.values)]",
            "        painter.setPen(QPen(QColor('#2563EB'), 2.2))",
            "        for first, second in zip(points, points[1:]):",
            "            painter.drawLine(round(first[0]), round(first[1]), round(second[0]), round(second[1]))",
            "        painter.setBrush(QColor('#2563EB'))",
            "        for x, y in points:",
            "            painter.drawEllipse(round(x)-2, round(y)-2, 4, 4)",
            "",
            "",
        ])
    if any(element.element_type == "ellipse" for element in document.elements):
        imports.extend([
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
    imports.extend([
        f"class {class_name}(QWidget):",
        "    def __init__(self):",
        "        super().__init__()",
        f"        self.setWindowTitle({document.name!r})",
        f"        self.resize({document.width}, {document.height})",
        "        self.setMinimumSize(240, 180)",
        *stroke_assignment,
        "",
        "    def paintEvent(self, event):",
        "        painter = QPainter(self)",
        "        painter.setRenderHint(QPainter.RenderHint.Antialiasing)",
        "        painter.fillRect(self.rect(), QColor('white'))",
        "        for points, width in getattr(self, '_sketch_strokes', []):",
        "            if len(points) < 2:",
        "                continue",
        "            path = QPainterPath(QPointF(*points[0]))",
        "            for point in points[1:]:",
        "                path.lineTo(QPointF(*point))",
        "            painter.setPen(QPen(QColor('#202938'), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))",
        "            painter.drawPath(path)",
        "",
        "",
    ])
    widgets = []
    ordered = sorted(enumerate(document.elements), key=lambda pair: (pair[1].element_type != "panel", pair[1].y, pair[1].x, pair[0]))
    for index, (_, element) in enumerate(ordered, start=1):
        widgets.extend(_element_code(element, index))
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
    return "\n".join(imports + widgets + tail)


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
