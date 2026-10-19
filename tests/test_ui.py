import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton

from sketch2gui.models import Stroke, UIElement
from sketch2gui.ui.main_window import MainWindow


class MainWindowEditingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.element = UIElement("panel", 20, 30, 180, 90, confidence=0.3,
                                 alternatives=["button", "search_field"])
        self.window.document.elements = [self.element]
        self.window._refresh_all()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def test_component_type_edit_updates_review_preview_and_code(self):
        self.window.select_element(self.element.element_id)
        self.assertEqual(self.window.review_button.text(), "1 to review")

        index = self.window.properties.type_combo.findData("search_field")
        self.window.properties.type_combo.setCurrentIndex(index)

        updated = self.window.document.elements[0]
        self.assertEqual(updated.element_type, "search_field")
        self.assertTrue(updated.confirmed)
        self.assertEqual(self.window.review_button.text(), "0 to review")
        self.assertIsInstance(self.window.preview._widgets[0], QLineEdit)
        self.assertIn("QLineEdit", self.window.code_editor.toPlainText())

    def test_preview_click_selects_component_without_activating_it(self):
        button = UIElement("button", 20, 30, 180, 45, text="Run")
        self.window.document.elements = [button]
        self.window._refresh_all()
        self.window.resize(1280, 800)
        self.window.show()
        self.app.processEvents()
        preview_button = self.window.preview._widgets[0]
        activations = []
        preview_button.clicked.connect(lambda: activations.append(True))

        QTest.mouseClick(preview_button, Qt.MouseButton.LeftButton)

        self.assertEqual(self.window.selected_id, button.element_id)
        self.assertEqual(activations, [])

    def test_review_button_cycles_through_uncertain_components(self):
        second = UIElement("button", 240, 30, 130, 42, confidence=0.4)
        self.window.document.elements.append(second)
        self.window._refresh_all()

        self.window.review_button.click()
        self.assertEqual(self.window.selected_id, self.element.element_id)
        self.window.review_button.click()
        self.assertEqual(self.window.selected_id, second.element_id)

    def test_paddle_is_default_when_both_optional_packages_are_available(self):
        from sketch2gui.ui import main_window

        with patch.object(main_window.importlib.util, "find_spec", side_effect=[object(), object()]):
            window = MainWindow()
        try:
            self.assertEqual(window.engine_combo.currentData(), "paddle")
        finally:
            window.close()

    def test_text_and_placeholder_edits_update_the_preview_and_generated_source(self):
        button = UIElement("button", 20, 30, 180, 45, text="Submit")
        self.window.document.elements = [button]
        self.window._refresh_all()
        self.window.select_element(button.element_id)
        self.window.properties.text_edit.setText("Continue")
        self.window.properties.text_edit.editingFinished.emit()

        self.assertEqual(self.window.document.elements[0].text, "Continue")
        self.assertEqual(self.window.preview._widgets[0].text(), "Continue")
        self.assertIn("Continue", self.window.code_editor.toPlainText())

        search = UIElement("search_field", 20, 90, 180, 36, placeholder="Search")
        self.window.document.elements = [search]
        self.window._refresh_all()
        self.window.select_element(search.element_id)
        self.window.properties.placeholder_edit.setText("Find accounts")
        self.window.properties.placeholder_edit.editingFinished.emit()
        self.assertEqual(self.window.preview._widgets[0].placeholderText(), "Find accounts")
        self.assertIn("Find accounts", self.window.code_editor.toPlainText())

    def test_delete_button_removes_selected_component_and_undo_restores_it(self):
        self.window.select_element(self.element.element_id)
        self.assertTrue(self.window.delete_button.isEnabled())

        self.window.delete_button.click()
        self.assertEqual(self.window.document.elements, [])
        self.assertTrue(self.window.undo_button.isEnabled())

        self.window.undo_button.click()
        self.assertEqual(len(self.window.document.elements), 1)
        self.assertEqual(self.window.document.elements[0].element_id, self.element.element_id)
        self.assertTrue(self.window.redo_button.isEnabled())
        self.window.redo_button.click()
        self.assertEqual(self.window.document.elements, [])
        self.window.undo_button.click()
        self.assertEqual(len(self.window.document.elements), 1)

    def test_save_open_and_export_file_actions_preserve_the_design(self):
        self.window.document.strokes = [Stroke([(10, 15), (25, 30)], stroke_id="original-stroke")]
        self.window.document.elements = [UIElement(
            "button", 40, 50, 140, 42, text="Open project", confirmed=True,
            user_modified=True, source_stroke_ids=["original-stroke"],
        )]
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            project_path = Path(folder) / "smoke-project.json"
            with patch("sketch2gui.ui.main_window.QFileDialog.getSaveFileName",
                       return_value=(str(project_path), "")):
                self.window.save_project()
            saved = json.loads(project_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["strokes"][0]["id"], "original-stroke")
            self.assertTrue(saved["elements"][0]["user_modified"])

            self.window.document.elements.clear()
            self.window._refresh_all()
            with patch("sketch2gui.ui.main_window.QFileDialog.getOpenFileName",
                       return_value=(str(project_path), "")):
                self.window.open_project()
            self.assertEqual(len(self.window.document.elements), 1)
            self.assertEqual(self.window.document.strokes[0].stroke_id, "original-stroke")

            python_path = Path(folder) / "generated_gui.py"
            with patch("sketch2gui.ui.main_window.QFileDialog.getSaveFileName",
                       return_value=(str(python_path), "")):
                self.window.export_python()
            exported = python_path.read_text(encoding="utf-8")
            compile(exported, str(python_path), "exec")
            self.assertIn("Open project", exported)

    def test_malformed_project_does_not_replace_the_current_design(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            project_path = Path(folder) / "malformed.json"
            project_path.write_text('{"format":"sketch2gui","elements":{}}', encoding="utf-8")
            with patch("sketch2gui.ui.main_window.QFileDialog.getOpenFileName",
                       return_value=(str(project_path), "")), \
                 patch("sketch2gui.ui.main_window.QMessageBox.critical") as show_error:
                self.window.open_project()

            show_error.assert_called_once()
            self.assertEqual(len(self.window.document.elements), 1)
            self.assertEqual(self.window.document.elements[0].element_id, self.element.element_id)

    def test_sample_capture_does_not_overwrite_existing_image_or_truth(self):
        self.window.document.strokes = [Stroke([(10, 10), (50, 40)])]
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            image_path = Path(folder) / "existing.png"
            truth_path = image_path.with_suffix(".txt")
            Image.new("RGB", (8, 8), "white").save(image_path)
            original_image = image_path.read_bytes()
            truth_path.write_text("Original label", encoding="utf-8")
            with patch("sketch2gui.ui.main_window.QInputDialog.getText",
                       return_value=("Replacement label", True)), \
                 patch("sketch2gui.ui.main_window.QFileDialog.getSaveFileName",
                       return_value=(str(image_path), "")), \
                 patch("sketch2gui.ui.main_window.QMessageBox.critical") as show_error:
                self.window.save_ocr_sample()

            show_error.assert_called_once()
            self.assertEqual(image_path.read_bytes(), original_image)
            self.assertEqual(truth_path.read_text(encoding="utf-8"), "Original label")

    def test_interpret_button_turns_canvas_strokes_into_reviewable_suggestions(self):
        self.window.document.elements = []
        self.window._refresh_all()
        self.window.resize(1280, 800)
        self.window.show()
        self.app.processEvents()
        canvas = self.window.canvas
        scale, offset_x, offset_y = canvas._canvas_transform()
        design_points = [
            (40, 40), (90, 40), (140, 40), (180, 40),
            (180, 60), (180, 90), (180, 110),
            (140, 110), (90, 110), (40, 110),
            (40, 90), (40, 60), (40, 40),
        ]
        canvas_points = [QPoint(round(offset_x + x * scale), round(offset_y + y * scale))
                         for x, y in design_points]
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=canvas_points[0])
        for point in canvas_points[1:-1]:
            QTest.mouseMove(canvas, point, 1)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=canvas_points[-1])
        self.app.processEvents()

        self.assertEqual(len(self.window.document.strokes), 1)
        self.window.interpret_button.click()

        self.assertEqual(len(self.window.document.elements), 1)
        self.assertTrue(self.window.document.elements[0].needs_review)
        self.assertEqual(self.window.review_button.text(), "1 to review")

    def test_canvas_click_selects_but_drag_inside_component_draws(self):
        self.window.resize(1280, 800)
        self.window.show()
        self.app.processEvents()
        canvas = self.window.canvas
        scale, offset_x, offset_y = canvas._canvas_transform()
        to_canvas = lambda x, y: QPoint(round(offset_x + x * scale), round(offset_y + y * scale))

        QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=to_canvas(80, 75))
        self.assertEqual(self.window.selected_id, self.element.element_id)
        self.assertEqual(self.window.document.strokes, [])

        start = to_canvas(60, 60)
        middle = to_canvas(85, 65)
        end = to_canvas(110, 70)
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(canvas, middle, 1)
        QTest.mouseMove(canvas, end, 1)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
        self.app.processEvents()
        self.assertEqual(len(self.window.document.strokes), 1)

        QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=to_canvas(300, 300))
        self.assertIsNone(self.window.selected_id)
        self.assertEqual(len(self.window.document.strokes), 1)


if __name__ == "__main__":
    unittest.main()
