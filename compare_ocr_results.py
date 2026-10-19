"""Compare per-engine benchmark JSON reports generated in separate environments."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_engine(path: Path, engine: str) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    details = data.get("engines", {}).get(engine)
    if not details or "exact_match_accuracy" not in details:
        raise ValueError(f"{path} does not contain a completed {engine!r} run")
    return data, details


def sample_truths(data: dict) -> dict[str, str]:
    for engine in data.get("engines", {}).values():
        if isinstance(engine, dict) and isinstance(engine.get("samples"), list):
            return {row["image"]: row["truth"] for row in engine["samples"] if "image" in row and "truth" in row}
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paddle-json", type=Path, required=True)
    parser.add_argument("--trocr-json", type=Path, required=True)
    args = parser.parse_args()
    paddle_data, paddle = load_engine(args.paddle_json, "paddle")
    trocr_data, trocr = load_engine(args.trocr_json, "trocr")
    if sample_truths(paddle_data) != sample_truths(trocr_data):
        parser.error("The two reports do not contain the same image filenames and ground-truth labels")
    print("Same labeled sample set verified. Metrics include inference failures as incorrect predictions.")
    print(f"{'Metric':<28}{'PaddleOCR':>18}{'TrOCR':>18}")
    print("-" * 64)
    for label, key, formatter in (
        ("Exact-match accuracy", "exact_match_accuracy", lambda x: f"{x:.1%}"),
        ("Mean character error rate", "mean_character_error_rate", lambda x: f"{x:.3f}"),
        ("Median inference (ms)", "median_inference_ms", lambda x: "n/a" if x is None else f"{x:.1f}"),
        ("Model load (ms)", "load_time_ms", lambda x: f"{x:.0f}"),
        ("Failed samples", "failed_samples", lambda x: str(x)),
    ):
        a, b = paddle.get(key), trocr.get(key)
        print(f"{label:<28}{formatter(a) if a is not None else 'n/a':>18}{formatter(b) if b is not None else 'n/a':>18}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
