"""Synthetic labeling pipeline for Phase 2.

Runs the full pipeline (ingest → enumerate → feature extract → label) and
writes ``labeled_dataset.csv`` — the training input for the LightGBM baseline.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Ensure project root is on the import path when running as a script.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT))

from ad_attack_path_predictor.pipeline import generate_labeled_dataset
from features.path_features import FEATURE_COLUMNS


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate labeled feature dataset from BloodHound-style JSON.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to BloodHound-style JSON file.",
    )
    parser.add_argument(
        "--output",
        default="labeling/labeled_dataset.csv",
        help="Output CSV path (default: labeling/labeled_dataset.csv).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.65,
        help="Score threshold for positive label (default: 0.65).",
    )
    parser.add_argument(
        "--cutoff",
        type=int,
        default=6,
        help="Maximum path hop depth (default: 6).",
    )
    parser.add_argument(
        "--max-paths",
        type=int,
        default=500,
        help="Maximum number of candidate paths (default: 500).",
    )
    args = parser.parse_args()

    rows = generate_labeled_dataset(
        args.input,
        cutoff=args.cutoff,
        max_paths=args.max_paths,
        label_threshold=args.threshold,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["path_id"] + FEATURE_COLUMNS + ["transparent_score", "label"]

    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    positives = sum(1 for r in rows if r["label"] == 1)
    negatives = len(rows) - positives
    print(f"Wrote {len(rows)} paths to {output}")
    print(f"  Positives (label=1): {positives}")
    print(f"  Negatives (label=0): {negatives}")


if __name__ == "__main__":
    main()
