# Sketch2GUI overnight build report

Date: 2026-10-19

## Completed

- Audited the recovered project, instructions, plan, app modules, docs, dependencies, tests, sample folders, and build workflow. There is no `.git` metadata, so a Git diff/status could not be produced. The benchmark folder contains no recovered drawings, labeled OCR crops, or prior result CSV/JSON files.
- Kept the selected optional OCR backend as PaddleOCR PP-OCRv5 mobile English (`en_PP-OCRv5_mobile_rec`) with binary text-line preprocessing. Paddle remains optional; geometry-only startup is covered when Paddle dependencies are absent. OCR predictions remain suggestions requiring correction.
- Improved benchmark reporting so raw exact match is separate from normalized exact match; made malformed project-data errors clearer; made project saves atomic; prevented sample image/truth overwrite; added undoable element deletion; and fixed canvas scaling/selection behavior.
- Added Qt UI and OCR tests for drawing/selecting/deselecting, interpretation, review navigation, type/text/placeholder correction, preview/code synchronization, delete/undo/redo, save/open/export, malformed-file handling, sample overwrite protection, OCR errors/empty/punctuation, optional-engine selection, and preprocessing.
- Added an optional PyInstaller build requirement and Windows folder-build script. Revised the build to rely on PyInstaller's PySide6 hooks instead of collecting all optional Qt modules.
- Updated README setup, tests, OCR caveats, and Windows packaging instructions.

## Verification and exact results

Full test suite (workspace-local temp paths are needed in this sandbox):

```powershell
$env:TEMP=(Get-Location).Path; $env:TMP=(Get-Location).Path; $env:QT_QPA_PLATFORM='offscreen'; .\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Result: `Ran 65 tests in 0.149s` / `OK`.

Compile check:

```powershell
.\.venv\Scripts\python.exe -m compileall -q sketch2gui tests launch_sketch2gui.py benchmark_ocr.py compare_ocr_results.py compare_ocr_variants.py prepare_ocr_samples.py prepare_ocr_variants.py
```

Result: exit code `0`.

Additional verified checks:

- Offscreen app entrypoint and Qt event loop ran; the geometry-only app window was visible to Qt and the entrypoint returned `0` after a timed close.
- Generated representative PySide6 source compiled, executed, and instantiated actual widgets.
- Windows package launch check: started `dist_lean\Sketch2GUI\Sketch2GUI.exe` without the offscreen setting, observed the `Sketch2GUI` window, then closed it through the Windows main-window close request.
- The offscreen packaged-app attempt did not expose a Windows close handle; it is not counted as the package smoke check. The visible Windows launch above succeeded.

PyInstaller dependency installation command and result:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
```

Result: installed PyInstaller `6.22.3` in the project `.venv`.

First package build (the then-current broad `--collect-all PySide6` configuration):

```powershell
.\build_windows.bat
```

Result: `Build complete: dist\Sketch2GUI\Sketch2GUI.exe`; 3,962 files, 684.8 MiB total, executable 4.77 MiB. It included many unused Qt modules.

Narrow package build using PyInstaller's normal PySide6 hooks (separate output paths preserved the first package):

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --windowed --name Sketch2GUI --distpath dist_lean --workpath build_lean launch_sketch2gui.py
```

Result: exit code `0`; 219 files, 128.3 MiB total, executable 2.64 MiB. The build script was updated to use this narrower PyInstaller configuration (with its normal `dist` and `build` output paths). The updated batch file itself was not rerun over the already generated broad output; the equivalent narrow PyInstaller build command above succeeded.

## Historical OCR metrics (not rerun)

Historical sample count: **19 labeled mouse-written crops from two drawings**. The original crop files and raw reports were not recovered. No OCR benchmark was rerun, and no new metrics are claimed.

| Historical setup | Raw exact match | Mean CER | Median inference |
|---|---:|---:|---:|
| PaddleOCR original crops | 5.3% (1/19) | 0.378 | 21.9 ms |
| PaddleOCR tight crop + padding | 21.1% (4/19) | 0.351 | 14.1 ms |
| PaddleOCR binary preprocessing (selected) | 21.1% (4/19) | 0.351 | 13.1 ms |
| PaddleOCR thicker ink | 15.8% (3/19) | 0.379 | 13.9 ms |
| TrOCR Base Handwritten | 5.3% (1/19) | 0.906 | 869.2 ms |

These correlated 19 examples are preliminary and not representative. PaddlePaddle, PaddleOCR, and OCR model weights are absent from this environment, so real OCR inference and a new benchmark remain unverified.

## Limitations and manual follow-up

- Native packaged-app startup and close were verified. Full mouse-driven product interactions were verified by the offscreen Qt suite; a manual visible interaction pass (draw, interpret, correct, save/reopen, export/run) remains useful on the user's desktop.
- Real Paddle inference requires installing the optional packages in a compatible Python environment and collecting new genuinely labeled samples. The missing historical sample set cannot be recreated from this workspace.
- The build outputs are local ignored artifacts; nothing was committed, uploaded, published, or released. The broad first build remains preserved at `dist\Sketch2GUI`; the slimmer verified build is at `dist_lean\Sketch2GUI`.
- Geometry recognition is heuristic; generated layouts use absolute coordinates; OCR accuracy on the historical sample was low. Manual corrections remain necessary.

## Changed source and documentation files

`.gitignore`, `benchmark_ocr.py`, `tests/test_benchmark.py`, `sketch2gui/models.py`, `tests/test_models.py`, `sketch2gui/ui/main_window.py`, `sketch2gui/ui/canvas.py`, `tests/test_ui.py`, `tests/test_ocr_backend.py`, `tests/test_paddle_preprocessing.py`, `tests/test_geometry.py`, `README.md`, `PROJECT_STATUS.md`, `requirements-build.txt`, `build_windows.bat`, `launch_sketch2gui.py`, and `OVERNIGHT_BUILD_REPORT.md`.

