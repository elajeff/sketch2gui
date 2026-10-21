# OCR evaluation and preprocessing experiments

## Current choice

The standard application uses PaddleOCR PP-OCRv5 mobile English (`en_PP-OCRv5_mobile_rec`) with binary text-line preprocessing. OCR remains optional; users can choose geometry-only interpretation. Model weights are fetched lazily on first PaddleOCR use rather than at application startup.

A previous local comparison used 19 mouse-written text crops from only two drawings:

| Setup | Exact word match | Mean character error rate | Median inference time |
|---|---:|---:|---:|
| PaddleOCR, original crops | 5.3% (1/19) | 0.378 | 21.9 ms |
| PaddleOCR, tight crop and padding | 21.1% (4/19) | 0.351 | 14.1 ms |
| **PaddleOCR, binary preprocessing (current choice)** | **21.1% (4/19)** | **0.351** | **13.1 ms** |
| PaddleOCR, thicker ink | 15.8% (3/19) | 0.379 | 13.9 ms |
| TrOCR Base Handwritten | 5.3% (1/19) | 0.906 | 869.2 ms |

Binary preprocessing tied with tight-pad cropping on exact match and character error rate and was about 1 ms faster at the median. These are historical results, not a recent rerun; the original images and raw result files were not recovered. The sample is small and correlated, so it does not establish general handwriting accuracy.

The chosen preprocessing finds dark-ink bounds using a grayscale threshold of 245, crops to the bounds, adds white padding (`max(10 px, 12% of width)` horizontally and `max(10 px, 30% of height)` vertically), then thresholds at 200 to produce black-and-white text-line input. It is implemented in `sketch2gui/ocr/paddle_backend.py` as `preprocess_for_paddle`.

OCR output remains a suggestion. The confidence values exposed by OCR engines are model-specific and not calibrated probabilities. The current heuristic caps a base recognition score at `min(base_score, 0.35 + 0.5 * OCR_score)` when a usable OCR score exists, and at `0.55` when it does not. These are review heuristics, not statistically calibrated confidence estimates.

## Running a benchmark

Use real mouse-drawn text samples. Each image must have a same-stem `.txt` file containing the expected text. Add samples through Sketch2GUI's **Save OCR sample…** command or place paired files in `benchmark/samples/`. Do not mix different sample sets when comparing models.

Run the selected PaddleOCR pipeline:

```powershell
.\.venv\Scripts\python.exe .\tools\ocr\benchmark_ocr.py --samples .\benchmark\samples --engines paddle --output .\benchmark\results-paddle
```

TrOCR is an optional, larger alternative. Install its extra requirements before benchmarking it:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements-ocr-trocr.txt
.\.venv\Scripts\python.exe .\tools\ocr\benchmark_ocr.py --samples .\benchmark\samples --engines paddle,trocr --output .\benchmark\results-compare
```

To compare preprocessing variants, generate separate variants from the original labeled set:

```powershell
.\.venv\Scripts\python.exe .\tools\ocr\prepare_ocr_variants.py --samples .\benchmark\samples --output .\benchmark\preprocessed
.\.venv\Scripts\python.exe .\tools\ocr\benchmark_ocr.py --samples .\benchmark\preprocessed\tight_pad --engines paddle --raw-paddle-input --output .\benchmark\results-paddle-variants\tight_pad
.\.venv\Scripts\python.exe .\tools\ocr\benchmark_ocr.py --samples .\benchmark\preprocessed\thicker_ink --engines paddle --raw-paddle-input --output .\benchmark\results-paddle-variants\thicker_ink
.\.venv\Scripts\python.exe .\tools\ocr\benchmark_ocr.py --samples .\benchmark\preprocessed\binary --engines paddle --raw-paddle-input --output .\benchmark\results-paddle-variants\binary
.\.venv\Scripts\python.exe .\tools\ocr\compare_ocr_variants.py --baseline .\benchmark\results-paddle\results.json --variants-root .\benchmark\results-paddle-variants
```

Use `--raw-paddle-input` for already-preprocessed variants so the application preprocessor is not applied a second time. To compare the selected application path itself, omit that flag for the original crops. Benchmark output folders and local sample images are ignored by Git. Treat small differences as tentative and report the sample count with any results.
