# OCR development utilities

These scripts support local OCR experiments; they are not required to run the Sketch2GUI application.
Run commands from the repository root. Labeled samples are pairs of image files and same-stem `.txt` files containing the expected text. Local samples and benchmark outputs are not committed.

- `prepare_ocr_samples.py` — crop individual text lines from a saved canvas image and create matching text labels.
- `prepare_ocr_variants.py` — create comparable `tight_pad`, `thicker_ink`, and `binary` preprocessing variants without changing the originals.
- `benchmark_ocr.py` — run PaddleOCR and/or optional TrOCR on a labeled sample folder and write JSON/CSV metrics.
- `compare_ocr_results.py` — compare separate engine reports after verifying they contain the same labeled samples.
- `compare_ocr_variants.py` — compare preprocessing variants against a baseline report.

## Examples

```powershell
.\.venv\Scripts\python.exe .\tools\ocr\prepare_ocr_samples.py --image .\benchmark\samples\canvas.png --output .\benchmark\line_samples
.\.venv\Scripts\python.exe .\tools\ocr\benchmark_ocr.py --samples .\benchmark\line_samples --engines paddle --output .\benchmark\results-paddle
.\.venv\Scripts\python.exe .\tools\ocr\prepare_ocr_variants.py --samples .\benchmark\line_samples --output .\benchmark\preprocessed
```

For the historical experiment, metric definitions and preprocessing details, see [`../../docs/ocr-evaluation.md`](../../docs/ocr-evaluation.md). The recorded experiment is exploratory and small; its metrics should not be treated as general accuracy estimates.
