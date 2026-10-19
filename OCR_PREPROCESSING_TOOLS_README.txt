Sketch2GUI OCR preprocessing experiment

Purpose:
Compare the unmodified labeled image crops against three preprocessing variations:
- tight_pad: trim excess near-white border around the visible drawing and add a safe white margin
- thicker_ink: same crop with a mild 3x3 dark-pixel dilation
- binary: same crop converted to black and white using a fixed threshold

These are experiments, not guaranteed improvements. Original samples and existing baseline reports are not modified. The currently selected application path is PaddleOCR plus the `binary` variant, because it tied `tight_pad` on the previously reported 19-sample exact-match/CER results and was slightly faster. See OCR_DECISION.md. The original samples/results were not recovered with this project snapshot, so the measurements have not been rerun.

Install the two Python scripts into your Sketch2GUI project root, beside benchmark_ocr.py.

Generate variants:
  .\.venv-paddle\Scripts\python.exe .\prepare_ocr_variants.py --samples .\benchmark\line_samples --output .\benchmark\preprocessed

Benchmark each with the already-installed PaddleOCR environment. Use --raw-paddle-input because these folders are already externally preprocessed; this avoids applying the app's default preprocessing a second time:
  .\.venv-paddle\Scripts\python.exe .\benchmark_ocr.py --samples .\benchmark\preprocessed\tight_pad --engines paddle --raw-paddle-input --output .\benchmark\results-paddle-variants\tight_pad
  .\.venv-paddle\Scripts\python.exe .\benchmark_ocr.py --samples .\benchmark\preprocessed\thicker_ink --engines paddle --raw-paddle-input --output .\benchmark\results-paddle-variants\thicker_ink
  .\.venv-paddle\Scripts\python.exe .\benchmark_ocr.py --samples .\benchmark\preprocessed\binary --engines paddle --raw-paddle-input --output .\benchmark\results-paddle-variants\binary

Compare them with the original baseline:
  .\.venv-paddle\Scripts\python.exe .\compare_ocr_variants.py --baseline .\benchmark\results-paddle\results.json --variants-root .\benchmark\results-paddle-variants

Each benchmark variant uses exactly the same filename/label pairs. Do not replace the original sample images; they remain the baseline. Use --raw-paddle-input on the original baseline run too so the original, tight_pad, thicker_ink, and binary results are all measured without the app's default preprocessor being applied twice. To measure the selected app pipeline itself, run benchmark_ocr.py without --raw-paddle-input on the original crops.
