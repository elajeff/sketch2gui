import unittest
from types import SimpleNamespace
from sketch2gui.geometry import classify_stroke, recognize_sketch
from sketch2gui.models import DesignDocument, Stroke
from tests.helpers import rectangle, line, ellipse


class GeometryTests(unittest.TestCase):
    def test_rectangle_is_recognized(self):
        shape, confidence = classify_stroke(rectangle(20, 20, 250, 80))
        self.assertEqual(shape, "rectangle")
        self.assertGreaterEqual(confidence, 0.65)

    def test_ellipse_is_recognized(self):
        shape, confidence = classify_stroke(ellipse(100, 100, 45, 25))
        self.assertEqual(shape, "ellipse")
        self.assertGreater(confidence, 0.5)

    def test_straight_line_is_recognized(self):
        shape, confidence = classify_stroke(line(10, 30, 300, 33))
        self.assertEqual(shape, "line")
        self.assertGreater(confidence, 0.7)

    def test_short_straight_stroke_is_not_automatically_a_separator(self):
        self.assertIsNone(classify_stroke(line(20, 20, 28, 21)))

    def test_unclosed_scribble_is_not_forced_to_shape(self):
        scribble = Stroke([(10, 10), (40, 45), (20, 80), (60, 30), (15, 60)])
        self.assertIsNone(classify_stroke(scribble))

    def test_closed_rectangle_becomes_low_confidence_component(self):
        doc = DesignDocument(strokes=[rectangle(30, 30, 220, 75)])
        elements = recognize_sketch(doc)
        self.assertEqual(len(elements), 1)
        self.assertIn(elements[0].element_type, {"panel", "text_field"})
        self.assertTrue(elements[0].needs_review)

    def test_ambiguous_blank_rectangle_is_flagged_for_review(self):
        element = recognize_sketch(DesignDocument(strokes=[rectangle(20, 20, 180, 110)]))[0]
        self.assertTrue(element.needs_review)
        self.assertIn("button", element.alternatives)

    def test_empty_stroke_does_not_break_recognition(self):
        document = DesignDocument(strokes=[Stroke([]), rectangle(20, 20, 180, 110)])
        elements = recognize_sketch(document)
        self.assertEqual(len(elements), 1)

    def test_closed_rectangle_with_horizontal_and_vertical_divider_suggests_table(self):
        outer = rectangle(20, 20, 320, 180)
        dividers = [line(35, 100, 305, 100), line(170, 35, 170, 165)]
        elements = recognize_sketch(DesignDocument(strokes=[outer, *dividers]))
        outer_element = max(elements, key=lambda e: e.width * e.height)
        self.assertEqual(outer_element.element_type, "table")

    def test_multistroke_table_is_recognized_as_one_table(self):
        strokes = [
            line(50, 50, 250, 50), line(50, 150, 250, 150),
            line(50, 50, 50, 150), line(250, 50, 250, 150),
            line(150, 50, 150, 150), line(50, 100, 250, 100),
        ]
        elements = recognize_sketch(DesignDocument(strokes=strokes))
        tables = [element for element in elements if element.element_type == "table"]
        self.assertEqual(len(tables), 1)
        self.assertEqual(len(tables[0].source_stroke_ids), 6)
        self.assertFalse(any(element.element_type == "line" for element in elements))

    def test_four_separate_edges_are_recognized_as_a_box(self):
        strokes = [
            line(40, 40, 240, 40), line(40, 130, 240, 130),
            line(40, 40, 40, 130), line(240, 40, 240, 130),
        ]
        elements = recognize_sketch(DesignDocument(strokes=strokes))
        self.assertEqual(len(elements), 1)
        self.assertEqual(elements[0].element_type, "panel")
        self.assertTrue(elements[0].needs_review)
        self.assertIn("button", elements[0].alternatives)
        self.assertFalse(any(element.element_type == "table" for element in elements))

    def test_unrecognized_doodle_does_not_create_a_fake_panel(self):
        doodle = Stroke([(10, 20), (18, 13), (27, 20), (19, 28), (10, 20), (18, 13), (24, 17)])
        elements = recognize_sketch(DesignDocument(strokes=[doodle]))
        self.assertFalse(any(element.element_type == "panel" for element in elements))

    def test_two_horizontal_rules_suggest_table(self):
        outer = rectangle(20, 20, 320, 180)
        rules = [line(35, 70, 305, 70), line(35, 115, 305, 115)]
        elements = recognize_sketch(DesignDocument(strokes=[outer, *rules]))
        outer_element = max(elements, key=lambda e: e.width * e.height)
        self.assertEqual(outer_element.element_type, "table")
        self.assertIn("panel", outer_element.alternatives)

    def test_ocr_keyword_suggests_search_field(self):
        outer = rectangle(20, 20, 320, 80)
        label_strokes = [Stroke([(45, 41), (49, 46), (53, 42), (57, 47), (62, 41)])]
        fake_ocr = lambda image: SimpleNamespace(text="Search", confidence=0.82)
        elements = recognize_sketch(DesignDocument(strokes=[outer, *label_strokes]), ocr=fake_ocr)
        self.assertEqual(elements[0].element_type, "search_field")
        self.assertEqual(elements[0].text, "Search")
        self.assertAlmostEqual(elements[0].ocr_confidence, 0.82)
        self.assertFalse(elements[0].needs_review)

    def test_invalid_ocr_confidence_does_not_discard_recognized_text(self):
        outer = rectangle(20, 20, 320, 80)
        label_strokes = [Stroke([(45, 41), (49, 46), (53, 42), (57, 47), (62, 41)])]
        result = SimpleNamespace(text="Search", confidence="not-a-score")

        elements = recognize_sketch(
            DesignDocument(strokes=[outer, *label_strokes]), ocr=lambda image: result
        )

        self.assertEqual(elements[0].text, "Search")
        self.assertIsNone(elements[0].ocr_confidence)
        self.assertTrue(elements[0].needs_review)

    def test_low_ocr_score_flags_container_suggestion_for_review(self):
        outer = rectangle(20, 20, 320, 80)
        label_strokes = [Stroke([(45, 41), (49, 46), (53, 42), (57, 47), (62, 41)])]
        fake_ocr = lambda image: SimpleNamespace(text="Search", confidence=0.20)

        elements = recognize_sketch(DesignDocument(strokes=[outer, *label_strokes]), ocr=fake_ocr)

        self.assertEqual(elements[0].element_type, "search_field")
        self.assertEqual(elements[0].text, "Search")
        self.assertTrue(elements[0].needs_review)
        self.assertAlmostEqual(elements[0].ocr_confidence, 0.20)

    def test_nested_rectangles_infer_panel_and_keep_child(self):
        outer = rectangle(10, 10, 400, 280)
        inner = rectangle(50, 50, 250, 100)
        elements = recognize_sketch(DesignDocument(strokes=[outer, inner]))
        self.assertEqual(len(elements), 2)
        outer_element = max(elements, key=lambda e: e.width*e.height)
        self.assertEqual(outer_element.element_type, "panel")
        self.assertTrue(any(e.element_id != outer_element.element_id for e in elements))

    def test_ocr_can_create_label_from_strokes_outside_controls(self):
        strokes = [
            Stroke([(30, 40), (34, 30), (38, 40)]),
            Stroke([(42, 40), (42, 30), (47, 40)]),
            Stroke([(52, 30), (52, 40)]),
        ]
        fake_ocr = lambda image: SimpleNamespace(text="OK", confidence=0.91)
        elements = recognize_sketch(DesignDocument(strokes=strokes), ocr=fake_ocr)
        labels = [element for element in elements if element.element_type == "label"]
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0].text, "OK")
        self.assertEqual(len(labels[0].source_stroke_ids), 3)
        self.assertFalse(labels[0].needs_review)
        self.assertFalse(any(element.element_type == "line" for element in elements))

    def test_ocr_failure_keeps_geometry_suggestions_and_original_strokes(self):
        outer = rectangle(20, 20, 320, 80)
        lettering = Stroke([(45, 41), (49, 46), (53, 42), (57, 47), (62, 41)])
        document = DesignDocument(strokes=[outer, lettering])

        def failing_ocr(image):
            raise RuntimeError("model inference failed")

        elements = recognize_sketch(document, ocr=failing_ocr)

        self.assertTrue(elements)
        self.assertEqual(document.strokes, [outer, lettering])
        self.assertFalse(any(element.element_type == "label" for element in elements))

    def test_empty_ocr_text_does_not_create_a_label(self):
        strokes = [
            Stroke([(30, 40), (34, 30), (38, 40)]),
            Stroke([(42, 40), (42, 30), (47, 40)]),
            Stroke([(52, 30), (52, 40)]),
        ]
        result = SimpleNamespace(text="  ", confidence=None)

        document = DesignDocument(strokes=strokes)
        elements = recognize_sketch(document, ocr=lambda image: result)

        self.assertFalse(any(element.element_type == "label" for element in elements))
        self.assertEqual(document.strokes, strokes)

    def test_ocr_punctuation_is_preserved_as_a_text_suggestion(self):
        strokes = [
            Stroke([(30, 40), (34, 30), (38, 40)]),
            Stroke([(42, 40), (42, 30), (47, 40)]),
            Stroke([(52, 30), (52, 40)]),
        ]
        result = SimpleNamespace(text="?!.", confidence=0.42)

        elements = recognize_sketch(DesignDocument(strokes=strokes), ocr=lambda image: result)
        labels = [element for element in elements if element.element_type == "label"]

        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0].text, "?!.")
        self.assertTrue(labels[0].needs_review)

    def test_low_ocr_score_flags_standalone_label_for_review(self):
        strokes = [
            Stroke([(30, 40), (34, 30), (38, 40)]),
            Stroke([(42, 40), (42, 30), (47, 40)]),
            Stroke([(52, 30), (52, 40)]),
        ]
        fake_ocr = lambda image: SimpleNamespace(text="OK", confidence=0.20)

        elements = recognize_sketch(DesignDocument(strokes=strokes), ocr=fake_ocr)
        label = next(element for element in elements if element.element_type == "label")

        self.assertEqual(label.text, "OK")
        self.assertTrue(label.needs_review)
        self.assertAlmostEqual(label.ocr_confidence, 0.20)

    def test_empty_document_returns_no_elements(self):
        self.assertEqual(recognize_sketch(DesignDocument()), [])

    def test_unrecognized_strokes_are_not_lost_from_source_document(self):
        stroke = Stroke([(10, 10), (15, 25), (12, 33), (40, 50)])
        document = DesignDocument(strokes=[stroke])
        recognize_sketch(document)
        self.assertEqual(document.strokes, [stroke])
