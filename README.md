# Sketch2GUI

Sketch2GUI is a Windows desktop experiment that turns freehand mouse sketches into an editable GUI design, a live widget preview, and generated PySide6 Python source. It uses a shared design model so the canvas, preview, and generator stay synchronized.

## What works in this foundation

- **Freehand canvas:** capture and preserve original mouse strokes.
- **Geometry-based recognition:** detect closed rectangles, ellipses, straight lines, and simple candidate controls without a trained AI model.
- **Optional OCR adapters:** PaddleOCR PP-OCRv5 mobile English is the recommended OCR. It uses tight ink cropping, white padding, and binary thresholding based on a small benchmark; TrOCR remains an experimental alternative.
- **Correction workflow:** click any preview component to select it, change its type and properties, and update the preview and Python code from the same model. User-confirmed types are preserved in saved projects.
- **Quiet uncertainty cues:** low-confidence components show a small amber dot and appear in the “to review” navigation; no popups or flashing warnings.
- **Editable project files:** save/load `.json` designs, preserve original strokes, and undo/redo common design changes.
- **Code export:** generate a standalone Python file that builds a PySide6 GUI from the shared model.
- **Component editing:** select a preview/canvas item, edit its type, text and bounds, then use Delete or Ctrl+Z to remove/restore it.
- **OCR benchmark capture:** save the actual mouse-drawn label plus ground-truth text, then compare both engines on exactly the same labeled examples.

## Current limitations

This is a foundational MVP, not a general-purpose sketch-understanding AI. The deterministic recognizer currently uses a small number of geometric heuristics; a rectangle's intended meaning is ambiguous, so uncertain guesses are expected and deliberately correctable. OCR recognizes text lines only; it does not decide component meaning by itself. Mouse-drawn handwriting may be very different from handwriting in model training data.

The preview currently prioritizes matching element positions in a fixed-size canvas. Generated code uses absolute coordinates, so exported interfaces are not yet automatically responsive to every window size. Container/layout inference, richer table configuration, drag-to-move/resize, image import, and AI-based interpretation are future improvements, not claims about this version.

## Run on Windows

Install Python 3.13 64-bit (recommended), then double-click `run.bat`. On first launch, it creates `.venv`, installs the core dependencies, and starts the app. Or run manually from PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m sketch2gui
```

Core mode does not require an AI/OCR model. When PaddleOCR and PaddlePaddle are installed, the app selects the recommended PaddleOCR option by default; otherwise it starts in geometry-only mode. Choose **OCR off (geometry only)** to avoid model loading/downloads.

## OCR setup

Use a regular core installation first. OCR dependencies and pretrained weights are intentionally optional so the base app remains easier to install and small. The current recommended choice is PaddleOCR PP-OCRv5 mobile English (`en_PP-OCRv5_mobile_rec`) with binary text-line preprocessing. The optional TrOCR adapter remains available for comparison, but the current small handwritten sample trial was substantially slower and had a higher character error rate.

### PaddleOCR PP-OCRv5 mobile English

PaddleOCR documents `en_PP-OCRv5_mobile_rec` as a small English text recognizer (listed at about 7.5 MB) with improved handwritten-English recognition. The inference package and PaddlePaddle runtime are separate dependencies; compatible Windows wheels depend on Python/platform versions.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ocr-paddle.txt
```

The first use may download pretrained model files. Official model card: https://huggingface.co/PaddlePaddle/en_PP-OCRv5_mobile_rec

### Microsoft TrOCR Base Handwritten

TrOCR is a handwriting-focused transformer recognizer. Its `microsoft/trocr-base-handwritten` model is much larger than the Paddle mobile model, and its weights and dependencies consume substantially more disk and memory.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ocr-trocr.txt
```

The first use downloads the model and processor from Hugging Face. Official model card: https://huggingface.co/microsoft/trocr-base-handwritten

If installing both model stacks into one environment causes dependency conflicts, keep the sample folder shared and run each benchmark from a separate virtual environment. The benchmark produces compatible `results.json` and `results.csv` files for each run; `compare_ocr_results.py` verifies the sample names and ground-truth labels match before showing a side-by-side comparison.

## Compare the OCR engines fairly

Do not choose a recognizer solely from published model-card results: neither model was evaluated specifically on text drawn with this app's mouse canvas in the current environment. Collect a representative set of your own labels first.

1. If you already drew many words on one canvas and saved it with **Save OCR sample…**, reuse that PNG. The app's OCR adapter recognizes one line/crop at a time, so a full-canvas image should be divided into individual text lines or labels before benchmarking. Current sample exports preserve the full bounds of every stroke with padding; very large drawings are uniformly scaled down instead of clipped.
2. Run the crop helper against your existing full-canvas image:

```powershell
py -3.13 .\prepare_ocr_samples.py --image .\benchmark\samples\sample_123.png --output .\benchmark\line_samples
```

Replace `sample_123.png` with your actual saved image filename. In the window, drag a rectangle around one text line or label, click **Save selected crop…**, and enter the exact text. Repeat for other labels; the helper writes a cropped PNG and matching `.txt` file for each selection. You do not have to redraw the words. It uses Python's built-in Tkinter and the existing Pillow dependency.
3. Aim for 20–30 different line crops eventually, with neat and messy writing and different sizes. One full sketch is enough to begin a smoke test; multiple crops from it are useful but correlated, so add samples from other sketches before making a final choice.
4. With both OCR packages installed, run the benchmark against the crop folder:

```powershell
.\.venv\Scripts\python.exe .\benchmark_ocr.py --samples .\benchmark\line_samples --engines paddle,trocr --output .\benchmark\results
```

The first model initialization may download weights. The report contains exact-match accuracy, mean character error rate (CER), median per-sample inference time, model load time, prediction-by-prediction output, and errors. By default Paddle uses the same binary preprocessing as the app. When comparing externally preprocessed folders (`tight_pad`, `thicker_ink`, `binary`), add `--raw-paddle-input` to prevent preprocessing the images twice. Both engines receive each labeled image; sample order is the same. This benchmark currently measures recognition, not automatic text-region detection.

`exact_match_accuracy` compares the original strings exactly. `normalized_exact_match_accuracy` separately ignores case and repeated/leading/trailing whitespace. Per-sample `cer` is calculated after the same normalization; failed inference counts as an empty prediction.

At least three labeled samples are required for a smoke benchmark, but use 20–30 or more before treating the result as a meaningful comparison. Include failed and ambiguous results rather than deleting them. Do not compare runs that use different sets of images.

If model packages conflict, install them separately and run the same sample set once per environment. Both environments need the core app dependencies because the benchmark script uses the shared project package:

```powershell
# Create the Paddle environment
py -3.13 -m venv .venv-paddle
.\.venv-paddle\Scripts\python.exe -m pip install --upgrade pip
.\.venv-paddle\Scripts\python.exe -m pip install -r requirements.txt -r requirements-ocr-paddle.txt
.\.venv-paddle\Scripts\python.exe .\benchmark_ocr.py --samples .\benchmark\line_samples --engines paddle --output .\benchmark\results-paddle

# Create the TrOCR environment
py -3.13 -m venv .venv-trocr
.\.venv-trocr\Scripts\python.exe -m pip install --upgrade pip
.\.venv-trocr\Scripts\python.exe -m pip install -r requirements.txt -r requirements-ocr-trocr.txt
.\.venv-trocr\Scripts\python.exe .\benchmark_ocr.py --samples .\benchmark\line_samples --engines trocr --output .\benchmark\results-trocr

# Check that the reports use the same labeled images and compare their metrics
py -3.13 .\compare_ocr_results.py --paddle-json .\benchmark\results-paddle\results.json --trocr-json .\benchmark\results-trocr\results.json
```

### Current OCR decision (19 labeled mouse-written crops; preliminary)

The best measured setup so far is **PaddleOCR PP-OCRv5 mobile English + binary preprocessing** (tight crop around dark ink, add white padding, then threshold to black/white at 200). Binary and tight-pad preprocessing tied on the available samples; binary was slightly faster at the median, so it is the current default. Historical results from the user's earlier local run:

| Setup | Exact word match | Mean character error rate (CER) | Median inference |
|---|---:|---:|---:|
| PaddleOCR, original crops | 5.3% (1/19) | 0.378 | 21.9 ms |
| PaddleOCR, tight-pad | 21.1% (4/19) | 0.351 | 14.1 ms |
| **PaddleOCR, binary (current default)** | **21.1% (4/19)** | **0.351** | **13.1 ms** |
| PaddleOCR, thicker ink | 15.8% (3/19) | 0.379 | 13.9 ms |
| TrOCR Base Handwritten | 5.3% (1/19) | 0.906 | 869.2 ms |

The original samples and raw report files were not present in the recovered archives, so these numbers are preserved as historical results and were not rerun during recovery. Only 19 crops from two drawings were used; this is not a representative or conclusive benchmark. OCR must remain optional and user-correctable. Do not silently treat predictions as correct or claim reliable handwriting recognition.

## Run tests

Core model, geometry recognition, code generation, and benchmark metric tests do not download OCR models:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Build a Windows folder package

The optional PyInstaller build creates a folder distribution without OCR model weights. From PowerShell, install the core dependencies and build tool, then run:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt
.\build_windows.bat
```

The executable and support files are written to `dist\Sketch2GUI`. PyInstaller's PySide6 hooks collect the Qt libraries used by the app; the build script avoids collecting every optional Qt module. The package does not include OCR model weights. The build was verified on Windows with Python 3.13.16 and PyInstaller 6.22.3; run the executable on the target computer before distributing it.

The unittest suite includes offscreen Qt checks for canvas drawing and selection, interpretation, correction, review navigation, deletion, and undo. A visible desktop smoke test is still useful before distributing a build. PaddleOCR inference has not been run in the current environment because its optional packages and model weights are not installed.

## Project structure

```text
sketch2gui/
  models.py          Shared serializable design model
  geometry.py        Deterministic freehand shape/component heuristics
  codegen.py         Standalone PySide6 source generator
  ocr/               Optional OCR interface; Paddle's selected default includes binary preprocessing
  ui/                Canvas, preview, properties panel, main window
benchmark/
  samples/           User-captured full-canvas PNG + original text labels
  line_samples/      Cropped individual text lines + truth pairs (generated locally)
prepare_ocr_samples.py Crop one or more labels from an existing full-canvas sample
benchmark_ocr.py     Repeatable same-sample OCR comparison
compare_ocr_results.py Compare separate-environment benchmark reports
requirements*.txt    Core and optional OCR dependencies
run.bat              Windows setup and launcher
 tests/              Offline unit tests
```

## License

MIT. See `LICENSE`.
