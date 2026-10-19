import unittest

from PIL import Image, ImageDraw

from sketch2gui.ocr.paddle_backend import preprocess_for_paddle


class PaddlePreprocessingTests(unittest.TestCase):
    def test_preprocessing_crops_ink_adds_padding_and_returns_rgb(self):
        image = Image.new("RGB", (100, 60), "white")
        draw = ImageDraw.Draw(image)
        draw.line((30, 25, 69, 25), fill=(30, 30, 30), width=2)

        result = preprocess_for_paddle(image)

        # Ink crop is 40x3; preprocessing adds the tested minimum 10px margin per side.
        self.assertEqual(result.mode, "RGB")
        self.assertEqual(result.size, (60, 22))
        self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(result.getpixel((10, 11)), (0, 0, 0))

    def test_preprocessing_uses_binary_black_white_threshold(self):
        image = Image.new("RGB", (24, 20), "white")
        image.putpixel((6, 6), (100, 100, 100))
        image.putpixel((12, 6), (220, 220, 220))

        result = preprocess_for_paddle(image)

        # Cropping begins at x=6, y=6; its x/y padding is 10px.
        self.assertEqual(result.getpixel((10, 10)), (0, 0, 0))
        self.assertEqual(result.getpixel((16, 10)), (255, 255, 255))
        self.assertLessEqual(set(result.tobytes()), {0, 255})

    def test_blank_image_stays_white_and_gets_binary_output(self):
        result = preprocess_for_paddle(Image.new("RGBA", (20, 10), (248, 248, 248, 255)))

        self.assertEqual(result.mode, "RGB")
        self.assertEqual(result.size, (20, 10))
        self.assertEqual(set(result.tobytes()), {255})
