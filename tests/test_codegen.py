import ast
import unittest
from sketch2gui.codegen import generate_python
from sketch2gui.models import DesignDocument, UIElement


class CodeGenerationTests(unittest.TestCase):
    def test_empty_document_generates_valid_standalone_source(self):
        source = generate_python(DesignDocument())
        ast.parse(source)
        self.assertIn("QApplication(sys.argv)", source)
        self.assertIn("window.show()", source)

    def test_all_supported_element_types_generate_valid_code(self):
        types = ["button", "text_field", "search_field", "label", "checkbox", "dropdown", "table", "panel", "radio_button", "line"]
        elements = [UIElement(kind, 10+i*3, 20+i*2, 140, 40, text='O\'Reilly "form"') for i, kind in enumerate(types)]
        source = generate_python(DesignDocument(elements=elements))
        ast.parse(source)
        for widget_type in ("QPushButton", "QLineEdit", "QLabel", "QCheckBox", "QComboBox", "QTableWidget", "QFrame", "QRadioButton"):
            self.assertIn(widget_type, source)

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
