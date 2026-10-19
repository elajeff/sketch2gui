import unittest
from prepare_ocr_samples import map_display_rect_to_image, safe_stem


class OCRCropHelperTests(unittest.TestCase):
    def test_maps_display_box_to_original_image_coordinates(self):
        self.assertEqual(
            map_display_rect_to_image((10, 20, 30, 40), 2.0, 3.0, 200, 300),
            (20, 60, 60, 120),
        )

    def test_normalizes_reverse_drag_and_clips_bounds(self):
        self.assertEqual(
            map_display_rect_to_image((30, 40, -5, -10), 2.0, 2.0, 100, 100),
            (0, 0, 60, 80),
        )

    def test_safe_stem_uses_label_and_sequence(self):
        self.assertEqual(safe_stem("Search field!", 2), "sample_002_Search_field")
        self.assertEqual(safe_stem("!!!", 3), "sample_003_label")


if __name__ == "__main__":
    unittest.main()
