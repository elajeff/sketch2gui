# Sketch2GUI

Sketch2GUI is a Windows desktop tool for turning rough interface sketches into editable GUI designs and standalone Python applications built with PySide6.

## Features

- **One shared design model.** The canvas, interpreted preview, saved project and code generator use the same serializable model, keeping geometry and component edits synchronized. Original pen strokes remain available as artwork.
- **Inspectable sketch recognition.** Deterministic geometry heuristics identify likely shapes and simple relationships. Uncertain results are flagged for review instead of presented as guaranteed classifications.
- **Human-guided correction.** Draw components with an explicit type when geometry alone is ambiguous, or correct and edit recognized components afterward. Move, resize, duplicate, align and multi-select items on the canvas.
- **Runnable code export.** Export a standalone PySide6 window containing real widgets, editable table data, configurable line charts and preserved freehand strokes.
- **Optional local OCR.** PaddleOCR can recognize English text lines to provide extra evidence during interpretation. Once its model files are downloaded, inference runs locally; OCR is not a general-purpose model that understands an entire interface.

## Recognition approach and limitations

The first-pass recognizer uses inspectable geometry rules for stroke closure, straightness, dimensions and relationships. A rectangle can represent a panel, button or input field, so automatic classification is inherently ambiguous; explicit drawing tools and manual correction are part of the intended workflow.

OCR is a text-recognition aid, not full sketch understanding. A historical trial of 19 short crops from two drawings achieved 21.1% exact word match with the selected preprocessing. That small, correlated sample is not a reliable estimate of general accuracy, and the original images were not recovered for a fresh evaluation. Confidence scores are model-specific review signals, not calibrated probabilities. Exported layouts use absolute coordinates and are not automatically responsive.

## Getting started on Windows

Use 64-bit Python 3.13. Double-click `run.bat`; it creates `.venv` when needed, installs the core app and PaddleOCR dependencies, then launches Sketch2GUI. Initial setup can take several minutes because the OCR runtime is large. Model weights download separately on first OCR use and are cached for subsequent runs.

To install and run from PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-ocr-paddle.txt
.\.venv\Scripts\python.exe -m sketch2gui
```

Select **PaddleOCR · English** and choose **Interpret sketch** to use OCR. The first model download requires an internet connection. Select **OCR off (geometry only)** for geometry-only interpretation. An experimental TrOCR adapter is available for development with the additional dependencies in `requirements-ocr-trocr.txt`; it is not part of the standard Windows bundle. See [`docs/ocr-evaluation.md`](docs/ocr-evaluation.md) for the historical experiment and benchmark commands.

## Development and release

Run the tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Build and package the OCR-enabled Windows distribution:

```powershell
powershell -ExecutionPolicy Bypass -File .\release_windows.ps1
```

The build uses PyInstaller to create `dist\Sketch2GUI`. The release script creates a ZIP and a SHA-256 checksum. Keep the full distribution together with `Sketch2GUI.exe`; English model weights are not bundled and download on first OCR use.

Before distributing a release, launch the packaged executable on Windows and perform an actual OCR recognition. Passing unit tests or building the executable alone does not prove that model download and inference work on the target machine.

## Project layout

```text
sketch2gui/       Application, shared model, geometry recognition, OCR adapters and UI
tests/            Unit and GUI regression tests
docs/             OCR experiment notes and benchmark instructions
benchmark_ocr.py  Labeled-sample OCR benchmark runner
run.bat           Source setup and launcher
build_windows.bat Windows folder build
release_windows.ps1 Build, package and checksum the release
requirements*.txt Core, build and optional OCR dependencies
```

## License

MIT. See [`LICENSE`](LICENSE).
