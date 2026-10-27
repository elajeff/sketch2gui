import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QMessageBox, QPushButton, QTableWidget

from sketch2gui.models import DEFAULT_DROPDOWN_OPTIONS, DesignDocument, Stroke, UIElement
from sketch2gui.ui.main_window import MainWindow, _read_project_file


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
        # Explicitly destroy each top-level Qt window before the shared
        # QApplication is torn down at interpreter exit. close() alone
        # only hides a QWidget unless WA_DeleteOnClose is enabled.
        window = self.window
        # Tests may intentionally leave edits unsaved; don't open a modal dialog in teardown.
        window._saved_state = window._serialize()
        window.close()
        window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.window = None

    def test_preview_dropdown_uses_shared_default_options(self):
        dropdown = UIElement("dropdown", 20, 30, 180, 40)
        self.window.document.elements = [dropdown]
        self.window._refresh_all()

        preview_dropdown = self.window.preview._widgets[0]
        self.assertIsInstance(preview_dropdown, QComboBox)
        self.assertEqual(
            [preview_dropdown.itemText(index) for index in range(preview_dropdown.count())],
            list(DEFAULT_DROPDOWN_OPTIONS),
        )

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

        with patch.object(main_window.importlib.util, "find_spec", return_value=object()):
            window = MainWindow()
        try:
            self.assertEqual(window.engine_combo.currentData(), "paddle")
        finally:
            window.close()
            window.deleteLater()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()

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
            with patch("sketch2gui.ui.main_window.QMessageBox.warning",
                       return_value=QMessageBox.StandardButton.Discard):
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

    def test_open_project_cancel_preserves_unsaved_changes(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            project_path = Path(folder) / "replacement.json"
            replacement = DesignDocument(elements=[UIElement("button", 10, 20, 120, 36, text="Replacement")])
            project_path.write_text(json.dumps(replacement.to_dict()), encoding="utf-8")

            with patch("sketch2gui.ui.main_window.QFileDialog.getOpenFileName",
                       return_value=(str(project_path), "")):
                with patch("sketch2gui.ui.main_window.QMessageBox.warning",
                           return_value=QMessageBox.StandardButton.Cancel):
                    self.window.open_project()

        self.assertEqual([item.element_id for item in self.window.document.elements], [self.element.element_id])
        self.assertTrue(self.window._has_unsaved_changes())

    def test_open_project_discard_replaces_unsaved_changes(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            project_path = Path(folder) / "replacement.json"
            replacement = DesignDocument(elements=[UIElement("button", 10, 20, 120, 36, text="Replacement")])
            project_path.write_text(json.dumps(replacement.to_dict()), encoding="utf-8")

            with patch("sketch2gui.ui.main_window.QFileDialog.getOpenFileName",
                       return_value=(str(project_path), "")):
                with patch("sketch2gui.ui.main_window.QMessageBox.warning",
                           return_value=QMessageBox.StandardButton.Discard):
                    self.window.open_project()

        self.assertEqual(len(self.window.document.elements), 1)
        self.assertEqual(self.window.document.elements[0].text, "Replacement")
        self.assertFalse(self.window._has_unsaved_changes())

    def test_close_can_be_cancelled_when_changes_are_unsaved(self):
        event = QCloseEvent()
        with patch("sketch2gui.ui.main_window.QMessageBox.warning",
                   return_value=QMessageBox.StandardButton.Cancel):
            self.window.closeEvent(event)

        self.assertFalse(event.isAccepted())
        self.assertTrue(self.window._has_unsaved_changes())

    def test_close_can_save_unsaved_changes_before_exiting(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            project_path = Path(folder) / "save-before-close.json"
            event = QCloseEvent()
            with patch("sketch2gui.ui.main_window.QMessageBox.warning",
                       return_value=QMessageBox.StandardButton.Save):
                with patch("sketch2gui.ui.main_window.QFileDialog.getSaveFileName",
                           return_value=(str(project_path), "")):
                    self.window.closeEvent(event)

            self.assertTrue(event.isAccepted())
            self.assertTrue(project_path.is_file())
            self.assertFalse(self.window._has_unsaved_changes())

    def test_oversized_project_is_rejected_before_json_parsing(self):
        with tempfile.TemporaryDirectory() as folder:
            project_path = Path(folder) / "oversized.json"
            project_path.write_text("{}", encoding="utf-8")
            with patch("sketch2gui.ui.main_window.MAX_PROJECT_FILE_BYTES", 1):
                with self.assertRaisesRegex(ValueError, "size limit"):
                    _read_project_file(project_path)

    def test_oversized_save_preserves_existing_file_and_unsaved_design(self):
        with tempfile.TemporaryDirectory() as folder:
            project_path = Path(folder) / "existing.json"
            project_path.write_text("original", encoding="utf-8")
            previous_name = self.window.document.name
            with patch("sketch2gui.ui.main_window.MAX_PROJECT_FILE_BYTES", 1), \
                 patch("sketch2gui.ui.main_window.QFileDialog.getSaveFileName",
                       return_value=(str(project_path), "")), \
                 patch("sketch2gui.ui.main_window.QMessageBox.critical") as error:
                self.assertFalse(self.window.save_project())
            self.assertEqual(project_path.read_text(encoding="utf-8"), "original")
            self.assertEqual(self.window.document.name, previous_name)
            self.assertTrue(self.window._has_unsaved_changes())
            error.assert_called_once()

    def test_deeply_nested_project_json_is_rejected_clearly(self):
        with tempfile.TemporaryDirectory() as folder:
            project_path = Path(folder) / "deeply-nested.json"
            project_path.write_text("[" * 1100 + "0" + "]" * 1100, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "nested too deeply"):
                _read_project_file(project_path)

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

    def test_new_freehand_stroke_updates_preview_without_interpretation(self):
        self.window.document.elements = []
        self.window._refresh_all()
        stroke = Stroke([(80, 100), (180, 100)], width=3.0)
        self.window.add_stroke(stroke)
        self.assertEqual(self.window.preview.document.strokes, [stroke])
        self.assertIn("self._sketch_strokes", self.window.code_editor.toPlainText())

    def test_freehand_release_without_intermediate_mouse_move_updates_generated_code(self):
        self.window.document.elements = []
        self.window._refresh_all()
        code_before = self.window.code_editor.toPlainText()
        self.window.resize(1280, 800)
        self.window.show()
        self.app.processEvents()

        # Deliberately send press/release only, without a mouse-move event.
        QTest.mousePress(self.window.canvas, Qt.MouseButton.LeftButton, pos=QPoint(45, 45))
        QTest.mouseRelease(self.window.canvas, Qt.MouseButton.LeftButton, pos=QPoint(170, 130))
        self.app.processEvents()

        self.assertEqual(len(self.window.document.strokes), 1)
        generated = self.window.code_editor.toPlainText()
        self.assertNotEqual(generated, code_before)
        self.assertIn("self._sketch_strokes = [", generated)

    def test_adding_a_stroke_preserves_existing_preview_controls(self):
        button = UIElement("button", 30, 40, 140, 42, text="Keep me")
        self.window.document.elements = [button]
        self.window._refresh_all()
        original_widget = self.window.preview._widgets[0]

        self.window.add_stroke(Stroke([(80, 100), (180, 100)]))

        self.assertIs(self.window.preview._widgets[0], original_widget)
        self.assertEqual(self.window.preview.document.strokes, self.window.document.strokes)
        self.assertEqual(self.window.preview._widgets[0].text(), "Keep me")

    def test_failed_ocr_sample_write_leaves_no_partial_files(self):
        self.window.document.strokes = [Stroke([(10, 10), (50, 40)])]
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            image_path = Path(folder) / "failed-sample.png"
            broken_image = Mock()
            broken_image.save.side_effect = OSError("disk full")
            with patch("sketch2gui.ui.main_window.QInputDialog.getText",
                       return_value=("Sample label", True)), \
                 patch("sketch2gui.ui.main_window.QFileDialog.getSaveFileName",
                       return_value=(str(image_path), "")), \
                 patch("sketch2gui.ui.main_window.render_strokes", return_value=broken_image), \
                 patch("sketch2gui.ui.main_window.QMessageBox.critical") as show_error:
                self.window.save_ocr_sample()

            show_error.assert_called_once()
            self.assertFalse(image_path.exists())
            self.assertFalse(image_path.with_suffix(".txt").exists())

    def test_recognition_busy_state_disables_review_button(self):
        self.window.document.elements = [
            UIElement("button", 20, 30, 120, 40, confidence=0.4)
        ]
        self.window._refresh_all()
        self.assertTrue(self.window.review_button.isEnabled())

        self.window._set_recognition_busy(True)
        self.assertFalse(self.window.review_button.isEnabled())

        self.window._set_recognition_busy(False)
        self.window._refresh_all()
        self.assertTrue(self.window.review_button.isEnabled())

    def test_freehand_art_is_visible_in_preview(self):
        self.window.document.elements = []
        self.window.document.strokes = [Stroke([(80, 100), (180, 100)], width=3.0)]
        self.window._refresh_all()
        self.window.resize(1280, 800)
        self.window.show()
        self.app.processEvents()

        preview = self.window.preview
        image = preview.grab().toImage()
        scale = min(
            image.width() / max(self.window.document.width, 1),
            image.height() / max(self.window.document.height, 1),
        )
        offset_x = max(0, round((image.width() - self.window.document.width * scale) / 2))
        offset_y = max(0, round((image.height() - self.window.document.height * scale) / 2))
        pixel = image.pixelColor(round(offset_x + 130 * scale), round(offset_y + 100 * scale))
        self.assertLess(max(pixel.red(), pixel.green(), pixel.blue()), 150)

    def test_shape_tool_creates_a_button_without_recognition(self):
        self.window.document.elements = []
        self.window._refresh_all()
        self.window.resize(1280, 800)
        self.window.show()
        self.app.processEvents()
        index = self.window.drawing_tool_combo.findData("button")
        self.window.drawing_tool_combo.setCurrentIndex(index)
        canvas = self.window.canvas
        scale_x, scale_y, offset_x, offset_y = canvas._canvas_transform()
        start = QPoint(round(offset_x + 40 * scale_x), round(offset_y + 50 * scale_y))
        end = QPoint(round(offset_x + 180 * scale_x), round(offset_y + 95 * scale_y))
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(canvas, QPoint(start.x() + 35, start.y() + 12), 1)
        QTest.mouseMove(canvas, end, 1)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
        self.app.processEvents()

        self.assertEqual(len(self.window.document.elements), 1)
        self.assertEqual(self.window.document.elements[0].element_type, "button")
        self.assertTrue(self.window.document.elements[0].confirmed)
        self.assertIn("Button", self.window.code_editor.toPlainText())
        self.assertIsInstance(self.window.preview._widgets[0], QPushButton)

    def test_shape_tool_uses_release_position_without_intermediate_mouse_move(self):
        self.window.document.elements = []
        self.window._refresh_all()
        self.window.resize(1280, 800)
        self.window.show()
        self.app.processEvents()
        self.window.drawing_tool_combo.setCurrentIndex(
            self.window.drawing_tool_combo.findData("button")
        )
        canvas = self.window.canvas
        scale_x, scale_y, offset_x, offset_y = canvas._canvas_transform()
        start = QPoint(round(offset_x + 40 * scale_x), round(offset_y + 50 * scale_y))
        end = QPoint(round(offset_x + 180 * scale_x), round(offset_y + 95 * scale_y))
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
        self.app.processEvents()

        self.assertEqual(len(self.window.document.elements), 1)
        element = self.window.document.elements[0]
        self.assertEqual(element.element_type, "button")
        self.assertGreater(element.width, 100)
        self.assertGreater(element.height, 30)
        self.assertIn("QPushButton('Button'", self.window.code_editor.toPlainText())

    def test_component_move_uses_release_position_without_intermediate_mouse_move(self):
        self.window.resize(1280, 800)
        self.window.show()
        self.app.processEvents()
        self.window.drawing_tool_combo.setCurrentIndex(
            self.window.drawing_tool_combo.findData("select")
        )
        canvas = self.window.canvas
        sx, sy, ox, oy = canvas._canvas_transform()
        start = QPoint(round(80 * sx + ox), round(70 * sy + oy))
        end = QPoint(round(130 * sx + ox), round(100 * sy + oy))
        old_x, old_y = self.element.x, self.element.y
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
        self.app.processEvents()

        self.assertGreater(self.element.x, old_x)
        self.assertGreater(self.element.y, old_y)

    def test_component_resize_uses_release_position_without_intermediate_mouse_move(self):
        self.window.resize(1280, 800)
        self.window.show()
        self.app.processEvents()
        self.window.drawing_tool_combo.setCurrentIndex(
            self.window.drawing_tool_combo.findData("select")
        )
        canvas = self.window.canvas
        sx, sy, ox, oy = canvas._canvas_transform()
        start = QPoint(round((self.element.x + self.element.width) * sx + ox),
                       round((self.element.y + self.element.height) * sy + oy))
        end = QPoint(round(240 * sx + ox), round(150 * sy + oy))
        old_width, old_height = self.element.width, self.element.height
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
        self.app.processEvents()

        self.assertGreater(self.element.width, old_width)
        self.assertGreater(self.element.height, old_height)

    def test_line_tool_creates_horizontal_and_vertical_components(self):
        self.window.document.elements = []
        self.window._refresh_all()
        self.window.resize(1280, 800)
        self.window.show()
        self.app.processEvents()
        self.window.drawing_tool_combo.setCurrentIndex(
            self.window.drawing_tool_combo.findData("line")
        )
        canvas = self.window.canvas
        sx, sy, ox, oy = canvas._canvas_transform()
        to_canvas = lambda x, y: QPoint(round(x * sx + ox), round(y * sy + oy))

        for start_point, end_point in (((40, 50), (160, 50)), ((220, 60), (220, 180))):
            QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=to_canvas(*start_point))
            QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=to_canvas(*end_point))
        self.app.processEvents()

        lines = self.window.document.elements
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(element.element_type == "line" for element in lines))
        self.assertGreater(lines[0].width, lines[0].height)
        self.assertGreater(lines[1].height, lines[1].width)
        source = self.window.code_editor.toPlainText()
        self.assertIn("QFrame.Shape.HLine", source)
        self.assertIn("QFrame.Shape.VLine", source)

    def test_converting_component_to_table_keeps_cell_edits_safe(self):
        self.window.select_element(self.element.element_id)
        self.window.change_element_property("element_type", "table")
        table = self.window.document.elements[0]
        self.assertEqual(table.element_type, "table")
        self.assertEqual(len(table.table_cells), table.table_rows)
        self.assertEqual(len(table.table_cells[0]), table.table_columns)
        self.assertIsInstance(self.window.preview._widgets[0], QTableWidget)

        self.window.update_table_cell(table.element_id, 0, 0, "Name")
        self.assertEqual(table.table_cells[0][0], "Name")
        self.assertIn("QTableWidgetItem('Name')", self.window.code_editor.toPlainText())

    def test_inline_text_field_edit_updates_model_preview_and_code(self):
        field = UIElement("text_field", 30, 40, 180, 38, placeholder="Enter text...")
        self.window.document.elements = [field]
        self.window._refresh_all()
        widget = self.window.preview._widgets[0]
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
        self.assertFalse(widget.isReadOnly())
        QTest.keyClicks(widget, "Search records")
        QTest.keyClick(widget, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.window.document.elements[0].text, "Search records")
        self.assertIn("setText('Search records')", self.window.code_editor.toPlainText())
        self.assertEqual(self.window.preview._widgets[0].text(), "Search records")

    def test_chart_values_edit_drives_preview_and_generated_code(self):
        chart = UIElement("chart", 30, 40, 300, 180)
        self.window.document.elements = [chart]
        self.window._refresh_all()
        self.window.select_element(chart.element_id)
        editor = self.window.properties.chart_values_edit
        editor.setText("2, 9, 4")
        editor.editingFinished.emit()
        self.assertEqual(self.window.document.elements[0].chart_values, [2.0, 9.0, 4.0])
        self.assertEqual(self.window.preview._widgets[0].values, [2.0, 9.0, 4.0])
        self.assertIn("ChartWidget([2.0, 9.0, 4.0], self)", self.window.code_editor.toPlainText())

        editor.setText("1e308, -1e308, 0")
        editor.editingFinished.emit()
        self.app.processEvents()
        self.window.preview._widgets[0].grab()
        self.window.canvas.grab()
        self.assertEqual(
            self.window.document.elements[0].chart_values, [1e308, -1e308, 0.0]
        )

    def test_canvas_select_tool_moves_and_resizes_component(self):
        component = UIElement("button", 40, 40, 100, 50, text="Move me", confirmed=True)
        self.window.document.elements = [component]
        self.window._refresh_all()
        self.window.resize(1280, 800)
        self.window.show()
        self.app.processEvents()
        self.window.drawing_tool_combo.setCurrentIndex(self.window.drawing_tool_combo.findData("select"))
        self.app.processEvents()
        canvas = self.window.canvas
        sx, sy, ox, oy = canvas._canvas_transform()
        point = lambda x, y: QPoint(round(ox + x * sx), round(oy + y * sy))
        start = point(80, 60)
        end = point(115, 83)
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(canvas, end, 10)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
        self.app.processEvents()
        self.assertEqual((component.x, component.y), (80.0, 60.0))

        start = point(component.x + component.width, component.y + component.height)
        end = point(component.x + component.width + 27, component.y + component.height + 21)
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(canvas, end, 10)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
        self.app.processEvents()
        self.assertGreaterEqual(component.width, 120.0)
        self.assertGreaterEqual(component.height, 60.0)

    def test_undo_preserves_code_editor_scroll_and_cursor(self):
        self.window.document.elements = [
            UIElement("button", 10, 10 + index * 6, 150, 30, text=f"Button {index}")
            for index in range(70)
        ]
        self.window.resize(1280, 800)
        self.window.show()
        self.window._refresh_all()
        self.app.processEvents()
        editor = self.window.code_editor
        self.assertGreater(editor.verticalScrollBar().maximum(), 15)

        # Capture a useful place in the generated source, then make an undoable edit.
        editor.verticalScrollBar().setValue(15)
        cursor = editor.textCursor()
        cursor.setPosition(min(120, len(editor.toPlainText())))
        editor.setTextCursor(cursor)
        editor.verticalScrollBar().setValue(15)
        expected_position = editor.textCursor().position()
        expected_scroll = editor.verticalScrollBar().value()

        self.window._snapshot()
        self.window.document.elements.append(UIElement("button", 10, 500, 150, 30, text="Added later"))
        self.window._refresh_all()
        self.app.processEvents()
        editor.verticalScrollBar().setValue(expected_scroll)

        self.window.undo()
        self.app.processEvents()
        self.assertEqual(editor.verticalScrollBar().value(), expected_scroll)
        self.assertEqual(editor.textCursor().position(), expected_position)
        self.assertNotIn("Added later", editor.toPlainText())

    def test_property_edits_stay_inside_canvas_and_confirm_component(self):
        component = UIElement("button", 770, 580, 20, 20, confidence=0.3, alternatives=["panel"])
        self.window.document.elements = [component]
        self.window.selected_id = component.element_id
        self.window.selected_ids = {component.element_id}
        self.window._refresh_all()

        self.window.change_element_property("width", 5000)
        self.assertLessEqual(component.x + component.width, self.window.document.width)
        self.assertLessEqual(component.y + component.height, self.window.document.height)
        self.assertEqual(component.width, 30)
        self.assertFalse(component.needs_review)

        self.window.change_element_property("x", 5000)
        self.window.change_element_property("y", 5000)
        self.assertLessEqual(component.x + component.width, self.window.document.width)
        self.assertLessEqual(component.y + component.height, self.window.document.height)

    def test_unknown_property_does_not_create_undo_history(self):
        self.window.select_element(self.element.element_id)
        before_undo = list(self.window._undo_stack)
        before_redo = list(self.window._redo_stack)
        self.window.change_element_property("not_a_real_property", "value")
        self.assertEqual(self.window._undo_stack, before_undo)
        self.assertEqual(self.window._redo_stack, before_redo)

    def test_duplicate_alignment_and_move_resize(self):
        first = UIElement("button", 20, 30, 100, 40, text="One", confirmed=True)
        second = UIElement("button", 180, 100, 100, 40, text="Two", confirmed=True)
        self.window.document.elements = [first, second]
        self.window._refresh_all()
        self.window.select_element(first.element_id)
        self.window.toggle_selected_element(second.element_id)
        self.window.align_combo.setCurrentIndex(self.window.align_combo.findData("left"))
        self.window.align_selected_elements()
        self.assertEqual(self.window.document.elements[1].x, self.window.document.elements[0].x)

        self.window.commit_element_geometry(first.element_id, 40, 50, 130, 45)
        self.assertEqual((first.x, first.y, first.width, first.height), (40.0, 50.0, 130.0, 45.0))
        self.window.select_element(first.element_id)
        self.window.duplicate_selected_elements()
        self.assertEqual(len(self.window.document.elements), 3)
        self.assertEqual(len({item.element_id for item in self.window.document.elements}), len(self.window.document.elements))
        self.assertNotEqual(self.window.document.elements[-1].element_id, first.element_id)

    def test_no_op_alignment_preserves_redo_history(self):
        first = UIElement("button", 20, 30, 100, 40, text="One", confirmed=True, user_modified=True)
        second = UIElement("button", 20, 100, 100, 40, text="Two", confirmed=True, user_modified=True)
        self.window.document.elements = [first, second]
        self.window._refresh_all()
        self.window.select_element(first.element_id)
        self.window.toggle_selected_element(second.element_id)
        self.window.align_combo.setCurrentIndex(self.window.align_combo.findData("left"))
        self.window._snapshot()
        second.x = 30
        self.window._refresh_all()
        self.window.undo()
        self.window.select_element(first.element_id)
        self.window.toggle_selected_element(second.element_id)
        redo_before = list(self.window._redo_stack)

        self.window.align_selected_elements()

        self.assertEqual(self.window._redo_stack, redo_before)
        self.assertEqual([element.x for element in self.window.document.elements], [20.0, 20.0])

    def test_table_configuration_and_cell_edits_update_model_and_code(self):
        table = UIElement("table", 10, 10, 220, 120)
        self.window.document.elements = [table]
        self.window._refresh_all()
        self.window.select_element(table.element_id)
        self.window.change_element_property("table_rows", 2)
        self.window.change_element_property("table_columns", 2)
        self.window.update_table_cell(table.element_id, 0, 0, "Name")
        self.assertEqual((table.table_rows, table.table_columns), (2, 2))
        self.assertEqual(table.table_cells[0][0], "Name")
        self.assertIn("QTableWidget(2, 2, self)", self.window.code_editor.toPlainText())
        self.assertIn("QTableWidgetItem('Name')", self.window.code_editor.toPlainText())

    def test_interpret_button_turns_canvas_strokes_into_reviewable_suggestions(self):
        self.window.document.elements = []
        self.window._refresh_all()
        # Force geometry-only mode to keep the test deterministic and avoid
        # downloading OCR models. Interpretation uses the same background worker.
        self.window.engine_combo.setCurrentIndex(0)
        self.window.resize(1280, 800)
        self.window.show()
        self.app.processEvents()
        canvas = self.window.canvas
        scale_x, scale_y, offset_x, offset_y = canvas._canvas_transform()
        design_points = [
            (40, 40), (90, 40), (140, 40), (180, 40),
            (180, 60), (180, 90), (180, 110),
            (140, 110), (90, 110), (40, 110),
            (40, 90), (40, 60), (40, 40),
        ]
        canvas_points = [QPoint(round(offset_x + x * scale_x), round(offset_y + y * scale_y))
                         for x, y in design_points]
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=canvas_points[0])
        for point in canvas_points[1:-1]:
            QTest.mouseMove(canvas, point, 1)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=canvas_points[-1])
        self.app.processEvents()

        self.assertEqual(len(self.window.document.strokes), 1)
        self.window.engine_combo.setCurrentIndex(self.window.engine_combo.findData("off"))
        self.window.interpret_button.click()

        # Interpretation runs in a worker. Process Qt events until its completion
        # callback has updated the document, rather than asserting before it returns.
        for _ in range(500):
            self.app.processEvents()
            if self.window.document.elements and not self.window._busy:
                break
            QTest.qWait(10)
        self.app.processEvents()
        self.assertFalse(self.window._busy, "Interpretation did not finish within 5 seconds")
        self.assertEqual(len(self.window.document.elements), 1)
        self.assertTrue(self.window.document.elements[0].needs_review)
        self.assertEqual(self.window.review_button.text(), "1 to review")

    def test_canvas_click_selects_but_drag_inside_component_draws(self):
        self.window.resize(1280, 800)
        self.window.show()
        self.app.processEvents()
        canvas = self.window.canvas
        scale_x, scale_y, offset_x, offset_y = canvas._canvas_transform()
        to_canvas = lambda x, y: QPoint(round(offset_x + x * scale_x), round(offset_y + y * scale_y))

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
