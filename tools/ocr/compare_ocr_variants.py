"""Compare PaddleOCR preprocessing variants against an original baseline JSON.

Usage:
    python tools/ocr/compare_ocr_variants.py --baseline benchmark/results-paddle/results.json --variants-root benchmark/results-paddle-variants

The variants root should contain tight_pad/results.json, thicker_ink/results.json,
and binary/results.json, each created by benchmark_ocr.py.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def norm(text: str) -> str:
    return " ".join(text.casefold().split())


def load(path: Path) -> tuple[dict, dict, dict[str, dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    details = data.get("engines", {}).get("paddle")
    if not isinstance(details, dict) or "samples" not in details:
        raise ValueError(f"No completed PaddleOCR results in {path}")
    rows = {row["image"]: row for row in details["samples"] if "image" in row}
    return data, details, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--variants-root", type=Path, required=True)
    args = parser.parse_args()

    _, base, base_rows = load(args.baseline)
    results = [("original", base)]

    for variant in ("tight_pad", "thicker_ink", "binary"):
        path = args.variants_root / variant / "results.json"
        if not path.is_file():
            print(f"Skipping {variant}: missing {path}")
            continue
        _, details, rows = load(path)
        base_truth = {name: row.get("truth", "") for name, row in base_rows.items()}
        other_truth = {name: row.get("truth", "") for name, row in rows.items()}
        if base_truth != other_truth:
            parser.error(f"{variant} results do not contain the same image names and expected labels as baseline")
        improvements = 0
        regressions = 0
        for name, row in rows.items():
            before = base_rows[name].get("cer", 1.0)
            after = row.get("cer", 1.0)
            if after < before:
                improvements += 1
            elif after > before:
                regressions += 1
        results.append((variant, {**details, "improved_samples": improvements, "worsened_samples": regressions}))

    print("PaddleOCR preprocessing comparison (same labeled samples)")
    print(f"{'Variant':<16}{'Exact match':>14}{'Mean CER':>12}{'Median ms':>12}{'Better CER':>13}{'Worse CER':>12}")
    print("-" * 79)
    for name, detail in results:
        exact = detail.get("exact_match_accuracy")
        cer = detail.get("mean_character_error_rate")
        median = detail.get("median_inference_ms")
        better = detail.get("improved_samples", "-")
        worse = detail.get("worsened_samples", "-")
        print(
            f"{name:<16}{(f'{exact:.1%}' if exact is not None else 'n/a'):>14}"
            f"{(f'{cer:.3f}' if cer is not None else 'n/a'):>12}"
            f"{(f'{median:.1f}' if median is not None else 'n/a'):>12}"
            f"{str(better):>13}{str(worse):>12}"
        )

    if len(results) == 1:
        print("\nNo variant result files were found yet; run each variant benchmark first.")
    print("\nTreat small differences as tentative on this exploratory sample set.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
