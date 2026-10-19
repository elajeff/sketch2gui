# Sketch2GUI project instructions

## User and engineering preferences

- The user is a third-year Applied Computer Science student. The code must be understandable and defensible in an interview. Prefer straightforward Python and clear module responsibilities over speculative architecture, frameworks, or clever abstractions.
- Build a real, usable desktop app, not just a demo. Also do not keep expanding scope indefinitely: treat `AUTONOMOUS_BUILD_PLAN.md` as the product contract and completion checklist.
- Inspect the actual working tree, Git status, files, dependency versions, README, test suite, sample data, and existing benchmark outputs before editing. Repository notes can be stale; verify them.
- Preserve existing work. Never delete/overwrite user drawings, project JSON files, truth labels, images, benchmark baselines, result JSON/CSV, or settings. Back up data before any transformations. Write derived samples/results to new folders.
- Do not commit, push, publish a release, upload user data, change Windows startup settings, or perform destructive cleanup without explicit user approval.
- Never invent test outcomes, benchmark metrics, Windows validation, or features. State exactly what ran and what did not.
- Do not lower the test count for optics. Keep tests for distinct realistic failures and public behavior. Consolidate only when the coverage remains obvious and equally strong. Explain removed tests and preserve their meaningful cases.
- Keep README concise and factual, with a subtle emphasis on the technically meaningful parts. Avoid marketing hype and phrases such as “portfolio ready.”
- Prefer PowerShell for Windows instructions. Use pinned/compatible dependencies when required; do not casually upgrade unrelated packages.
- Do not call OCR output certain. It is a suggestion. Users must be able to correct recognized component type and text easily.
- Current OCR default is PaddleOCR PP-OCRv5 mobile English with the measured binary text-line preprocessing path described in `OCR_DECISION.md`. When its optional packages are installed, select Paddle by default; without them, start in geometry-only mode. Do not make TrOCR or any other heavy model a required dependency.
- Historical OCR numbers came from just 19 mouse-written crops and the original files were not recovered. They are context only; do not claim a fresh benchmark or reliable OCR. Continue the rest of the product build without waiting for new samples.
- Avoid running OCR inference on every mouse event. Recognition/OCR should be explicit or triggered at sensible points after a stroke/interpret action.

## Shared model is authoritative

The drawing canvas, recognition layer, properties editor, preview, persistence, and code generator must operate on one shared, serializable design model. Preserve original input strokes and stable element IDs. Recognition produces suggestions; the user can override semantic component type/properties. An explicit user correction must survive subsequent interpretation if its source geometry hasn't changed, unless the user explicitly requests re-recognition/reset.

## Working protocol

1. Read `PROJECT_STATUS.md` and `AUTONOMOUS_BUILD_PLAN.md`.
2. Inspect real code and `git status`; do not overwrite uncommitted changes.
3. Run the baseline tests before changes and retain the output.
4. Work through phases in order and continue without asking the user questions for routine choices. Choose conservative defaults and document them.
5. For each phase, implement, test, update notes, then continue to the next phase. Do not stop just because the OCR investigation is complete.
6. Run focused tests after changes and the full suite at milestones. Add regression tests for found bugs; avoid test bloat.
7. Finish only when the acceptance criteria in `AUTONOMOUS_BUILD_PLAN.md` are met or a real blocker/usage limit prevents more work. If blocked, finish all independent work and give exact blocker/output.
8. Before reporting completion, inspect final diff, build outputs, docs, and ensure no generated caches, model weights, credentials, private samples or virtual environments are accidentally added to the source package.
