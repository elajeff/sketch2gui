"""Crop text lines from a full Sketch2GUI canvas image for OCR evaluation.

Usage:
    python tools/ocr/prepare_ocr_samples.py --image benchmark/samples/sample_123.png

Drag a rectangle around one text line/label, click "Save selected crop", then
enter the exact text. Crops are saved with matching .txt files for benchmark_ocr.py.
"""
from __future__ import annotations

import argparse
import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from PIL import Image, ImageTk


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def map_display_rect_to_image(
    rect: tuple[float, float, float, float],
    scale_x: float,
    scale_y: float,
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int]:
    """Map a display-space rectangle to a clipped image-space crop box."""
    x1, y1, x2, y2 = rect
    left = max(0, min(image_width, round(min(x1, x2) * scale_x)))
    top = max(0, min(image_height, round(min(y1, y2) * scale_y)))
    right = max(0, min(image_width, round(max(x1, x2) * scale_x)))
    bottom = max(0, min(image_height, round(max(y1, y2) * scale_y)))
    return left, top, right, bottom


def safe_stem(text: str, index: int) -> str:
    """Return a short, portable filename stem for a sample label."""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", text.strip()).strip("_-")
    return f"sample_{index:03d}_{slug[:32] or 'label'}"


class CropWindow:
    def __init__(self, root: tk.Tk, image_path: Path, output_dir: Path):
        self.root = root
        self.image_path = image_path
        self.output_dir = output_dir
        self.image = Image.open(image_path).convert("RGB")
        self.original_width, self.original_height = self.image.size
        self.display_image = self.image.copy()
        self.display_image.thumbnail((1120, 700), Image.Resampling.LANCZOS)
        self.display_width, self.display_height = self.display_image.size
        self.scale_x = self.original_width / self.display_width
        self.scale_y = self.original_height / self.display_height
        self.photo = ImageTk.PhotoImage(self.display_image)
        self.start: tuple[int, int] | None = None
        self.rect_id: int | None = None
        self.saved_count = len(list(output_dir.glob("*.png"))) if output_dir.exists() else 0

        root.title("Prepare OCR samples — select one text line at a time")
        root.geometry(f"{self.display_width + 36}x{self.display_height + 145}")
        root.minsize(640, 400)

        instructions = (
            "Drag a box around ONE handwritten text line or label. Avoid nearby shapes where possible. "
            "Click Save selected crop and enter the exact text. Repeat for more lines."
        )
        tk.Label(root, text=instructions, wraplength=self.display_width, justify="left").pack(
            fill="x", padx=12, pady=(10, 6)
        )
        self.canvas = tk.Canvas(
            root,
            width=self.display_width,
            height=self.display_height,
            background="#20242c",
            highlightthickness=1,
            highlightbackground="#8a929f",
            cursor="crosshair",
        )
        self.canvas.pack(padx=12, pady=4)
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        self.canvas.bind("<ButtonPress-1>", self._start_selection)
        self.canvas.bind("<B1-Motion>", self._update_selection)
        self.canvas.bind("<ButtonRelease-1>", self._finish_selection)

        button_row = tk.Frame(root)
        button_row.pack(fill="x", padx=12, pady=8)
        self.save_button = tk.Button(
            button_row, text="Save selected crop…", command=self.save_crop, state="disabled"
        )
        self.save_button.pack(side="left")
        tk.Button(button_row, text="Clear selection", command=self.clear_selection).pack(
            side="left", padx=(8, 0)
        )
        self.status = tk.Label(root, text=self._status_text(), anchor="w")
        self.status.pack(fill="x", padx=12, pady=(0, 8))

    def _status_text(self) -> str:
        return f"Source: {self.image_path.name}  |  Saved labeled crops: {self.saved_count}  |  Output: {self.output_dir}"

    def _start_selection(self, event):
        self.start = (event.x, event.y)
        if self.rect_id is not None:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline="#F59E0B", width=2
        )
        self.save_button.configure(state="disabled")

    def _update_selection(self, event):
        if self.start is None or self.rect_id is None:
            return
        self.canvas.coords(self.rect_id, self.start[0], self.start[1], event.x, event.y)

    def _finish_selection(self, event):
        if self.start is None:
            return
        x1, y1 = self.start
        x2, y2 = event.x, event.y
        self.start = None
        if abs(x2 - x1) >= 6 and abs(y2 - y1) >= 6:
            self.save_button.configure(state="normal")

    def clear_selection(self):
        if self.rect_id is not None:
            self.canvas.delete(self.rect_id)
            self.rect_id = None
        self.save_button.configure(state="disabled")

    def save_crop(self):
        if self.rect_id is None:
            return
        coords = self.canvas.coords(self.rect_id)
        if len(coords) != 4:
            return
        box = map_display_rect_to_image(
            tuple(coords), self.scale_x, self.scale_y, self.original_width, self.original_height
        )
        left, top, right, bottom = box
        if right - left < 5 or bottom - top < 5:
            messagebox.showwarning("Crop too small", "Please select a slightly larger region.", parent=self.root)
            return

        truth = simpledialog.askstring(
            "Label OCR crop",
            "Enter exactly the text inside this crop (case and spacing as written):",
            parent=self.root,
        )
        if truth is None:
            return
        truth = truth.strip()
        if not truth:
            messagebox.showwarning("Text required", "Expected text cannot be empty.", parent=self.root)
            return

        self.output_dir.mkdir(parents=True, exist_ok=True)
        index = 1
        while True:
            stem = safe_stem(truth, index)
            image_out = self.output_dir / f"{stem}.png"
            text_out = self.output_dir / f"{stem}.txt"
            if not image_out.exists() and not text_out.exists():
                break
            index += 1
        created_paths: list[Path] = []
        try:
            # Exclusive creation prevents overwriting an existing sample if another
            # process creates the same pair after the filename check above.
            with image_out.open("xb") as image_file:
                created_paths.append(image_out)
                self.image.crop(box).save(image_file, format="PNG")
            with text_out.open("x", encoding="utf-8") as text_file:
                created_paths.append(text_out)
                text_file.write(truth)
        except Exception as exc:
            # Keep the image and its ground-truth label as an all-or-nothing pair.
            for created_path in reversed(created_paths):
                try:
                    created_path.unlink(missing_ok=True)
                except OSError:
                    pass
            messagebox.showerror(
                "Could not save crop",
                f"Could not save the labeled crop:\n{exc}",
                parent=self.root,
            )
            return
        self.saved_count += 1
        self.status.configure(text=self._status_text())
        self.clear_selection()



def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, help="Existing full-canvas PNG/JPEG from Save OCR sample…")
    parser.add_argument(
        "--output", type=Path, default=Path("benchmark/line_samples"),
        help="Folder to store individual text-line crops and matching .txt labels (default: benchmark/line_samples)",
    )
    args = parser.parse_args()
    image_path = args.image
    if image_path is None:
        chooser = tk.Tk()
        chooser.withdraw()
        selected = filedialog.askopenfilename(
            title="Choose your saved Sketch2GUI canvas image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.webp"), ("All files", "*.*")],
        )
        chooser.destroy()
        if not selected:
            return 1
        image_path = Path(selected)
    if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_SUFFIXES:
        print(f"Image not found or unsupported: {image_path}")
        return 2

    root = tk.Tk()
    CropWindow(root, image_path.resolve(), args.output.resolve())
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
