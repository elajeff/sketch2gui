from __future__ import annotations

import copy
import importlib.util
import json
import math
import os
import tempfile
import time
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QAction, QKeySequence, QFont, QTextCursor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QCheckBox,
    QSplitter, QPlainTextEdit, QScrollArea, QFileDialog, QMessageBox, QInputDialog,
    QFrame,
)

from ..app_icon import load_app_icon
from ..codegen import generate_python
from ..geometry import recognize_sketch
from ..models import DesignDocument, UIElement, Stroke, preserve_manual_edits, new_id, SUPPORTED_ELEMENT_TYPES
from ..ocr import load_backend
from ..sample_images import render_strokes
from .canvas import DrawingCanvas
from .preview import PreviewSurface
from .properties import PropertiesPanel


def _atomic_write_text(target: Path, contents: str) -> None:
    """Write text beside its destination, then replace it only after a full write."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(contents)
        os.replace(temporary_path, target)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


class WorkerSignals(QObject):
    finished = Signal(object, object)  # result, error string or None


def _optional_modules_available(*module_names: str) -> bool:
    """Return whether every optional dependency is discoverable without importing it."""
    try:
        return all(importlib.util.find_spec(name) is not None for name in module_names)
    except (ImportError, ValueError):
        return False


def _paddle_dependencies_available() -> bool:
    """Avoid selecting Paddle by default when its optional dependencies are missing."""
    return _optional_modules_available("paddle", "paddleocr")


def _trocr_dependencies_available() -> bool:
    """Expose the experimental TrOCR option only when its optional packages exist."""
    return _optional_modules_available("torch", "transformers")

class InterpretWorker(QRunnable):
    def __init__(self, document: DesignDocument, engine_name: str):
        super().__init__()
        self.document = document
        self.engine_name = engine_name
        self.signals = WorkerSignals()

    def run(self):
        try:
            ocr_callable = None
            if self.engine_name != "off":
                backend = load_backend(self.engine_name)
                ocr_callable = backend.recognize
            result = recognize_sketch(self.document, ocr=ocr_callable)
            self.signals.finished.emit(result, None)
        except Exception as exc:
            self.signals.finished.emit(None, f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(load_app_icon())
        self.setWindowTitle("Sketch2GUI")
        self.resize(1540, 930)
        self.setMinimumSize(1120, 720)
        self.document = DesignDocument()
        self.selected_id: str | None = None
        self.selected_ids: set[str] = set()
        self._undo_stack: list[str] = []
        self._redo_stack: list[str] = []
        self._history_limit = 60
        self._pending_before: str | None = None
        self._pending_elements: list[UIElement] = []
        self._current_file: Path | None = None
        self._busy = False
        self._pool = QThreadPool.globalInstance()
        self._worker: InterpretWorker | None = None

        self._build_ui()
        self._build_actions()
        self._refresh_all()
        self.statusBar().showMessage("Draw a rough interface on the left, then choose Interpret sketch.")

    def _build_ui(self):
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(10, 8, 10, 8)
        root_layout.setSpacing(8)
        toolbar = QHBoxLayout()
        self.interpret_button = QPushButton("Interpret sketch")
        self.interpret_button.setStyleSheet("QPushButton { background:#2563EB; color:white; border:0; border-radius:5px; padding:8px 14px; font-weight:600; } QPushButton:hover { background:#1D4ED8; }")
        self.undo_button = QPushButton("Undo")
        self.redo_button = QPushButton("Redo")
        self.clear_button = QPushButton("Clear drawing")
        self.save_button = QPushButton("Save project")
        self.open_button = QPushButton("Open project")
        self.export_button = QPushButton("Export Python")
        self.delete_button = QPushButton("Delete component")
        self.sample_button = QPushButton("Save OCR sample…")
        self.engine_combo = QComboBox()
        self.engine_combo.addItem("OCR off (geometry only)", "off")
        self.engine_combo.addItem("PaddleOCR · English (recommended)", "paddle")
        if _trocr_dependencies_available():
            self.engine_combo.addItem("TrOCR · handwritten (experimental)", "trocr")
        self.engine_combo.setToolTip(
            "PaddleOCR is the recommended OCR based on a small local test. "
            "When installed, it is selected automatically. OCR models may download on first use; "
            "choose OCR off for geometry-only operation."
        )
        if _paddle_dependencies_available():
            self.engine_combo.setCurrentIndex(1)
        for widget in (self.interpret_button, self.undo_button, self.redo_button, self.clear_button,
                       self.save_button, self.open_button, self.export_button, self.delete_button, self.sample_button, self.engine_combo):
            toolbar.addWidget(widget)
        toolbar.addStretch(1)
        self.review_button = QPushButton("0 to review")
        self.review_button.setToolTip("Select the next component that has an uncertain interpretation.")
        toolbar.addWidget(self.review_button)
        root_layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        # Make the canvas fill the entire left panel. A separate header and
        # inner layout margins left visible strips that looked drawable but did
        # not belong to the DrawingCanvas widget, so mouse strokes could not
        # start there.
        self.canvas = DrawingCanvas()
        canvas_frame = QFrame()
        canvas_frame.setFrameShape(QFrame.Shape.StyledPanel)
        canvas_layout = QVBoxLayout(canvas_frame)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)
        tool_row = QHBoxLayout()
        tool_row.addWidget(QLabel("Tool:"))
        self.drawing_tool_combo = QComboBox()
        for label, key in (
            ("Freehand", "freehand"),
            ("Select", "select"),
            ("Box", "panel"),
            ("Button", "button"),
            ("Text field", "text_field"),
            ("Label", "label"),
            ("Table", "table"),
            ("Chart", "chart"),
            ("Ellipse", "ellipse"),
            ("Line", "line"),
        ):
            self.drawing_tool_combo.addItem(label, key)
        self.drawing_tool_combo.setToolTip("Freehand preserves your drawing. Choose a component tool, then drag on the canvas to create a clean component directly.")
        tool_row.addWidget(self.drawing_tool_combo, 1)
        canvas_layout.addLayout(tool_row)
        edit_row = QHBoxLayout()
        self.snap_checkbox = QCheckBox("Snap 10 px")
        self.snap_checkbox.setChecked(True)
        self.duplicate_button = QPushButton("Duplicate")
        self.align_combo = QComboBox()
        for label, key in (("Left", "left"), ("Center X", "center_x"), ("Right", "right"), ("Top", "top"), ("Center Y", "center_y"), ("Bottom", "bottom")):
            self.align_combo.addItem(label, key)
        self.align_button = QPushButton("Align")
        edit_row.addWidget(self.snap_checkbox)
        edit_row.addWidget(self.duplicate_button)
        edit_row.addWidget(self.align_combo, 1)
        edit_row.addWidget(self.align_button)
        canvas_layout.addLayout(edit_row)
        canvas_layout.addWidget(self.canvas, 1)

        middle_splitter = QSplitter(Qt.Orientation.Vertical)
        preview_frame = QFrame()
        preview_frame.setFrameShape(QFrame.Shape.StyledPanel)
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        preview_layout.addWidget(self._section_label("2 · Interpreted GUI preview"))
        self.preview = PreviewSurface()
        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        preview_scroll.setWidget(self.preview)
        preview_layout.addWidget(preview_scroll, 1)

        code_frame = QFrame()
        code_frame.setFrameShape(QFrame.Shape.StyledPanel)
        code_layout = QVBoxLayout(code_frame)
        code_layout.setContentsMargins(8, 8, 8, 8)
        code_layout.addWidget(self._section_label("3 · Generated PySide6 code"))
        self.code_editor = QPlainTextEdit()
        self.code_editor.setReadOnly(True)
        self.code_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.code_editor.setFont(QFont("Consolas", 9))
        self.code_editor.setStyleSheet("QPlainTextEdit { background:#151A23; color:#D8E1F0; border:0; selection-background-color:#284E8C; }")
        code_layout.addWidget(self.code_editor, 1)
        middle_splitter.addWidget(preview_frame)
        middle_splitter.addWidget(code_frame)
        middle_splitter.setSizes([440, 360])

        self.properties = PropertiesPanel()
        self.properties.setMinimumWidth(235)
        splitter.addWidget(canvas_frame)
        splitter.addWidget(middle_splitter)
        splitter.addWidget(self.properties)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 2)
        splitter.setSizes([470, 630, 290])
        root_layout.addWidget(splitter, 1)
        self.setCentralWidget(root)

        self.interpret_button.clicked.connect(self.interpret_sketch)
        self.undo_button.clicked.connect(self.undo)
        self.redo_button.clicked.connect(self.redo)
        self.clear_button.clicked.connect(self.clear_drawing)
        self.save_button.clicked.connect(self.save_project)
        self.open_button.clicked.connect(self.open_project)
        self.export_button.clicked.connect(self.export_python)
        self.delete_button.clicked.connect(self.delete_selected_element)
        self.sample_button.clicked.connect(self.save_ocr_sample)
        self.review_button.clicked.connect(self.select_next_uncertain)
        self.canvas.stroke_added.connect(self.add_stroke)
        self.canvas.element_added.connect(self.add_created_element)
        self.canvas.element_geometry_changed.connect(self.commit_element_geometry)
        self.canvas.selection_toggled.connect(self.toggle_selected_element)
        self.snap_checkbox.toggled.connect(lambda checked: setattr(self.canvas, "snap_enabled", bool(checked)))
        self.duplicate_button.clicked.connect(self.duplicate_selected_elements)
        self.align_button.clicked.connect(self.align_selected_elements)
        self.preview.table_cell_changed.connect(self.update_table_cell)
        self.preview.selection_toggled.connect(self.toggle_selected_element)
        self.drawing_tool_combo.currentIndexChanged.connect(
            lambda _index: self.canvas.set_tool(str(self.drawing_tool_combo.currentData()))
        )
        self.canvas.set_tool(str(self.drawing_tool_combo.currentData()))
        self.canvas.element_selected.connect(self.select_element)
        self.preview.element_selected.connect(self.select_element)
        self.preview.text_edit_finished.connect(self.update_preview_text)
        self.properties.change_requested.connect(self.change_element_property)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-weight:600;font-size:13px;padding-bottom:3px;")
        return label

    def _build_actions(self):
        undo_action = QAction("Undo", self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self.undo)
        self.addAction(undo_action)
        redo_action = QAction("Redo", self)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(self.redo)
        self.addAction(redo_action)
        save_action = QAction("Save project", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_project)
        self.addAction(save_action)
        open_action = QAction("Open project", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_project)
        self.addAction(open_action)
        delete_action = QAction("Delete selected component", self)
        delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        delete_action.triggered.connect(self.delete_selected_element)
        self.addAction(delete_action)

    def _serialize(self) -> str:
        return json.dumps(self.document.to_dict(), ensure_ascii=False, sort_keys=True)

    def _snapshot(self):
        state = self._serialize()
        if not self._undo_stack or self._undo_stack[-1] != state:
            self._undo_stack.append(state)
            self._undo_stack = self._undo_stack[-self._history_limit:]
        self._redo_stack.clear()

    def undo(self):
        if not self._undo_stack or self._busy:
            return
        self._redo_stack.append(self._serialize())
        state = self._undo_stack.pop()
        self.document = DesignDocument.from_dict(json.loads(state))
        self.selected_id = None
        self.selected_ids.clear()
        self._refresh_all()
        self.statusBar().showMessage("Undid the previous design change.", 2500)

    def redo(self):
        if not self._redo_stack or self._busy:
            return
        self._undo_stack.append(self._serialize())
        state = self._redo_stack.pop()
        self.document = DesignDocument.from_dict(json.loads(state))
        self.selected_id = None
        self.selected_ids.clear()
        self._refresh_all()
        self.statusBar().showMessage("Redid the design change.", 2500)

    def add_stroke(self, stroke: Stroke):
        if self._busy:
            return
        self._snapshot()
        self.document.strokes.append(stroke)
        self.canvas.set_document(self.document)
        # Redraw the original ink without rebuilding controls in the preview.
        self.preview.update_strokes()
        self._refresh_code()
        self.statusBar().showMessage(f"Captured stroke · {len(self.document.strokes)} total. Interpret when you're ready.", 2500)

    def _refresh_selection_ui(self):
        valid_ids = {element.element_id for element in self.document.elements}
        self.selected_ids.intersection_update(valid_ids)
        if self.selected_id not in self.selected_ids:
            self.selected_id = next(iter(self.selected_ids), None)
        primary = next((e for e in self.document.elements if e.element_id == self.selected_id), None)
        self.canvas.set_selected_many(self.selected_ids, self.selected_id)
        self.preview.set_selected_many(self.selected_ids, self.selected_id)
        self.properties.set_element(primary)
        self.delete_button.setEnabled(bool(self.selected_ids) and not self._busy)
        self.duplicate_button.setEnabled(bool(self.selected_ids) and not self._busy)
        self.align_button.setEnabled(len(self.selected_ids) >= 2 and not self._busy)

    def toggle_selected_element(self, element_id):
        if element_id is None:
            return
        if not any(e.element_id == element_id for e in self.document.elements):
            return
        if element_id in self.selected_ids:
            self.selected_ids.remove(element_id)
        else:
            self.selected_ids.add(element_id)
            self.selected_id = element_id
        if self.selected_id not in self.selected_ids:
            self.selected_id = next(iter(self.selected_ids), None)
        self._refresh_selection_ui()

    def commit_element_geometry(self, element_id: str, x: float, y: float, width: float, height: float):
        element = next((e for e in self.document.elements if e.element_id == element_id), None)
        if element is None or self._busy:
            return
        width = min(max(8.0, float(width)), float(self.document.width))
        height = min(max(8.0, float(height)), float(self.document.height))
        x = min(max(0.0, float(x)), float(self.document.width) - width)
        y = min(max(0.0, float(y)), float(self.document.height) - height)
        if (element.x, element.y, element.width, element.height) == (x, y, width, height):
            return
        self._snapshot()
        element.x, element.y, element.width, element.height = x, y, width, height
        element.user_modified = True
        element.confirmed = True
        element.confidence = 1.0
        element.alternatives = []
        self._refresh_all()
        self.statusBar().showMessage("Component position or size updated.", 2200)

    def duplicate_selected_elements(self):
        if self._busy or not self.selected_ids:
            return
        selected = [copy.deepcopy(e) for e in self.document.elements if e.element_id in self.selected_ids]
        if not selected:
            return
        self._snapshot()
        created = []
        for element in selected:
            element.element_id = new_id()
            element.source_stroke_ids = []
            element.x = min(float(self.document.width) - element.width, element.x + 20)
            element.y = min(float(self.document.height) - element.height, element.y + 20)
            element.user_modified = True
            element.confirmed = True
            element.confidence = 1.0
            element.alternatives = []
            created.append(element)
        self.document.elements.extend(created)
        self.selected_ids = {e.element_id for e in created}
        self.selected_id = created[-1].element_id
        self._refresh_all()
        self.statusBar().showMessage(f"Duplicated {len(created)} component(s).", 2200)

    def align_selected_elements(self):
        if self._busy or len(self.selected_ids) < 2:
            self.statusBar().showMessage("Hold Shift and select at least two components, then choose Align.", 3000)
            return
        chosen = [e for e in self.document.elements if e.element_id in self.selected_ids]
        anchor = next((e for e in chosen if e.element_id == self.selected_id), chosen[0])
        mode = str(self.align_combo.currentData())
        self._snapshot()
        for element in chosen:
            if element.element_id == anchor.element_id:
                continue
            if mode == "left":
                element.x = anchor.x
            elif mode == "center_x":
                element.x = anchor.x + (anchor.width - element.width) / 2
            elif mode == "right":
                element.x = anchor.x + anchor.width - element.width
            elif mode == "top":
                element.y = anchor.y
            elif mode == "center_y":
                element.y = anchor.y + (anchor.height - element.height) / 2
            elif mode == "bottom":
                element.y = anchor.y + anchor.height - element.height
            # Alignment takes precedence over snapping so aligned edges remain exact.
            element.x = min(max(0.0, element.x), max(0.0, self.document.width-element.width))
            element.y = min(max(0.0, element.y), max(0.0, self.document.height-element.height))
            element.user_modified = True
            element.confirmed = True
            element.confidence = 1.0
            element.alternatives = []
        self._refresh_all()
        self.statusBar().showMessage("Selected components aligned.", 2200)

    def update_table_cell(self, element_id: str, row: int, column: int, value: str):
        element = next((e for e in self.document.elements if e.element_id == element_id), None)
        if element is None or element.element_type != "table" or self._busy:
            return
        if not (0 <= row < element.table_rows and 0 <= column < element.table_columns):
            return
        value = str(value)[:500]
        if element.table_cells[row][column] == value:
            return
        self._snapshot()
        element.table_cells[row][column] = value
        element.user_modified = True
        element.confirmed = True
        element.confidence = 1.0
        element.alternatives = []
        self._refresh_code()
        self.canvas.update()
        self.undo_button.setEnabled(bool(self._undo_stack) and not self._busy)
        self.redo_button.setEnabled(bool(self._redo_stack) and not self._busy)

    def add_created_element(self, element: UIElement):
        if self._busy:
            return
        self._snapshot()
        self.document.elements.append(element)
        self.selected_id = element.element_id
        self.selected_ids = {element.element_id}
        self._refresh_all()
        self.statusBar().showMessage(f"Added {element.element_type.replace('_', ' ')}.", 2200)

    def _set_recognition_busy(self, busy: bool) -> None:
        """Keep all controls consistent while the background OCR worker is active."""
        self._busy = busy
        self.canvas.drawing_enabled = not busy
        for widget in (
            self.canvas, self.preview, self.properties, self.interpret_button,
            self.undo_button, self.redo_button, self.clear_button, self.save_button,
            self.open_button, self.export_button, self.delete_button, self.sample_button,
            self.engine_combo, self.drawing_tool_combo, self.snap_checkbox,
            self.duplicate_button, self.align_combo, self.align_button, self.review_button,
        ):
            widget.setEnabled(not busy)

    def interpret_sketch(self):
        if self._busy:
            return
        if not self.document.strokes:
            QMessageBox.information(self, "Nothing to interpret", "Draw a few shapes or labels on the left canvas first.")
            return
        engine = str(self.engine_combo.currentData())
        if engine == "off":
            self._snapshot()
            result = recognize_sketch(copy.deepcopy(self.document))
            self.document.elements = preserve_manual_edits(self.document.elements, result)
            self.selected_id = None
            self.selected_ids.clear()
            self._refresh_all()
            self.statusBar().showMessage(f"Interpreted sketch · {len(result)} candidate components.", 4000)
            return
        self._pending_before = self._serialize()
        self._pending_elements = copy.deepcopy(self.document.elements)
        snapshot = copy.deepcopy(self.document)
        self._set_recognition_busy(True)
        self.statusBar().showMessage(
            "Loading OCR model and interpreting sketch. First use may download model files…"
        )
        worker = InterpretWorker(snapshot, engine)
        worker.signals.finished.connect(self._interpret_finished)
        self._worker = worker
        self._pool.start(worker)

    def _interpret_finished(self, result, error):
        self._worker = None
        self._set_recognition_busy(False)
        if error:
            self._pending_elements = []
            self._pending_before = None
            self._refresh_all()
            QMessageBox.warning(self, "OCR / recognition failed", error.split("\n\n", 1)[0] + "\n\nYou can switch OCR off and still use geometry recognition.")
            self.statusBar().showMessage("Recognition failed; your sketch has been kept.", 5000)
            return
        if self._pending_before:
            self._undo_stack.append(self._pending_before)
            self._undo_stack = self._undo_stack[-self._history_limit:]
            self._redo_stack.clear()
        self.document.elements = preserve_manual_edits(self._pending_elements, result)
        self._pending_elements = []
        self.selected_id = None
        self.selected_ids.clear()
        self._refresh_all()
        count = sum(element.needs_review for element in self.document.elements)
        self.statusBar().showMessage(f"Interpreted sketch · {len(result)} components, {count} to review.", 5000)

    def update_preview_text(self, element_id: str, value: str):
        element = next((item for item in self.document.elements if item.element_id == element_id), None)
        if element is None or element.text == value or self._busy:
            return
        self._snapshot()
        element.text = value
        element.user_modified = True
        element.confirmed = True
        element.confidence = 1.0
        element.alternatives = []
        # Do not rebuild the preview widgets after a field commit: the current
        # QLineEdit is already showing the edited value, and rebuilding here
        # would interrupt focus or discard the next field's click event.
        self._refresh_code()
        self.canvas.set_document(self.document)
        self.properties.set_element(element)
        self.preview.set_selected(self.selected_id)
        self.undo_button.setEnabled(bool(self._undo_stack) and not self._busy)
        self.redo_button.setEnabled(bool(self._redo_stack) and not self._busy)
        uncertain_count = sum(item.needs_review for item in self.document.elements)
        self.review_button.setText(f"{uncertain_count} to review")
        self.review_button.setEnabled(uncertain_count > 0)
        self.statusBar().showMessage("Text field updated.", 2200)

    def select_element(self, element_id):
        valid_ids = {e.element_id for e in self.document.elements}
        self.selected_id = element_id if element_id in valid_ids else None
        self.selected_ids = {self.selected_id} if self.selected_id else set()
        self.delete_button.setEnabled(self.selected_id is not None and not self._busy)
        self._refresh_selection_ui()

    def change_element_property(self, field: str, value):
        """Validate one property edit before recording it in undo history."""
        if self._busy:
            return
        element = next(
            (item for item in self.document.elements if item.element_id == self.selected_id),
            None,
        )
        if element is None:
            return

        supported_fields = {
            "element_type", "x", "y", "width", "height", "text", "placeholder",
            "chart_values", "table_rows", "table_columns",
        }
        if field not in supported_fields:
            return

        normalized_value = value
        new_bounds = None
        new_table = None
        try:
            if field == "element_type":
                normalized_value = str(value)
                if normalized_value not in SUPPORTED_ELEMENT_TYPES:
                    return
            elif field in ("x", "y", "width", "height"):
                requested = float(value)
                if not math.isfinite(requested):
                    return
                canvas_width = float(self.document.width)
                canvas_height = float(self.document.height)
                width = min(max(8.0, float(element.width)), canvas_width)
                height = min(max(8.0, float(element.height)), canvas_height)
                x = min(max(0.0, float(element.x)), max(0.0, canvas_width - width))
                y = min(max(0.0, float(element.y)), max(0.0, canvas_height - height))

                if field == "x":
                    x = min(max(0.0, requested), max(0.0, canvas_width - width))
                elif field == "y":
                    y = min(max(0.0, requested), max(0.0, canvas_height - height))
                elif field == "width":
                    width = min(max(8.0, requested), max(8.0, canvas_width - x))
                else:
                    height = min(max(8.0, requested), max(8.0, canvas_height - y))
                new_bounds = (x, y, width, height)
                old_bounds = (element.x, element.y, element.width, element.height)
                if new_bounds == old_bounds:
                    return
            elif field in ("text", "placeholder"):
                normalized_value = str(value)
            elif field == "chart_values":
                if element.element_type != "chart":
                    return
                normalized_value = [float(item) for item in value]
                if len(normalized_value) > 100 or any(not math.isfinite(item) for item in normalized_value):
                    return
            elif field in ("table_rows", "table_columns"):
                if element.element_type != "table":
                    return
                size = int(value)
                if not 1 <= size <= 20:
                    return
                rows = size if field == "table_rows" else element.table_rows
                columns = size if field == "table_columns" else element.table_columns
                old_cells = element.table_cells
                new_cells = [
                    [str(old_cells[r][c]) if r < len(old_cells) and c < len(old_cells[r]) else ""
                     for c in range(columns)]
                    for r in range(rows)
                ]
                new_table = (rows, columns, new_cells)
                current = (element.table_rows, element.table_columns, element.table_cells)
                if new_table == current:
                    return
        except (TypeError, ValueError, OverflowError):
            return

        current_value = getattr(element, field, None)
        if field not in ("x", "y", "width", "height", "table_rows", "table_columns") and current_value == normalized_value:
            return

        # Do not create no-op/invalid history entries. Snapshot immediately before mutation.
        self._snapshot()
        if field == "element_type":
            element.set_type(normalized_value, user_confirmed=True)
        elif field in ("x", "y", "width", "height"):
            element.x, element.y, element.width, element.height = new_bounds
        elif field in ("text", "placeholder", "chart_values"):
            setattr(element, field, normalized_value)
        elif field in ("table_rows", "table_columns"):
            element.table_rows, element.table_columns, element.table_cells = new_table

        # Any explicit user edit resolves the component's recognition uncertainty.
        element.user_modified = True
        element.confirmed = True
        element.confidence = 1.0
        element.alternatives = []
        self._refresh_all()
        self.properties.set_element(element)
        self.statusBar().showMessage("Component updated · preview and code synchronized.", 2200)


    def select_next_uncertain(self):
        uncertain = [e for e in self.document.elements if e.needs_review]
        if not uncertain:
            self.statusBar().showMessage("No components currently need review.", 2500)
            return
        current_index = next((i for i, e in enumerate(uncertain) if e.element_id == self.selected_id), -1)
        next_element = uncertain[(current_index + 1) % len(uncertain)]
        self.select_element(next_element.element_id)
        self.statusBar().showMessage("Review this component's type in the Properties panel.", 3000)

    def delete_selected_element(self):
        if self._busy or not self.selected_ids:
            return
        before = len(self.document.elements)
        self._snapshot()
        self.document.elements = [e for e in self.document.elements if e.element_id not in self.selected_ids]
        removed_count = before - len(self.document.elements)
        if removed_count <= 0:
            return
        self.selected_ids.clear()
        self.selected_id = None
        self._refresh_all()
        self.statusBar().showMessage(f"Deleted {removed_count} component(s). Undo restores them.", 2500)

    def clear_drawing(self):
        if self._busy:
            return
        if not self.document.strokes and not self.document.elements:
            return
        answer = QMessageBox.question(self, "Clear current design", "Remove all strokes and detected components from this design?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._snapshot()
        self.document.strokes.clear()
        self.document.elements.clear()
        self.selected_id = None
        self._refresh_all()
        self.statusBar().showMessage("Drawing cleared.", 2500)

    def save_project(self):
        default = str(self._current_file or (Path.home() / "Sketch2GUI-project.json"))
        path, _ = QFileDialog.getSaveFileName(self, "Save Sketch2GUI project", default, "Sketch2GUI project (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        target = Path(path)
        previous_name = self.document.name
        self.document.name = target.stem
        try:
            contents = json.dumps(self.document.to_dict(), indent=2, ensure_ascii=False)
            _atomic_write_text(target, contents)
        except (OSError, TypeError, ValueError) as exc:
            self.document.name = previous_name
            QMessageBox.critical(self, "Could not save project", str(exc))
            return
        self._current_file = target
        self._refresh_code()
        self.statusBar().showMessage(f"Saved project to {target}", 4000)

    def open_project(self):
        if self._busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Sketch2GUI project", str(Path.home()), "Sketch2GUI project (*.json)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            new_document = DesignDocument.from_dict(data)
        except (OSError, ValueError, TypeError, OverflowError) as exc:
            QMessageBox.critical(self, "Could not open project", str(exc))
            return
        self._snapshot()
        self.document = new_document
        self._current_file = Path(path)
        self.selected_id = None
        self.selected_ids.clear()
        self._refresh_all()
        self.statusBar().showMessage(f"Opened {Path(path).name}", 3000)

    def export_python(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export generated Python", str(Path.home() / "generated_gui.py"), "Python source (*.py)")
        if not path:
            return
        if not path.lower().endswith(".py"):
            path += ".py"
        try:
            _atomic_write_text(Path(path), generate_python(self.document))
            self.statusBar().showMessage(f"Exported Python source to {path}", 4000)
        except (OSError, TypeError, ValueError) as exc:
            QMessageBox.critical(self, "Could not export Python", str(exc))

    def save_ocr_sample(self):
        """Save the current canvas strokes as a labeled OCR benchmark sample."""
        if not self.document.strokes:
            QMessageBox.information(self, "No handwriting", "Draw one word or short phrase on an otherwise empty canvas first.")
            return
        truth, ok = QInputDialog.getText(self, "Label OCR sample", "What text did you draw? (ground truth)")
        if not ok or not truth.strip():
            return
        suggested = Path.cwd() / "benchmark" / "samples" / f"sample_{time.time_ns()}.png"
        path, _ = QFileDialog.getSaveFileName(self, "Save labeled OCR sample", str(suggested), "PNG image (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        try:
            image = render_strokes(self.document.strokes)
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            truth_target = target.with_suffix(".txt")
            if target.exists() or truth_target.exists():
                raise FileExistsError("The image or label already exists. Choose a new filename to preserve the existing sample.")
            image_created = False
            truth_created = False
            try:
                with target.open("xb") as image_file:
                    image_created = True
                    image.save(image_file, format="PNG")
                with truth_target.open("x", encoding="utf-8") as truth_file:
                    truth_created = True
                    truth_file.write(truth.strip())
            except Exception:
                # Remove only the paired files created by this operation; existing
                # samples are never overwritten or removed on an error.
                if truth_created:
                    truth_target.unlink(missing_ok=True)
                if image_created:
                    target.unlink(missing_ok=True)
                raise
            QMessageBox.information(self, "Sample saved", f"Saved image and expected text:\n{target}\n{target.with_suffix('.txt')}\n\nCollect the same set of samples before comparing OCR engines.")
        except Exception as exc:
            QMessageBox.critical(self, "Could not save sample", str(exc))

    def _refresh_all(self):
        """Refresh the document views, then update shared selection state once."""
        self.canvas.set_document(self.document)
        self.preview.set_design(self.document, self.selected_id)
        self._refresh_code()
        self.undo_button.setEnabled(bool(self._undo_stack) and not self._busy)
        self.redo_button.setEnabled(bool(self._redo_stack) and not self._busy)
        uncertain_count = sum(element.needs_review for element in self.document.elements)
        self.review_button.setText(f"{uncertain_count} to review")
        self.review_button.setEnabled(uncertain_count > 0)
        self._refresh_selection_ui()


    def _refresh_code(self):
        """Preserve editor view state while generated source changes."""
        editor = self.code_editor
        generated = generate_python(self.document)
        if editor.toPlainText() == generated:
            return

        vertical_position = editor.verticalScrollBar().value()
        horizontal_position = editor.horizontalScrollBar().value()
        old_cursor = editor.textCursor()
        cursor_position = old_cursor.position()
        cursor_anchor = old_cursor.anchor()

        editor.setPlainText(generated)

        # Keep the caret/selection near the same source location after undo/redo.
        restored_cursor = editor.textCursor()
        restored_cursor.setPosition(min(cursor_anchor, len(generated)))
        restored_cursor.setPosition(
            min(cursor_position, len(generated)),
            QTextCursor.MoveMode.KeepAnchor,
        )
        editor.setTextCursor(restored_cursor)

        # Restore scrolling last because setting the cursor can auto-scroll the editor.
        editor.verticalScrollBar().setValue(
            min(vertical_position, editor.verticalScrollBar().maximum())
        )
        editor.horizontalScrollBar().setValue(
            min(horizontal_position, editor.horizontalScrollBar().maximum())
        )


    def closeEvent(self, event):
        if self._busy:
            answer = QMessageBox.question(self, "Recognition in progress", "OCR is still running. Close the app anyway?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()
