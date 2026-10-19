"""Utilities for exporting the user's original strokes as OCR sample images."""
from __future__ import annotations

import math
from typing import Iterable

from .models import Stroke


def render_strokes(
    strokes: Iterable[Stroke],
    *,
    scale: float = 2.0,
    padding: float = 24.0,
    max_dimension: int = 3200,
):
    """Render every stroke into a white PNG-friendly image without cropping.

    The output is tightly fitted to the stroke bounds plus padding. Large designs
    are scaled down uniformly to stay within ``max_dimension``; content is never
    truncated to a fixed width or height.
    """
    from PIL import Image, ImageDraw

    stroke_list = [stroke for stroke in strokes if stroke.points]
    points = [point for stroke in stroke_list for point in stroke.points]
    if not points:
        raise ValueError("No strokes to save")
    if scale <= 0:
        raise ValueError("Scale must be greater than zero")
    if padding < 0:
        raise ValueError("Padding cannot be negative")
    if max_dimension < 48:
        raise ValueError("Maximum image dimension must be at least 48 pixels")

    left = min(float(point[0]) for point in points)
    top = min(float(point[1]) for point in points)
    right = max(float(point[0]) for point in points)
    bottom = max(float(point[1]) for point in points)

    content_width = max(right - left, 1.0)
    content_height = max(bottom - top, 1.0)
    desired_width = content_width + padding * 2
    desired_height = content_height + padding * 2

    # Apply one scale factor to both axes so the entire drawing fits without
    # distortion. This replaces the old fixed 600 px height that clipped tall
    # drawings after rendering them at 2x resolution.
    actual_scale = min(scale, max_dimension / desired_width, max_dimension / desired_height)
    width = max(48, int(math.ceil(desired_width * actual_scale)))
    height = max(48, int(math.ceil(desired_height * actual_scale)))

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    line_width = max(1, int(round(2.0 * actual_scale)))

    for stroke in stroke_list:
        coords = [
            ((float(x) - left + padding) * actual_scale,
             (float(y) - top + padding) * actual_scale)
            for x, y in stroke.points
        ]
        if len(coords) >= 2:
            draw.line(coords, fill="black", width=line_width, joint="curve")
        else:
            x, y = coords[0]
            radius = max(1, line_width // 2)
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill="black")

    return image
