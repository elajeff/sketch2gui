# Autonomous task entry point — end-to-end Sketch2GUI MVP

Read `AGENTS.md`, `PROJECT_STATUS.md`, `OCR_DECISION.md`, and `AUTONOMOUS_BUILD_PLAN.md` in full.

This is an end-to-end product task. Do not stop after OCR benchmarking. Use PaddleOCR PP-OCRv5 mobile English plus the implemented binary preprocessing as the selected OCR path for now, but keep OCR optional. The app should choose Paddle by default only when its dependencies exist; otherwise start in geometry-only mode.

The old 19 handwritten crops and raw OCR result files are missing from the recovered archives. Treat the metrics in `OCR_DECISION.md` as historical context only; do not invent recreated samples or claim a fresh benchmark. Do not wait for more sample images to continue app implementation.

Continue phase by phase until the plan's definition of done is satisfied or a genuine blocker/usage limit prevents further work. Preserve any user files and existing results. Don't delete tests merely to reduce test count. Don't commit, push, publish, upload user data, or perform destructive operations without approval.

At completion, report changed files, actual OCR decision, exact test/build commands and results, real Windows smoke-test status, generated package paths, limitations, and blocked acceptance criteria. If interrupted, leave a concise verified checkpoint.
