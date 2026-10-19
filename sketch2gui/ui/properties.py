from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QLabel, QComboBox, QLineEdit, QSpinBox, QGroupBox

from ..models import SUPPORTED_ELEMENT_TYPES, UIElement

TYPE_LABELS = {
    "button": "Button", "text_field": "Text field", "search_field": "Search field",
    "label": "Label", "checkbox": "Checkbox", "dropdown": "Dropdown",
    "table": "Table", "panel": "Panel", "radio_button": "Radio button", "line": "Line / separator",
}


class PropertiesPanel(QWidget):
    change_requested = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._element_id: str | None = None
        self._loading = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(12)
        self.heading = QLabel("Select a component")
        self.heading.setStyleSheet("font-size:15px;font-weight:600;")
        self.hint = QLabel("Click an element in the preview or canvas to inspect it.")
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color:#667085;")
        outer.addWidget(self.heading)
        outer.addWidget(self.hint)

        general_box = QGroupBox("Component")
        general = QFormLayout(general_box)
        self.type_combo = QComboBox()
        for key in sorted(SUPPORTED_ELEMENT_TYPES, key=lambda t: TYPE_LABELS[t]):
            self.type_combo.addItem(TYPE_LABELS[key], key)
        self.text_edit = QLineEdit()
        self.placeholder_edit = QLineEdit()
        general.addRow("Type", self.type_combo)
        general.addRow("Text / label", self.text_edit)
        general.addRow("Placeholder", self.placeholder_edit)
        outer.addWidget(general_box)

        bounds_box = QGroupBox("Position and size")
        bounds = QFormLayout(bounds_box)
        self.x_spin = self._spin()
        self.y_spin = self._spin()
        self.width_spin = self._spin(8, 3000)
        self.height_spin = self._spin(8, 3000)
        bounds.addRow("X", self.x_spin)
        bounds.addRow("Y", self.y_spin)
        bounds.addRow("Width", self.width_spin)
        bounds.addRow("Height", self.height_spin)
        outer.addWidget(bounds_box)

        self.confidence_label = QLabel("Recognition status: —")
        self.confidence_label.setWordWrap(True)
        self.confidence_label.setStyleSheet("color:#667085;")
        outer.addWidget(self.confidence_label)
        outer.addStretch(1)

        self.type_combo.currentIndexChanged.connect(self._type_changed)
        self.text_edit.editingFinished.connect(lambda: self._send("text", self.text_edit.text()))
        self.placeholder_edit.editingFinished.connect(lambda: self._send("placeholder", self.placeholder_edit.text()))
        for field, spin in (("x", self.x_spin), ("y", self.y_spin), ("width", self.width_spin), ("height", self.height_spin)):
            spin.valueChanged.connect(lambda value, name=field: self._send(name, value))
        self.set_element(None)

    @staticmethod
    def _spin(minimum: int = 0, maximum: int = 3000) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(5)
        return spin

    def _send(self, field: str, value: object) -> None:
        if not self._loading and self._element_id:
            self.change_requested.emit(field, value)

    def _type_changed(self, index: int) -> None:
        if not self._loading and self._element_id:
            self.change_requested.emit("element_type", self.type_combo.itemData(index))

    def set_element(self, element: UIElement | None) -> None:
        self._loading = True
        self._element_id = element.element_id if element else None
        enabled = element is not None
        for control in (self.type_combo, self.text_edit, self.placeholder_edit,
                        self.x_spin, self.y_spin, self.width_spin, self.height_spin):
            control.setEnabled(enabled)
        if not element:
            self.heading.setText("Select a component")
            self.hint.setText("Click an element in the preview or canvas to inspect it.")
            self.text_edit.clear()
            self.placeholder_edit.clear()
            self.confidence_label.setText("Recognition status: —")
            self._loading = False
            return
        self.heading.setText(f"{TYPE_LABELS[element.element_type]} · {element.element_id}")
        self.hint.setText("Edit the detected component. Your changes update the preview and generated code.")
        index = self.type_combo.findData(element.element_type)
        self.type_combo.setCurrentIndex(max(0, index))
        self.text_edit.setText(element.text)
        self.placeholder_edit.setText(element.placeholder)
        self.x_spin.setValue(int(round(element.x)))
        self.y_spin.setValue(int(round(element.y)))
        self.width_spin.setValue(int(round(element.width)))
        self.height_spin.setValue(int(round(element.height)))
        if element.confirmed:
            status = "Confirmed by you"
            color = "#237A57"
        elif element.needs_review:
            options = ", ".join(TYPE_LABELS[x] for x in element.alternatives if x in TYPE_LABELS)
            status = f"Needs review · heuristic confidence {element.confidence:.0%}"
            if options:
                status += f"\nOther possibilities: {options}"
            color = "#9A6816"
        else:
            status = f"Higher-confidence guess · {element.confidence:.0%}"
            color = "#667085"
        if element.ocr_confidence is not None:
            status += f"\nOCR score: {element.ocr_confidence:.0%} (model-specific; not calibrated across engines)"
        self.confidence_label.setText(status)
        self.confidence_label.setStyleSheet(f"color:{color};")
        self._loading = False
