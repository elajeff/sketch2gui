from __future__ import annotations

import copy
import importlib.util
import json
import os
import tempfile
import time
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QAction, QKeySequence, QFont
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSplitter, QPlainTextEdit, QScrollArea, QFileDialog, QMessageBox, QInputDialog,
    QFrame,
)

from ..codegen import generate_python
from ..geometry import recognize_sketch
from ..models import DesignDocument, UIElement, Stroke, preserve_manual_edits
from ..ocr import load_backend
from ..sample_images import render_strokes
from .canvas import DrawingCanvas
from .preview import PreviewSurface
from .properties import PropertiesPanel


class WorkerSignals(QObject):
    finished = Signal(object, object)  # result, error string or None


def _paddle_dependencies_available() -> bool:
    """Avoid selecting Paddle by default when its optional dependencies are missing."""
    for module_name in ("paddle", "paddleocr"):
        try:
            if importlib.util.find_spec(module_name) is None:
                return False
        except (ImportError, ModuleNotFoundError, ValueError):
            return False
    return True


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
        self.setWindowTitle("Sketch2GUI")
        self.resize(1540, 930)
        self.setMinimumSize(1120, 720)
        self.document = DesignDocument()
        self.selected_id: str | None = None
        self._undo_stack: list[str] = []
        self._redo_stack: list[str] = []
        self._history_limit = 60
        self._revision = 0
        self._pending_before: str | None = None
        self._pending_elements: list[UIElement] = []
        self._current_file: Path | None = None
        self._busy = False
        self._pool = QThreadPool.globalInstance()
        self._worker: InterpretWorker | None = None
        self._last_property_snapshot = 0.0

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
        self.canvas = DrawingCanvas()
        canvas_frame = QFrame()
        canvas_frame.setFrameShape(QFrame.Shape.StyledPanel)
        canvas_layout = QVBoxLayout(canvas_frame)
        canvas_layout.setContentsMargins(8, 8, 8, 8)
        canvas_header = QLabel("1 · Freehand sketch")
        canvas_header.setStyleSheet("font-weight:600;font-size:13px;")
        canvas_layout.addWidget(canvas_header)
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
        self.canvas.element_selected.connect(self.select_element)
        self.preview.element_selected.connect(self.select_element)
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
        self._revision += 1
        self.selected_id = None
        self._refresh_all()
        self.statusBar().showMessage("Undid the previous design change.", 2500)

    def redo(self):
        if not self._redo_stack or self._busy:
            return
        self._undo_stack.append(self._serialize())
        state = self._redo_stack.pop()
        self.document = DesignDocument.from_dict(json.loads(state))
        self._revision += 1
        self.selected_id = None
        self._refresh_all()
        self.statusBar().showMessage("Redid the design change.", 2500)

    def add_stroke(self, stroke: Stroke):
        if self._busy:
            return
        self._snapshot()
        self.document.strokes.append(stroke)
        self._revision += 1
        self.canvas.set_document(self.document)
        self.statusBar().showMessage(f"Captured stroke · {len(self.document.strokes)} total. Interpret when you're ready.", 2500)

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
            self._revision += 1
            self.selected_id = None
            self._refresh_all()
            self.statusBar().showMessage(f"Interpreted sketch · {len(result)} candidate components.", 4000)
            return
        self._pending_before = self._serialize()
        self._pending_elements = copy.deepcopy(self.document.elements)
        snapshot = copy.deepcopy(self.document)
        self._busy = True
        self.canvas.drawing_enabled = False
        self.canvas.setEnabled(False)
        self.preview.setEnabled(False)
        self.properties.setEnabled(False)
        for button in (self.interpret_button, self.undo_button, self.redo_button, self.clear_button,
                       self.save_button, self.open_button, self.export_button, self.delete_button, self.sample_button, self.engine_combo):
            button.setEnabled(False)
        if engine == "off":
            self.statusBar().showMessage("Interpreting sketch using geometry only…")
        else:
            self.statusBar().showMessage("Loading OCR model and interpreting sketch. First use may download model files…")
        worker = InterpretWorker(snapshot, engine)
        worker.signals.finished.connect(self._interpret_finished)
        self._worker = worker
        self._pool.start(worker)

    def _interpret_finished(self, result, error):
        self._worker = None
        self._busy = False
        self.canvas.drawing_enabled = True
        self.canvas.setEnabled(True)
        self.preview.setEnabled(True)
        self.properties.setEnabled(True)
        for button in (self.interpret_button, self.undo_button, self.redo_button, self.clear_button,
                       self.save_button, self.open_button, self.export_button, self.delete_button, self.sample_button, self.engine_combo):
            button.setEnabled(True)
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
        self._revision += 1
        self.selected_id = None
        self._refresh_all()
        count = sum(element.needs_review for element in self.document.elements)
        self.statusBar().showMessage(f"Interpreted sketch · {len(result)} components, {count} to review.", 5000)

    def select_element(self, element_id):
        self.selected_id = element_id if element_id and any(e.element_id == element_id for e in self.document.elements) else None
        self.delete_button.setEnabled(self.selected_id is not None and not self._busy)
        element = next((e for e in self.document.elements if e.element_id == self.selected_id), None)
        self.properties.set_element(element)
        self.canvas.set_selected(self.selected_id)
        self.preview.set_design(self.document, self.selected_id)

    def change_element_property(self, field: str, value):
        element = next((e for e in self.document.elements if e.element_id == self.selected_id), None)
        if element is None or self._busy:
            return
        old = getattr(element, field, None)
        if old == value:
            return
        self._snapshot()
        if field == "element_type":
            element.set_type(str(value), user_confirmed=True)
        elif field in ("x", "y", "width", "height"):
            setattr(element, field, float(value))
            element.user_modified = True
        elif field in ("text", "placeholder"):
            setattr(element, field, str(value))
            element.user_modified = True
        else:
            return
        self._revision += 1
        self._refresh_all()
        # Restore panel focus/content after rebuilding widgets.
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
        if self._busy or self.selected_id is None:
            return
        before = len(self.document.elements)
        self._snapshot()
        self.document.elements = [e for e in self.document.elements if e.element_id != self.selected_id]
        if len(self.document.elements) == before:
            return
        self.selected_id = None
        self._revision += 1
        self._refresh_all()
        self.statusBar().showMessage("Selected component deleted. Undo restores it.", 2500)

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
        self._revision += 1
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
        temp_path: Path | None = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            self.document.name = target.stem
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=target.parent,
                prefix=f".{target.name}.", suffix=".tmp", delete=False,
            ) as temp:
                temp_path = Path(temp.name)
                json.dump(self.document.to_dict(), temp, indent=2, ensure_ascii=False)
            os.replace(temp_path, target)
            temp_path = None
            self._current_file = target
            self._refresh_code()
            self.statusBar().showMessage(f"Saved project to {target}", 4000)
        except OSError as exc:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            QMessageBox.critical(self, "Could not save project", str(exc))

    def open_project(self):
        if self._busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Sketch2GUI project", str(Path.home()), "Sketch2GUI project (*.json)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            new_document = DesignDocument.from_dict(data)
        except (OSError, ValueError, TypeError, OverflowError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Could not open project", str(exc))
            return
        self._snapshot()
        self.document = new_document
        self._current_file = Path(path)
        self.selected_id = None
        self._revision += 1
        self._refresh_all()
        self.statusBar().showMessage(f"Opened {Path(path).name}", 3000)

    def export_python(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export generated Python", str(Path.home() / "generated_gui.py"), "Python source (*.py)")
        if not path:
            return
        if not path.lower().endswith(".py"):
            path += ".py"
        try:
            Path(path).write_text(generate_python(self.document), encoding="utf-8")
            self.statusBar().showMessage(f"Exported Python source to {path}", 4000)
        except OSError as exc:
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
            with target.open("xb") as image_file:
                image.save(image_file, format="PNG")
            try:
                with truth_target.open("x", encoding="utf-8") as truth_file:
                    truth_file.write(truth.strip())
            except FileExistsError:
                # The image was just created by this save; remove only that new file if a
                # competing writer created the label in the meantime.
                target.unlink(missing_ok=True)
                raise
            QMessageBox.information(self, "Sample saved", f"Saved image and expected text:\n{target}\n{target.with_suffix('.txt')}\n\nCollect the same set of samples before comparing OCR engines.")
        except Exception as exc:
            QMessageBox.critical(self, "Could not save sample", str(exc))

    def _refresh_all(self):
        self.canvas.set_document(self.document)
        self.canvas.set_selected(self.selected_id)
        self.preview.set_design(self.document, self.selected_id)
        self._refresh_code()
        self.undo_button.setEnabled(bool(self._undo_stack) and not self._busy)
        self.redo_button.setEnabled(bool(self._redo_stack) and not self._busy)
        self.delete_button.setEnabled(self.selected_id is not None and not self._busy)
        uncertain_count = sum(e.needs_review for e in self.document.elements)
        self.review_button.setText(f"{uncertain_count} to review")
        self.review_button.setEnabled(uncertain_count > 0)
        self.properties.set_element(next((e for e in self.document.elements if e.element_id == self.selected_id), None))

    def _refresh_code(self):
        self.code_editor.setPlainText(generate_python(self.document))

    def closeEvent(self, event):
        if self._busy:
            answer = QMessageBox.question(self, "Recognition in progress", "OCR is still running. Close the app anyway?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()
