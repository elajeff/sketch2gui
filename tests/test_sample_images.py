import unittest

from sketch2gui.models import Stroke
from sketch2gui.sample_images import render_strokes


class RenderStrokeSampleTests(unittest.TestCase):
    def test_tall_drawing_is_fully_preserved_instead_of_clipped(self):
        strokes = [
            Stroke(points=[(10, 10), (10, 580)]),
            Stroke(points=[(10, 580), (780, 580)]),
        ]
        image = render_strokes(strokes)
        self.assertGreater(image.height, 600)
        self.assertGreater(image.width, 1200)
        # Dark pixels must exist close to both the top and bottom content edges.
        pixels = image.convert("L")
        self.assertLess(min(pixels.crop((0, 0, image.width, 100)).getextrema()), 255)
        self.assertLess(min(pixels.crop((0, image.height - 100, image.width, image.height)).getextrema()), 255)

    def test_large_drawing_is_scaled_uniformly_below_limit(self):
        image = render_strokes([Stroke(points=[(0, 0), (5000, 4000)])])
        self.assertLessEqual(max(image.size), 3200)
        self.assertGreater(image.width, 1000)
        self.assertGreater(image.height, 700)

    def test_empty_strokes_are_rejected(self):
        with self.assertRaises(ValueError):
            render_strokes([])


if __name__ == "__main__":
    unittest.main()
