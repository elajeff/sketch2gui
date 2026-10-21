"""Create comparable OCR preprocessing variants without modifying labeled originals.

Usage:
    python tools/ocr/prepare_ocr_variants.py --samples benchmark/line_samples --output benchmark/preprocessed

Creates output/{tight_pad,thicker_ink,binary}/ with PNGs and matching TXT labels.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil

from PIL import Image, ImageFilter, ImageOps

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
VARIANTS = ("tight_pad", "thicker_ink", "binary")


def ink_bbox(image: Image.Image, threshold: int = 245):
    """Find foreground bounds assuming dark drawing on a light background."""
    gray = ImageOps.grayscale(image)
    mask = gray.point(lambda value: 255 if value < threshold else 0)
    return mask.getbbox()


def crop_and_pad(image: Image.Image) -> Image.Image:
    """Trim excess light margin around ink and add proportional white padding."""
    rgb = image.convert("RGB")
    bbox = ink_bbox(rgb)
    if bbox is None:
        # Do not destroy samples containing faint/non-dark content.
        return rgb.copy()

    left, top, right, bottom = bbox
    cropped = rgb.crop((left, top, right, bottom))
    width, height = cropped.size
    pad_x = max(10, round(width * 0.12))
    pad_y = max(10, round(height * 0.30))
    canvas = Image.new("RGB", (width + 2 * pad_x, height + 2 * pad_y), "white")
    canvas.paste(cropped, (pad_x, pad_y))
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, required=True, help="Original paired image/TXT samples")
    parser.add_argument("--output", type=Path, required=True, help="Output root for preprocessing variants")
    args = parser.parse_args()

    if not args.samples.is_dir():
        parser.error(f"Sample folder does not exist: {args.samples}")

    samples = []
    for path in sorted(args.samples.iterdir()):
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        truth_path = path.with_suffix(".txt")
        if not truth_path.is_file():
            print(f"Skipping {path.name}: matching .txt label missing")
            continue
        if not truth_path.read_text(encoding="utf-8").strip():
            print(f"Skipping {path.name}: label is empty")
            continue
        samples.append((path, truth_path))

    if not samples:
        parser.error(f"No labeled images found in {args.samples}")

    args.output.mkdir(parents=True, exist_ok=True)
    for variant in VARIANTS:
        (args.output / variant).mkdir(parents=True, exist_ok=True)

    print(f"Preparing {len(samples)} labeled samples; originals will not be changed.")
    for image_path, truth_path in samples:
        with Image.open(image_path) as opened:
            original_size = opened.size
            image = opened.convert("RGB")
        padded = crop_and_pad(image)
        gray = ImageOps.grayscale(padded)
        thick = gray.filter(ImageFilter.MinFilter(3))
        binary = gray.point(lambda value: 0 if value < 200 else 255)
        variant_images = {
            "tight_pad": padded,
            "thicker_ink": Image.merge("RGB", (thick, thick, thick)),
            "binary": Image.merge("RGB", (binary, binary, binary)),
        }
        for variant_name, variant_image in variant_images.items():
            output_dir = args.output / variant_name
            variant_image.save(output_dir / f"{image_path.stem}.png")
            shutil.copyfile(truth_path, output_dir / f"{image_path.stem}.txt")
        print(
            f"{image_path.name}: {original_size[0]}x{original_size[1]} -> "
            f"{padded.width}x{padded.height} (padded crop)"
        )

    print("\nCreated variants:")
    for name in VARIANTS:
        print(f"  {args.output / name}: {len(samples)} PNG/TXT pairs")
    print("Run tools/ocr/benchmark_ocr.py on each variant folder; compare to the original baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
