# Autonomous build plan: finish Sketch2GUI MVP

## Mission

Continue from the actual repository to a finished, testable, usable Windows MVP of Sketch2GUI. This is an end-to-end product task, not an OCR-only task. Work through each phase, verify it, then proceed to the next without stopping to ask routine questions. When an earlier part is already sound, verify it and move on rather than reimplementing it. Use conservative, interview-defensible solutions.

Do not interpret “finished product” as permission for unbounded features. The MVP is complete when all required acceptance criteria below are met, the app runs locally on Windows, tests pass, the generated code can execute, documentation matches actual behavior, and the final report states remaining limitations honestly. If context/usage limits stop the task, leave a clear checkpoint and list completed/remaining criteria.

## Phase 0 — Repository and baseline audit

- Read `AGENTS.md` and `PROJECT_STATUS.md`.
- Verify working directory, Python version, git status, branch/remotes, project structure, current app entrypoint, dependencies, tests, docs and build scripts.
- Never discard user changes. Do not restore/reset files or use destructive cleanup.
- Run current tests and preserve their actual output; reproduce any failure before fixing it.
- Check whether OCR result CSV/JSON files and sample/truth pairs actually exist in the recovered working tree. The saved recovery archives did not include them; if absent, record this and continue rather than searching indefinitely or recreating pretend historical results.
- If any real samples are present, verify their counts and label pairing and inspect representative PNGs. Do not treat synthetic test images as a replacement historical benchmark.

## Phase 1 — Use the current evidence-based OCR default

- Keep PaddleOCR PP-OCRv5 mobile English (`en_PP-OCRv5_mobile_rec`) as the recommended/default OCR engine, with the tested binary text-line preprocessing pipeline implemented in `sketch2gui/ocr/paddle_backend.py`: crop around dark ink using grayscale threshold 245, add at least 10 px / proportional white padding, then threshold grayscale below 200 to black and others to white.
- The only measured evidence available is a previously reported 19-crop run: binary and tight-pad variants each achieved 21.1% exact word match and mean CER 0.351; binary median inference was 13.1 ms versus 14.1 ms for tight-pad. Original Paddle crops scored 5.3% exact match / CER 0.378 at 21.9 ms; TrOCR scored 5.3% / 0.906 at 869.2 ms. Treat those results as preliminary, not conclusive.
- The original labeled crops and JSON/CSV report files were not found in the saved archives. Do not claim that results have been reproduced or rerun. New benchmarks can be run only on genuinely collected and labeled samples; do not generate fake ground truth to reconstruct the old metrics.
- Continue auditing the benchmark's path matching, truth loading, error handling, normalization and CER/exact-match math. Preserve raw exact match and report separately any normalized scores. Never overwrite real baseline outputs if they are recovered later.
- Inspect crops and predictions to distinguish mouse-stroke shape problems from cropping, polarity, stroke width, text-line assumptions, and model limitations.
- If helpful, add a small, representative set beyond the 19 correlated labels, but do not overwrite or silently edit ground truth. Be explicit about selection bias.
- The current selection is already made from the limited historical evidence: PaddleOCR + binary preprocessing. If validation reveals a concrete problem, make a measured and documented adjustment; otherwise don't restart an open-ended OCR research phase. OCR remains optional assistance, not ground truth. Keep manual correction prominent and explain the limitation.
- Keep each OCR engine behind the same adapter interface. Do not require users to install/download both heavyweight stacks. Core application must still work without OCR packages/network access.
- Test inference failure, empty text, weird punctuation, and engine-unavailable behavior.

## Phase 2 — Shared model and recognition correctness

- Verify one authoritative design model is used by canvas, recognizer, properties editor, preview, save/load and code generation.
- Preserve raw strokes and stable element IDs separately from recognized component objects.
- Recognition should return a suggestion, plausible alternatives when ambiguity matters, and a confidence/review state. A heuristic score is not a calibrated probability; call it a score/confidence estimate and don't imply statistics that aren't supported.
- Support sensible deterministic recognition for lines, rectangles/rounded rectangles, ellipses and common GUI patterns/components supported by the codebase.
- Maintain the user-confirmed semantic type/text/properties across later recognition passes unless source strokes materially changed or the user explicitly asks to reinterpret/reset.
- If existing data formats need changes, maintain backwards compatibility or include a clear safe migration with tests. Do not corrupt older JSON projects.

## Phase 3 — Correction and editing UX

- A user can select an item directly in the preview or canvas and change its semantic type (e.g., table-like rectangle -> search field), text/placeholder, position, size, and supported appearance.
- Changing component type preserves geometry and shared common properties where sensible; initialize sensible defaults for new type-specific fields.
- Edits immediately update model, preview and generated Python from the same data.
- Low-confidence cues are amber, subtle but visible, static/non-flashing, editor-only, with a review count and a way to navigate uncertain elements. Do not nag while drawing.
- Include usable selection outlines, sensible deselection, deleting elements, undo/redo, and no accidental preview-widget activation while trying to select it.
- Ensure drawing new strokes inside/over existing components is possible and intuitive. Test click/select/drag/draw behaviors distinctly.

## Phase 4 — Preview and generated source

- Preview must render actual PySide6 widgets for supported components, not merely paint approximations, where feasible.
- The code generator produces readable, standalone, syntactically valid Python/PySide6 code with imports and a runnable entry point.
- Correctly escape all user text/strings, make stable unique variable names, avoid generating imports/widgets for unsupported or deleted elements, and handle empty projects.
- Every supported component/property shown in the preview must either be reflected in generated code or clearly marked unsupported. Keep a single source of truth.
- Add integration-style checks that generate code for a representative design, compile it, and instantiate/run it in a safe smoke test where environment supports it.
- Absolute positioning is acceptable for the first MVP if it matches the sketch faithfully. Do not build a sophisticated automatic responsive-layout inference system without clear evidence and a manageable design.

## Phase 5 — Save/load and project reliability

- Save projects to JSON and reopen them with strokes, components, edits, confidence/review state and overrides intact.
- Validate malformed/old project files; report understandable errors without destroying the current project.
- Save atomically where simple and appropriate; avoid silent overwrite of a different project.
- Undo/redo should reliably cover normal editing operations and not lose the original strokes.
- Confirm sample-capture/export preserves full drawing bounds. Add a regression test for large canvas images not clipping at an arbitrary fixed height.
- Ensure benchmark tooling never modifies source sample PNGs, truth TXT files or prior result directories.

## Phase 6 — Finish the product UX

- Clear app title and hierarchy; sensible window resizing; canvas and preview both remain usable at practical window sizes.
- Toolbar/menu items for drawing/interpretation, selecting/correcting, undo/redo, save/open project, export Python, and OCR configuration should be understandable.
- Make OCR off/core mode useful without downloading a model. If PaddleOCR and PaddlePaddle are present, select PaddleOCR by default; if they are absent, default to OCR off and explain the optional install command clearly. Optional model setup errors should tell the user what is missing and how to install it.
- Provide a compact status line/progress feedback for expensive OCR/model loading, without freezing the main UI unnecessarily. Do not run OCR on each mouse move.
- Handle errors gracefully and keep GUI responsive during model loading/inference when practical. No fake progress.
- Check keyboard basics, selection/keyboard focus, color contrast, default window size and high-DPI scaling where practical.
- Do not add unnecessary accounts, cloud services, project telemetry, a plugin marketplace, custom model training, or unrelated features.

## Phase 7 — Tests, packaging, docs, final verification

- Review test suite for meaningful behavior/failure cases; do not reduce count for optics. Keep focused, maintainable tests, not exhaustive tests of every trivial helper.
- Add regression tests for actual bugs found: recognizer ambiguous cases, user correction persistence, save/load round-trip, generated source correctness, OCR metrics/failed inference, full-bounds sample export, and UI selection/review navigation.
- Run the full tests and compile check. Report exact commands, counts, failures/skips and environment, including tests for the binary OCR preprocessor.
- Run the app on Windows if working on Windows. Smoke-test: draw strokes, interpret, correct a component, check amber review, edit text, undo/redo, save/reopen, export and run generated Python, optional OCR/no-OCR mode.
- Verify optional dependency isolation and practical PyInstaller or Windows package workflow. Do not bundle model weights by default unless there is a strong justified reason; document first-run model downloads and expected size.
- Update README so it accurately describes current features and known limitations, with PowerShell setup/test/build commands.
- Check source distribution contains no virtual environments, Python caches, result data, user sample drawings, private settings or model-weight blobs unless explicitly intended.
- Do not commit/push/publish or upload samples; the user must explicitly approve it.

## Definition of done

Call the MVP finished only when all of the following are true or individually documented as blocked with evidence:

1. Core app starts on Windows using documented steps without requiring OCR installation.
2. Freehand strokes can be drawn, stored, recognized heuristically and displayed as suggestions.
3. Shared model is authoritative and corrections persist across normal operations and save/load.
4. User can select a preview component and correct type/properties; preview and generated source update consistently.
5. Low-confidence components are indicated quietly, can be navigated, and can be corrected without modal nagging.
6. PaddleOCR + binary preprocessing is the recommended optional OCR path when installed; otherwise geometry-only mode works. The historical 19-crop benchmark is explicitly identified as limited and not rerun during recovery. No unsupported accuracy claims.
7. Save/load, undo/redo, code export, and full-bounds sample capture are tested.
8. Generated Python compiles and a representative exported GUI can be smoke-tested.
9. The full focused test suite passes; any native GUI/OCR validations not executable must be listed, not falsely claimed.
10. README and Windows packaging instructions match the actual project. Final report includes files changed, technical findings, before/after OCR metrics and sample count, test outputs, package outputs, limitations, and any manual steps still needed.

## Continue/stop behavior

- Continue phase by phase until the definition of done is met; completing the OCR benchmark alone is not completion.
- If a model is unusable, make the product robust around that limitation (manual text and type correction, optional OCR) and continue the other phases.
- Don't pause to ask the user about routine implementation choices. Use conservative defaults and document them.
- Stop only when done, when a genuine external/permission/usage-limit blocker prevents progress, or before an irreversible/destructive/external action requiring approval. If blocked, complete all other independent phases and leave exact next commands and a checkpoint report.
- Never claim completion merely because a plan, mock-up, or unit test was created. Verify behavior in the real app when possible.
