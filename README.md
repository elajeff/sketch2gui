# Sketch2GUI

Sketch2GUI is a Windows desktop application for turning rough sketches into editable GUI designs, previewing the result, and exporting standalone PySide6 Python code. The canvas, preview, saved project and code generator share one serializable design model.

## Highlights

- **Sketch interpretation:** Deterministic geometry heuristics identify likely rectangles, lines, ellipses, tables and simple component relationships. Optional OCR can read text drawn into the sketch and help suggest control types.
- **Explicit component tools:** When a shape is ambiguous, users can choose Box, Button, Text field, Label, Table, Chart or Ellipse before drawing. The app records the intended type directly instead of guessing from a rectangle alone.
- **Correction and editing:** Review uncertain suggestions, reclassify components, edit text and placeholders, and move or resize components. Multi-selection, snapping, alignment, duplication, undo and redo support layout refinement.
- **Synchronized preview and code:** Changes update the shared design model, interpreted GUI and generated source. Original pen strokes are preserved as artwork rather than discarded when recognition is uncertain.
- **Tables and charts:** Configure table dimensions and cell values, or enter numeric chart values in Properties.
- **Portable projects:** Save and reopen JSON designs, then export a standalone Python program using PySide6 widgets.

## How recognition works

The first-pass recognizer uses inspectable geometry heuristics; it is not a general-purpose vision model. It analyzes stroke closure, straightness, dimensions and relationships to suggest components. Optional PaddleOCR can recognize English text lines to provide extra evidence, but it does not infer the full meaning of a sketch by itself.

A rectangle alone is often semantically ambiguous: it could be a panel, button or input field. The direct component tools let the user specify that intent explicitly, and all suggestions remain editable. The goal is to create a useful starting point—not to claim that every sketch will be interpreted correctly.

## Run on Windows

Use 64-bit Python 3.13. Double-click `run.bat`; it creates the project virtual environment when needed and installs the core application plus the PaddleOCR/PaddlePaddle runtime if the dependencies are missing. It then launches Sketch2GUI. The first setup may take several minutes because OCR dependencies are large. Model weights download separately on first OCR use and are cached for later runs.

To install and run manually from PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-ocr-paddle.txt
.\.venv\Scripts\python.exe -m sketch2gui
```

Choose **PaddleOCR · English** and click **Interpret sketch** to use OCR. An internet connection is needed the first time the model weights are fetched. Choose **OCR off (geometry only)** to run without OCR. An experimental TrOCR adapter is available for development when its optional dependencies are installed; it is not included in the standard Windows bundle. Historical comparison details and commands are in [`docs/ocr-evaluation.md`](docs/ocr-evaluation.md).

## Test and build

Run the offline test suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Create the OCR-enabled Windows folder distribution and timestamped release archive:

```powershell
powershell -ExecutionPolicy Bypass -File .\release_windows.ps1
```

The build script collects PaddleOCR/PaddlePaddle and the application icon into `dist\Sketch2GUI`. The English model weights are not bundled; they download on first OCR use. Keep the entire distribution folder together with `Sketch2GUI.exe`. The release script writes a SHA-256 checksum beside the release ZIP.

Before distributing a release, launch the packaged executable on Windows and run a real OCR interpretation. A successful unit-test run or PyInstaller build alone does not prove that model downloads and inference will work on every machine.

## Known limitations

- Geometry recognition is heuristic. If a sketch does not distinguish similar controls, the recognizer may suggest the wrong type; direct component tools and manual correction are part of the intended workflow.
- OCR accuracy on mouse-drawn handwriting is variable. A historical trial of 19 short crops from two drawings achieved about 21% exact word match. That small, correlated sample is not a reliable estimate of general accuracy, and the original samples were not recovered for rerunning.
- The OCR model recognizes English text lines; it does not convert an entire sketch into a semantically complete interface.
- Generated interfaces use absolute coordinates and are not automatically responsive to every window size.

## Project structure

```text
sketch2gui/       Application, design model, recognition, OCR adapters, UI and code generation
tests/            Unit and UI regression tests
benchmark/        Locally captured, labeled OCR samples (not included in source control)
docs/             OCR experiment notes and reproducible comparison commands
run.bat           Source setup and launcher
build_windows.bat OCR-enabled PyInstaller folder build
release_windows.ps1 Build, verify and package the Windows release
requirements*.txt Core, build, and optional OCR dependencies
```

## License

MIT. See `LICENSE`.
