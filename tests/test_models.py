import unittest
from sketch2gui.models import DesignDocument, Stroke, UIElement, preserve_manual_edits


class ModelTests(unittest.TestCase):
    def test_document_round_trip_preserves_strokes_and_elements(self):
        document = DesignDocument(strokes=[Stroke([(1, 2), (3, 4)])],
                                  elements=[UIElement("search_field", 10, 20, 150, 35,
                                                      placeholder="Search...", confidence=0.55,
                                                      alternatives=["text_field"])],
                                  name="Test project")
        loaded = DesignDocument.from_dict(document.to_dict())
        self.assertEqual(loaded.name, "Test project")
        self.assertEqual(loaded.strokes[0].points, [(1.0, 2.0), (3.0, 4.0)])
        self.assertEqual(loaded.elements[0].element_type, "search_field")
        self.assertEqual(loaded.elements[0].placeholder, "Search...")
        self.assertTrue(loaded.elements[0].needs_review)

    def test_user_correction_is_persisted_and_clears_warning(self):
        element = UIElement("table", 0, 0, 200, 45, confidence=0.4, alternatives=["search_field"])
        element.set_type("search_field")
        self.assertEqual(element.element_type, "search_field")
        self.assertTrue(element.confirmed)
        self.assertFalse(element.needs_review)
        restored = UIElement.from_dict(element.to_dict())
        self.assertTrue(restored.confirmed)

    def test_invalid_element_type_is_rejected(self):
        with self.assertRaises(ValueError):
            UIElement("not-a-widget", 0, 0, 100, 30)

    def test_dimensions_are_clamped_to_minimum(self):
        element = UIElement("button", 0, 0, 0, 0)
        self.assertEqual((element.width, element.height), (8, 8))

    def test_manual_correction_survives_a_later_recognition_pass(self):
        stroke_ids = ["stroke-a", "stroke-b"]
        previous = UIElement("search_field", 10, 20, 170, 40, text="Find users", placeholder="Find users",
                             confidence=1.0, confirmed=True, user_modified=True, source_stroke_ids=stroke_ids)
        new_guess = UIElement("table", 10, 20, 170, 40, confidence=0.5,
                              alternatives=["panel"], source_stroke_ids=stroke_ids)
        result = preserve_manual_edits([previous], [new_guess])
        self.assertEqual(result[0].element_type, "search_field")
        self.assertEqual(result[0].text, "Find users")
        self.assertEqual(result[0].element_id, previous.element_id)
        self.assertTrue(result[0].confirmed)

    def test_newly_drawn_strokes_do_not_inherit_old_correction(self):
        old = UIElement("search_field", 10, 20, 170, 40, confirmed=True, user_modified=True,
                        source_stroke_ids=["old-stroke"])
        new = UIElement("table", 10, 20, 170, 40, source_stroke_ids=["new-stroke"])
        result = preserve_manual_edits([old], [new])
        self.assertEqual(result[0].element_type, "table")
        self.assertFalse(result[0].confirmed)

    def test_bad_stroke_format_is_rejected(self):
        with self.assertRaises(ValueError):
            Stroke.from_dict({"points": [[1, 2, 3]]})

    def test_malformed_project_collections_are_rejected_clearly(self):
        with self.assertRaisesRegex(ValueError, "strokes and elements"):
            DesignDocument.from_dict({"strokes": {}, "elements": []})
        with self.assertRaisesRegex(ValueError, "JSON object"):
            DesignDocument.from_dict([])

    def test_unknown_alternatives_are_ignored_on_load(self):
        element = UIElement.from_dict({"type":"panel", "bounds":{"width":80,"height":80}, "alternatives":["bogus","button"]})
        self.assertEqual(element.alternatives, ["button"])
