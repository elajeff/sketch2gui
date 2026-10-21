import unittest
from sketch2gui.models import DesignDocument, Stroke, UIElement, preserve_manual_edits


class ModelTests(unittest.TestCase):
    def test_chart_values_round_trip(self):
        chart = UIElement("chart", 10, 10, 200, 100, chart_values=[1, 4.5, 2])
        restored = UIElement.from_dict(chart.to_dict())
        self.assertEqual(restored.chart_values, [1.0, 4.5, 2.0])

    def test_table_dimensions_and_cells_round_trip(self):
        table = UIElement("table", 10, 10, 240, 150, table_rows=2, table_columns=2,
                          table_cells=[["Name", "Room"], ["Ada", "Lab 1"]])
        restored = UIElement.from_dict(table.to_dict())
        self.assertEqual((restored.table_rows, restored.table_columns), (2, 2))
        self.assertEqual(restored.table_cells, [["Name", "Room"], ["Ada", "Lab 1"]])

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

    def test_changing_component_type_initializes_table_cells(self):
        element = UIElement("panel", 10, 20, 180, 90)
        element.set_type("table")
        self.assertEqual(element.table_cells, [["", "", ""], ["", "", ""], ["", "", ""]])
        element.table_cells[0][0] = "Name"
        element.set_type("button")
        self.assertEqual(element.table_cells, [])
        element.set_type("table")
        self.assertEqual(element.table_cells[0][0], "")

    def test_loaded_component_bounds_are_kept_inside_canvas(self):
        project = DesignDocument(width=200, height=240, elements=[
            UIElement("button", 10, 10, 80, 30)
        ]).to_dict()
        project["elements"][0]["bounds"] = {
            "x": -500, "y": 1_000_000_000, "width": 9000, "height": 8000
        }
        loaded = DesignDocument.from_dict(project)
        element = loaded.elements[0]
        self.assertEqual((element.x, element.y, element.width, element.height),
                         (0.0, 0.0, 200.0, 240.0))

    def test_project_rejects_duplicate_component_ids(self):
        project = DesignDocument(elements=[
            UIElement("button", 10, 10, 80, 30),
            UIElement("label", 100, 10, 80, 30),
        ]).to_dict()
        project["elements"][1]["id"] = project["elements"][0]["id"]
        with self.assertRaisesRegex(ValueError, "duplicate component IDs"):
            DesignDocument.from_dict(project)

        stroke_project = DesignDocument(strokes=[
            Stroke([(10, 10), (20, 20)]), Stroke([(30, 30), (40, 40)]),
        ]).to_dict()
        stroke_project["strokes"][1]["id"] = stroke_project["strokes"][0]["id"]
        with self.assertRaisesRegex(ValueError, "duplicate stroke IDs"):
            DesignDocument.from_dict(stroke_project)

    def test_project_rejects_oversized_point_collections(self):
        project = {"format": "sketch2gui", "version": 1,
                   "strokes": [{"points": [[1, 1]] * 25_001}], "elements": []}
        with self.assertRaisesRegex(ValueError, "more than 25000 points"):
            DesignDocument.from_dict(project)

    def test_project_rejects_excessive_table_cell_dimensions(self):
        with self.assertRaisesRegex(ValueError, "table cells cannot exceed 20 rows or columns"):
            UIElement.from_dict({"type": "table", "table_rows": 1, "table_columns": 1,
                                "table_cells": [["x"] * 21]})

    def test_project_rejects_stroke_points_outside_canvas(self):
        project = DesignDocument(strokes=[Stroke([(-1, 2), (3, 4)])]).to_dict()
        with self.assertRaisesRegex(ValueError, "within canvas bounds"):
            DesignDocument.from_dict(project)

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

    def test_manual_correction_survives_when_recognition_misses_its_strokes(self):
        corrected = UIElement(
            "search_field", 10, 20, 170, 40, text="Find users",
            placeholder="Find users", confidence=1.0, confirmed=True,
            user_modified=True, source_stroke_ids=["stroke-a", "stroke-b"],
        )
        unrelated = UIElement(
            "line", 300, 50, 100, 8, source_stroke_ids=["stroke-c"],
        )

        result = preserve_manual_edits([corrected], [unrelated])

        preserved = next(element for element in result if element.element_id == corrected.element_id)
        self.assertEqual(preserved.element_type, "search_field")
        self.assertEqual(preserved.text, "Find users")
        self.assertEqual(preserved.source_stroke_ids, ["stroke-a", "stroke-b"])

    def test_overlapping_drawing_tool_components_survive_interpretation(self):
        first = UIElement(
            "button", 20, 20, 120, 50, text="First",
            confirmed=True, user_modified=True,
        )
        second = UIElement(
            "text_field", 60, 35, 150, 45, placeholder="Second",
            confirmed=True, user_modified=True,
        )
        detections = [
            UIElement("panel", 18, 18, 125, 55, source_stroke_ids=["stroke-a"]),
            UIElement("button", 65, 38, 140, 40, source_stroke_ids=["stroke-b"]),
        ]

        result = preserve_manual_edits([first, second], detections)

        self.assertEqual({element.element_id for element in result}, {first.element_id, second.element_id})
        self.assertEqual([element.text for element in result], ["First", ""])
        self.assertEqual(result[1].placeholder, "Second")

    def test_drawing_tool_components_survive_interpretation(self):
        button = UIElement(
            "button", 30, 40, 120, 40, text="My button",
            confirmed=True, user_modified=True,
        )
        detected = UIElement(
            "panel", 28, 38, 125, 45, confidence=0.4,
            source_stroke_ids=["sketch-outline"],
        )
        preserved = preserve_manual_edits([button], [detected])
        self.assertEqual(len(preserved), 1)
        self.assertEqual(preserved[0].element_type, "button")
        self.assertEqual(preserved[0].text, "My button")

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

    def test_non_finite_stroke_data_is_rejected(self):
        for points in ([[float("nan"), 2]], [[1, float("inf")]]):
            with self.subTest(points=points), self.assertRaisesRegex(ValueError, "finite"):
                Stroke.from_dict({"points": points})
        with self.assertRaisesRegex(ValueError, "finite"):
            Stroke([], width=float("inf"))

    def test_non_finite_component_geometry_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            UIElement("button", float("nan"), 0, 100, 40)
        with self.assertRaisesRegex(ValueError, "finite"):
            UIElement("button", 0, 0, 100, 40, confidence=float("inf"))

    def test_malformed_numeric_project_fields_get_clear_errors(self):
        with self.assertRaisesRegex(ValueError, "chart values must be finite numbers"):
            UIElement.from_dict({"type": "chart", "chart_values": ["not-a-number"]})
        with self.assertRaisesRegex(ValueError, "canvas dimensions must be integers"):
            DesignDocument.from_dict({"format": "sketch2gui", "canvas": {"width": "wide"}})
        with self.assertRaisesRegex(ValueError, "table dimensions must be integers"):
            UIElement.from_dict({"type": "table", "table_rows": "many"})
        with self.assertRaisesRegex(ValueError, "Stroke points must be a list"):
            Stroke(None)

    def test_unsupported_project_version_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported Sketch2GUI project version"):
            DesignDocument.from_dict({"format": "sketch2gui", "version": 2})

    def test_source_stroke_ids_must_be_an_array(self):
        with self.assertRaisesRegex(ValueError, "source stroke IDs"):
            UIElement.from_dict({"type": "panel", "source_stroke_ids": "not-an-array"})

    def test_unknown_alternatives_are_ignored_on_load(self):
        element = UIElement.from_dict({"type":"panel", "bounds":{"width":80,"height":80}, "alternatives":["bogus","button"]})
        self.assertEqual(element.alternatives, ["button"])
