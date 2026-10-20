import ast
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

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
