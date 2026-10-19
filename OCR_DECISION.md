# Current OCR decision for Sketch2GUI

**Recommended engine:** PaddleOCR PP-OCRv5 mobile English, model `en_PP-OCRv5_mobile_rec`.

**Recommended preprocessing:** use the tested `binary` variant on each extracted text-line image: find the dark-ink bounds with grayscale threshold 245, crop to those bounds, add a white margin (`max(10 px, 12% of width)` horizontally and `max(10 px, 30% of height)` vertically), then convert pixels below grayscale 200 to black and all other pixels to white. This is implemented in `sketch2gui/ocr/paddle_backend.py` as `preprocess_for_paddle`. The Paddle model is still optional; use OCR off/geometry mode if its dependencies are not installed. `benchmark_ocr.py --raw-paddle-input` is available when comparing externally prepared variants so they are not preprocessed a second time. The app should default to Paddle only when Paddle and PaddleOCR are available.

## Why this choice

The previous local test used 19 mouse-written label crops from two drawings. Its reported results were:

| Setup | Exact word match | Mean character error rate | Median inference |
|---|---:|---:|---:|
| PaddleOCR, original crops | 5.3% (1/19) | 0.378 | 21.9 ms |
| PaddleOCR, tight crop + padding | 21.1% (4/19) | 0.351 | 14.1 ms |
| **PaddleOCR, binary preprocessing (chosen)** | **21.1% (4/19)** | **0.351** | **13.1 ms** |
| PaddleOCR, thicker ink | 15.8% (3/19) | 0.379 | 13.9 ms |
| TrOCR Base Handwritten | 5.3% (1/19) | 0.906 | 869.2 ms |

Binary and tight-padding variants tied on exact match and CER. Binary was about 1 ms faster at the median, so it is the current straightforward default. The difference is small, and the sample is too small and correlated to establish general accuracy. These historical metrics are retained from the earlier run; the original crops and raw JSON/CSV reports were not found in the recovered archives and were **not rerun**.

## Product behavior requirements

- Treat OCR as a text suggestion, never as a confirmed result.
- Keep text and component type manually editable, and preserve explicit user corrections.
- Do not require OCR dependencies for app launch or geometry-only use.
- Do not auto-download heavy models on app startup. The model may download on first Paddle OCR use.
- Do not block the end-to-end app build on improving OCR scores. Continue with canvas, shared design model, correction UX, preview, code export, save/load, undo/redo, tests and Windows packaging.
- Report the true historical sample count and never claim a new benchmark was run unless it was.
