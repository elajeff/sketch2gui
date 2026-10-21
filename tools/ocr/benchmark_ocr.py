"""Compare PaddleOCR and TrOCR on the exact same labeled image samples.

Sample format: image files paired with same-stem .txt files containing ground truth.
Example: python tools/ocr/benchmark_ocr.py --samples benchmark/samples --engines paddle,trocr
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from sketch2gui.ocr import load_backend

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance using O(min(len(a), len(b))) memory."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def raw_exact_match(reference: str, prediction: str) -> bool:
    """Compare original text exactly, including case and whitespace."""
    return reference == prediction


def normalized_exact_match(reference: str, prediction: str) -> bool:
    return normalized(reference) == normalized(prediction)


def cer(reference: str, prediction: str) -> float:
    """Return case/whitespace-normalized character error rate."""
    reference = normalized(reference)
    prediction = normalized(prediction)
    if not reference:
        return 0.0 if not prediction else 1.0
    return edit_distance(reference, prediction) / len(reference)


def discover_samples(directory: Path):
    samples = []
    for image_path in sorted(directory.iterdir()):
        if image_path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        truth_path = image_path.with_suffix(".txt")
        if truth_path.exists():
            truth = truth_path.read_text(encoding="utf-8").strip()
            if truth:
                samples.append((image_path, truth))
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=ROOT / "benchmark" / "samples")
    parser.add_argument("--engines", default="paddle,trocr", help="Comma-separated: paddle,trocr")
    parser.add_argument(
        "--raw-paddle-input", action="store_true",
        help="Disable the app's Paddle preprocessing (use when benchmarking externally prepared tight_pad/binary variants).",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "benchmark" / "results")
    args = parser.parse_args()
    engines = [x.strip().lower() for x in args.engines.split(",") if x.strip()]
    if not engines or any(x not in {"paddle", "trocr"} for x in engines):
        parser.error("--engines must contain paddle and/or trocr")
    if not args.samples.is_dir():
        print(f"Sample folder doesn't exist: {args.samples}", file=sys.stderr)
        return 2
    samples = discover_samples(args.samples)
    if len(samples) < 3:
        print(f"Found {len(samples)} labeled images; add at least 3 paired .png/.txt samples. More is better.", file=sys.stderr)
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    run_details = {"sample_count": len(samples), "samples_directory": str(args.samples), "engines": {}}
    csv_rows = []
    for engine_name in engines:
        print(f"\nLoading {engine_name} (first use may download model files)...", flush=True)
        start_load = time.perf_counter()
        try:
            backend = load_backend(
                engine_name,
                paddle_preprocess=not args.raw_paddle_input if engine_name == "paddle" else True,
            )
        except Exception as exc:
            run_details["engines"][engine_name] = {"error": f"{type(exc).__name__}: {exc}"}
            print(f"Cannot load {engine_name}: {exc}", file=sys.stderr)
            continue
        load_ms = (time.perf_counter() - start_load) * 1000
        records = []
        for index, (path, truth) in enumerate(samples, 1):
            try:
                with Image.open(path) as image:
                    result = backend.recognize(image.copy())
                prediction = result.text.strip()
                duration = result.duration_ms
                if duration is None:
                    duration = 0.0
                record = {"image": path.name, "truth": truth, "prediction": prediction,
                          "exact_match": raw_exact_match(truth, prediction),
                          "normalized_exact_match": normalized_exact_match(truth, prediction),
                          "cer": cer(truth, prediction), "duration_ms": round(duration, 2),
                          "confidence": result.confidence}
                records.append(record)
                csv_rows.append({"engine": engine_name, **record})
                print(f"[{engine_name}] {index}/{len(samples)} {path.name}: {prediction!r} ({duration:.0f} ms)", flush=True)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                records.append({"image": path.name, "truth": truth, "prediction": "", "exact_match": False,
                                "normalized_exact_match": False, "cer": cer(truth, ""),
                                "duration_ms": None, "confidence": None, "error": error})
                csv_rows.append({"engine": engine_name, **records[-1]})
        successful = [row for row in records if "error" not in row]
        scored = [row for row in records if "cer" in row]
        timed = [row for row in successful if isinstance(row.get("duration_ms"), (int, float))]
        summary = {
            "model": getattr(backend, "name", engine_name), "load_time_ms": round(load_ms, 2),
            "sample_count": len(samples), "successful_samples": len(successful), "failed_samples": len(records) - len(successful),
            # Failed inferences count as incorrect/empty, keeping both engines on the same denominator.
            "exact_match_accuracy": (sum(r["exact_match"] for r in scored) / len(samples) if samples else None),
            "normalized_exact_match_accuracy": (sum(r["normalized_exact_match"] for r in scored) / len(samples) if samples else None),
            "mean_character_error_rate": (statistics.mean(r["cer"] for r in scored) if scored else None),
            "median_inference_ms": (statistics.median(r["duration_ms"] for r in timed) if timed else None),
            "samples": records,
        }
        run_details["engines"][engine_name] = summary
        print(f"Summary {engine_name}: exact={summary['exact_match_accuracy']}, CER={summary['mean_character_error_rate']}, median_ms={summary['median_inference_ms']}")

    (args.output / "results.json").write_text(json.dumps(run_details, indent=2, ensure_ascii=False), encoding="utf-8")
    with (args.output / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["engine", "image", "truth", "prediction", "exact_match", "normalized_exact_match", "cer", "duration_ms", "confidence", "error"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(csv_rows)
    loaded = [v for v in run_details["engines"].values() if "exact_match_accuracy" in v]
    print(f"\nResults saved to {args.output / 'results.json'} and results.csv")
    if not loaded:
        print("No OCR engine completed. See results.json for errors.", file=sys.stderr)
        return 1
    if len(loaded) != len(engines):
        print("Comparison incomplete: at least one requested engine failed to load. See results.json; do not declare a winner yet.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
