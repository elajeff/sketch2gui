# Sketch2GUI — project context and measured OCR baseline

## Product goal

Sketch2GUI is a Windows desktop app built with Python and PySide6. Users draw a GUI freely with the mouse. The app recognizes candidate geometry/components, optionally reads text with OCR, renders an editable GUI preview, and generates readable Python/PySide6 code. The target is a genuinely useful portfolio application with a strong, testable foundation.

Expected project folder on the user's PC:

`<local project folder>`

Verify it at runtime; don't recursively search the whole Downloads folder unless necessary.

## Non-negotiable architecture

One shared design model is the source of truth. The canvas, preview, properties panel, persistence and code generator consume/update this model. Keep original strokes, stable element IDs, suggested semantic type, recognition confidence/review state, properties, and user-confirmed overrides. Manual correction must persist across re-interpretation if source strokes have not changed.

## Agreed UX

- Freehand mouse drawing is the primary interaction, not only toolbar-selected components.
- Geometric recognition must tolerate imperfect strokes and return ranked candidate interpretations where practical.
- User selects a component in the preview and corrects its meaning (e.g. rectangle/table -> search field) and properties. The preview and generated source update from the shared model.
- Low-confidence items get a subtle but visible amber marker and a review count/navigation path. No flashing or intrusive popups. Editor-only indicators never appear in exported applications.
- OCR helps recognize text; it does not infer component intent on its own. OCR can be disabled/replaced and manual editing always works.
- Save/load design JSON, preserve original strokes, undo/redo important changes, and export standalone readable Python code.
- Make the application polished, keyboard-accessible enough for ordinary use, resize sensibly, and explain uncertainty without nagging.

## OCR decision and historical measured results

The project has been recovered from saved ZIP snapshots after the local folder was deleted. The original `benchmark\line_samples` crops and raw result JSON/CSV files were not contained in those archives. The user approved proceeding without those files. The numbers below are the historical results previously reported from the user's actual Windows run, not a rerun of the recovered archive. Treat them as preliminary because the 19 labels came from two drawings and are correlated.

### Original preprocessing

| Metric | PaddleOCR PP-OCRv5 mobile English | Microsoft TrOCR Base Handwritten |
|---|---:|---:|
| Samples | 19 | 19 |
| Failures | 0 | 0 |
| Exact word match | 5.3% (1/19) | 5.3% (1/19) |
| Mean character error rate | 0.378 | 0.906 |
| Median inference time | 21.89 ms | 869.2 ms |
| Model load time | 14,728 ms | 183,590 ms |

Paddle examples: `animal -> anmas`, `bible -> be`, `cancel -> can cel`, `etiquette -> etiquctte`, `header -> header`, `login -> lojin`, `search -> x0`. TrOCR frequently hallucinated extra words or punctuation. Paddle is the better measured candidate so far, but neither is accurate enough to trust without correction.

### PaddleOCR preprocessing trial

| Variant | Exact word match | Mean CER | Median ms | Better CER vs original | Worse CER vs original |
|---|---:|---:|---:|---:|---:|
| Original | 5.3% | 0.378 | 21.9 | — | — |
| Tight crop + padding | 21.1% | 0.351 | 14.1 | 6 | 3 |
| Thicker ink | 15.8% | 0.379 | 13.9 | 4 | 4 |
| Binary | 21.1% | 0.351 | 13.1 | 6 | 3 |

**Current implementation choice:** PaddleOCR PP-OCRv5 mobile English (`en_PP-OCRv5_mobile_rec`) with binary text-line preprocessing is the default when its optional dependencies are installed. The tested binary variant crops around dark ink, adds proportional white padding, then thresholds grayscale values below 200 to black and all others to white. It tied tight-pad on exact match and CER and was about 1 ms faster at the median, so this is a conservative current default, not a claim that OCR is accurate enough to trust. If Paddle is not installed, the app should start in geometry-only mode and explain how to install it. Manual editing/correction must remain easy.

The historical raw result files and labeled images are currently unavailable in the recovered source; don't waste time looking for them indefinitely, don't recreate fake historical samples, and don't claim to have rerun the benchmark. Keep any newly collected tests in new folders. Keep original results immutable if they are later recovered. If testing combinations/normalization, label them as separate experiments. Do not turn punctuation/whitespace/case normalization into the primary exact-match metric without reporting raw exact match separately. Do not describe a 19-sample test as conclusive.

The recovery archives do not contain the earlier full canvas images, 19 line crops, or result JSON/CSV. If these files later appear in the working tree, verify their counts and pairings before use; otherwise proceed using the current Paddle + binary preprocessing choice and note that no new empirical benchmark has been run.

## Initial recovery build audit (2026-10-19; later environment update below)

- The inspected working folder has no `.git` directory, so branch, remote, and tracked/untracked diff checks are unavailable. The inspected `benchmark` folder contains only its samples README; no user drawings, labeled crop pairs, or old benchmark JSON/CSV outputs were present.
- The available interpreter is Python 3.15.0. It has no installed project dependencies (`PySide6`, Pillow, PaddlePaddle, PaddleOCR, pytest, and PyInstaller are absent). The baseline and final full unittest discovery attempts therefore cannot import image/OCR-dependent tests, and the native GUI/app/package smoke checks remain unexecuted.
- The default full test command currently stops on missing Pillow with 7 errors (five dependent test-module imports plus two geometry tests that render OCR crops). Core model, geometry-only, code-generation, compare-report, and benchmark-metric cases were exercised separately; see `OVERNIGHT_BUILD_REPORT.md` for exact commands and results.
- The app now retains raw exact benchmark matching alongside normalized matching, rejects malformed project collection shapes with readable `ValueError`s, saves JSON through a unique same-directory temporary file, exposes undoable component deletion, and refuses to overwrite an existing captured sample image/label pair.
- Added a separate optional PyInstaller requirement and Windows folder-build script. The build is a documented workflow only; it has not produced a package in this environment. No model weights are bundled by the script.
- The historical OCR result remains the previously reported 19 mouse-written labels from two drawings. No samples or raw result files were recovered and no OCR run was performed during this audit.

## Current known capabilities/limitations

The existing foundation README describes freehand stroke capture, deterministic geometric heuristics, optional PaddleOCR and TrOCR adapters, a correction workflow, low-confidence cues, JSON save/load, undo/redo, Python export, and OCR sample/benchmark tooling. Verify each claim against current code and tests before relying on it.

Known limitation: generated code uses absolute coordinates and is not yet automatically responsive to every window size. Geometry recognition is heuristic; arbitrary sketch intent is ambiguous. OCR benchmark has very low accuracy on the user's specific mouse-written samples. Do not claim AI-grade understanding or production-quality OCR.

## Follow-up verification (2026-10-19)

- The user created `.venv` with Python 3.13.16; Pillow 12.3.0 and PySide6 6.12.0 are installed. PaddleOCR, PaddlePaddle, pytest, and PyInstaller are not installed.
- Full unittest discovery now includes the binary preprocessing tests (converted from pytest-only functions), OCR failure/empty/punctuation cases, and offscreen UI behavior tests. With temp paths placed in the workspace and Qt set to offscreen, all 65 tests pass.
- Added an aspect-preserving canvas transform. Qt mouse tests verify selection/deselection, drawing inside existing elements, interpretation suggestions, review navigation, text/type/placeholder corrections, preview/code synchronization, save/open/export, malformed-file preservation, sample overwrite protection, Paddle-default selection when available, and delete/undo/redo.
- An offscreen Qt main-window lifecycle check and generated-PySide6-widget instantiation check both passed. Real Paddle inference was not run.
- Installing the optional PyInstaller build dependency failed because `pypi.org` DNS could not resolve in the restricted environment. No package was produced; the build remains a manual verification step in a network-enabled environment.

## Final autonomous build update (2026-10-19)

- Verified the project `.venv` full suite after implementation: 65 tests passed (`unittest discover -s tests -v`, Qt offscreen, TEMP/TMP set to the workspace). `compileall` returned exit code 0.
- Installed optional build tooling successfully: PyInstaller 6.22.3. The first `build_windows.bat` run succeeded but its broad PySide6 collection created a 684.8 MiB folder (3,962 files). Preserved that output at `dist\Sketch2GUI`.
- Replaced `--collect-all PySide6` in the build script with normal PyInstaller Qt hooks. The equivalent narrow command built successfully in separate paths at `dist_lean\Sketch2GUI` (128.3 MiB, 219 files). Its executable started visibly on Windows with title `Sketch2GUI` and closed cleanly.
- The OCR historical metrics and 19-sample count above remain historical only. Original files were not recovered; Paddle dependencies/model weights are absent; no OCR inference or benchmark rerun was performed.
- No repository metadata exists, so Git diff/status is unavailable. No user sample/result data was present or changed. No commit, push, release, upload, or publication occurred.
