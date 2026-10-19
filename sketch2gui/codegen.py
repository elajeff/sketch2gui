"""Readable, deterministic Python source generation from the shared model."""
from __future__ import annotations

import keyword
import re

from .models import DesignDocument, UIElement


def _safe_identifier(value: str, fallback: str) -> str:
    cleaned = re.sub(r"\W+", "_", value).strip("_")
    if not cleaned or cleaned[0].isdigit() or keyword.iskeyword(cleaned):
        cleaned = fallback
    return cleaned


def generate_python(document: DesignDocument, class_name: str = "GeneratedWindow") -> str:
    """Generate a standalone PySide6 QWidget program using absolute coordinates."""
    class_name = _safe_identifier(class_name, "GeneratedWindow")
    class_name = "".join(part[:1].upper() + part[1:] for part in class_name.split("_")) or "GeneratedWindow"
    imports = [
        "import sys",
        "from PySide6.QtWidgets import (",
        "    QApplication, QWidget, QPushButton, QLineEdit, QLabel,",
        "    QCheckBox, QComboBox, QTableWidget,",
        "    QFrame, QRadioButton,",
        ")",
        "",
        "",
        f"class {class_name}(QWidget):",
        "    def __init__(self):",
        "        super().__init__()",
        f"        self.setWindowTitle({document.name!r})",
        f"        self.resize({document.width}, {document.height})",
        "        self.setMinimumSize(240, 180)",
        "",
    ]
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
        lines.append(f"        {widget} = QTableWidget(3, 3, self)")
        lines.append(f"        {widget}.setHorizontalHeaderLabels(['Column 1', 'Column 2', 'Column 3'])")
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
