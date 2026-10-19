# Sketch2GUI recovery notes

This folder was rebuilt from the latest complete Sketch2GUI source archive available in the conversation Library: `Sketch2GUI-foundation-fixed-sample-export.zip`. The latest saved Codex handoff plan and OCR preprocessing helper scripts have also been added.

## What is included

- Sketch2GUI Python source, UI code, geometry recognizer, shared model, and code generator
- Offline tests and launch/setup files
- OCR adapters, benchmark runner, OCR sample-cropping/preprocessing utilities, and the selected PaddleOCR binary-preprocessing path
- `AGENTS.md`, `PROJECT_STATUS.md`, `AUTONOMOUS_BUILD_PLAN.md`, `OVERNIGHT_TASK.md`, and `CODEX_START_PROMPT.txt`

## Verification

After the OCR-default/preprocessing update, `python -m pytest -q` reports **47 passed** and `python -m compileall -q sketch2gui benchmark_ocr.py compare_ocr_results.py compare_ocr_variants.py prepare_ocr_samples.py prepare_ocr_variants.py` passes. This does not verify the native desktop GUI or real OCR inference: PySide6, PaddleOCR, and Transformers model weights were not available in this test environment.

## Files not recovered

The saved source archive did not contain the user's local `benchmark/line_samples` image crops, their matching `.txt` labels, or the raw PaddleOCR/TrOCR `results.json` and `results.csv` output folders. The current OCR selection is recorded in `OCR_DECISION.md`; the user approved proceeding with that choice without recovering the samples. The scripts to recreate and rerun those benchmarks are included, but the original local data/results are not represented as restored. The Paddle adapter now applies the historical best-performing binary preprocessing automatically and Paddle is selected by default only if its optional dependencies are available.

Results previously discussed in the conversation, for context only: on 19 labeled handwritten samples the unprocessed PaddleOCR and TrOCR runs each had 5.3% exact match; PaddleOCR mean character error rate was 0.378 versus 0.906 for TrOCR, with median inference of about 21.9 ms versus 869.2 ms. Tight padding and binary preprocessing each reached 21.1% exact match and CER about 0.351; thicker ink reached 15.8% exact match. The sample is small, so treat these as exploratory results, not a reliable general benchmark. The underlying raw report files are not included.

## Important

This is the latest **recoverable saved snapshot**, not a guarantee that it contains any unarchived changes that existed only in the deleted local folder. Keep a backup before making major changes.
