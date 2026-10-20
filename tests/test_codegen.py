import ast
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import (
    QApplication, QPushButton, QLineEdit, QLabel, QCheckBox, QComboBox,
    QTableWidget, QRadioButton, QFrame, QWidget,
)

from sketch2gui.codegen import generate_python
from sketch2gui.models import DesignDocument, Stroke, UIElement


class CodeGenerationTests(unittest.TestCase):
    def test_empty_document_generates_valid_standalone_source(self):
        source = generate_python(DesignDocument())
        ast.parse(source)
        self.assertIn("QApplication(sys.argv)", source)
        self.assertIn("window.show()", source)

    def test_all_supported_element_types_generate_valid_code(self):
        types = ["button", "text_field", "search_field", "label", "checkbox", "dropdown", "table", "panel", "radio_button", "line", "chart", "ellipse"]
        elements = [UIElement(kind, 10+i*3, 20+i*2, 140, 40, text='O\'Reilly "form"') for i, kind in enumerate(types)]
        source = generate_python(DesignDocument(elements=elements))
        ast.parse(source)
        for widget_type in ("QPushButton", "QLineEdit", "QLabel", "QCheckBox", "QComboBox", "QTableWidget", "QFrame", "QRadioButton"):
            self.assertIn(widget_type, source)

    def test_export_preserves_original_freehand_strokes(self):
        from sketch2gui.models import Stroke
        document = DesignDocument(strokes=[Stroke([(12, 18), (24, 35), (39, 22)], width=3.5)])
        source = generate_python(document)
        ast.parse(source)
        self.assertIn("self._sketch_strokes", source)
        self.assertIn("QPainterPath", source)
        self.assertIn("(12.0, 18.0)", source)

    def test_generated_window_renders_freehand_strokes(self):
        app = QApplication.instance() or QApplication([])
        document = DesignDocument(
            width=300,
            height=200,
            strokes=[Stroke([(30, 30), (60, 60), (90, 30)], width=4)],
        )
        namespace = {"__name__": "generated_window_test"}
        source = generate_python(document)
        exec(compile(source, "<generated-window>", "exec"), namespace)
        window = namespace["GeneratedWindow"]()

        try:
            window.show()
            app.processEvents()
            image = QImage(window.size(), QImage.Format.Format_ARGB32)
            image.fill(QColor("white"))
            window.render(image)

            self.assertNotEqual(image.pixelColor(45, 45), QColor("white"))
            self.assertEqual(image.pixelColor(150, 150), QColor("white"))
        finally:
            window.close()
            window.deleteLater()
            app.processEvents()

    def test_generated_mixed_gui_instantiates_widgets_and_renders_strokes(self):
        app = QApplication.instance() or QApplication([])
        document = DesignDocument(
            width=800,
            height=600,
            strokes=[Stroke([(20, 25), (40, 25), (60, 25)], width=4)],
            elements=[
                UIElement("button", 100, 80, 120, 36, text="Submit"),
                UIElement("text_field", 100, 130, 180, 32, text="Ada", placeholder="Name"),
                UIElement("search_field", 100, 175, 180, 32, placeholder="Search"),
                UIElement("label", 100, 220, 100, 25, text="Title"),
                UIElement("checkbox", 100, 260, 120, 28, text="Agree"),
                UIElement("dropdown", 230, 80, 130, 35),
                UIElement("radio_button", 230, 130, 120, 28, text="Option"),
                UIElement("table", 400, 40, 250, 120, table_rows=2,
                          table_columns=2, table_cells=[["Name", "Room"], ["Ada", "Lab"]]),
                UIElement("chart", 400, 190, 200, 120, chart_values=[2, 8, 4]),
                UIElement("ellipse", 650, 190, 80, 60),
                UIElement("panel", 350, 350, 180, 100),
                UIElement("line", 100, 330, 150, 8),
                UIElement("line", 300, 300, 8, 90),
            ],
        )
        source = generate_python(document)
        ast.parse(source)
        namespace = {"__name__": "generated_mixed_gui_test"}
        exec(compile(source, "<generated-mixed-gui>", "exec"), namespace)
        window = namespace["GeneratedWindow"]()

        try:
            window.show()
            app.processEvents()
            self.assertEqual(window.findChildren(QPushButton)[0].text(), "Submit")
            self.assertTrue(any(
                widget.text() == "Ada" and widget.placeholderText() == "Name"
                for widget in window.findChildren(QLineEdit)
            ))
            self.assertTrue(any(widget.text() == "Title" for widget in window.findChildren(QLabel)))
            self.assertTrue(any(widget.text() == "Agree" for widget in window.findChildren(QCheckBox)))
            self.assertEqual(window.findChildren(QComboBox)[0].count(), 3)
            self.assertTrue(any(widget.text() == "Option" for widget in window.findChildren(QRadioButton)))

            table = window.findChild(QTableWidget)
            self.assertIsNotNone(table)
            self.assertEqual((table.rowCount(), table.columnCount()), (2, 2))
            self.assertEqual(table.item(1, 0).text(), "Ada")
            chart = next(widget for widget in window.findChildren(QWidget)
                         if type(widget).__name__ == "ChartWidget")
            ellipse = next(widget for widget in window.findChildren(QWidget)
                           if type(widget).__name__ == "EllipseWidget")
            self.assertEqual(chart.values, [2.0, 8.0, 4.0])
            self.assertGreater(ellipse.width(), 0)
            line_shapes = {
                widget.frameShape() for widget in window.findChildren(QFrame)
                if widget.frameShape() in (QFrame.Shape.HLine, QFrame.Shape.VLine)
            }
            self.assertEqual(line_shapes, {QFrame.Shape.HLine, QFrame.Shape.VLine})

            image = QImage(window.size(), QImage.Format.Format_ARGB32)
            image.fill(QColor("white"))
            window.render(image)
            self.assertNotEqual(image.pixelColor(40, 25), QColor("white"))
            self.assertEqual(image.pixelColor(760, 550), QColor("white"))
        finally:
            window.close()
            window.deleteLater()
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()

    def test_chart_and_ellipse_generate_valid_source(self):
        elements = [UIElement("chart", 10, 10, 180, 90, chart_values=[2, 8, 4]), UIElement("ellipse", 220, 20, 80, 60)]
        source = generate_python(DesignDocument(elements=elements))
        ast.parse(source)
        self.assertIn("ChartWidget([2.0, 8.0, 4.0], self)", source)
        self.assertIn("Add 2+ values in Properties", source)
        self.assertIn("EllipseWidget(self)", source)

    def test_table_export_uses_configured_dimensions_and_cells(self):
        table = UIElement("table", 10, 10, 240, 150, table_rows=2, table_columns=2,
                          table_cells=[["Name", "Room"], ["Ada", "Lab 1"]])
        source = generate_python(DesignDocument(elements=[table]))
        ast.parse(source)
        self.assertIn("QTableWidget(2, 2, self)", source)
        self.assertIn("QTableWidgetItem('Ada')", source)

    def test_quotes_and_newlines_in_labels_are_escaped(self):
        element = UIElement("button", 0, 0, 100, 35, text="Find 'this'\nnow")
        source = generate_python(DesignDocument(elements=[element]))
        ast.parse(source)
        self.assertIn("Find 'this'\\nnow", source)

    def test_panel_is_created_before_other_widgets(self):
        panel = UIElement("panel", 0, 0, 500, 400)
        button = UIElement("button", 20, 20, 100, 35, text="Go")
        source = generate_python(DesignDocument(elements=[button, panel]))
        self.assertLess(source.index("QFrame(self)"), source.index("QPushButton('Go'"))
