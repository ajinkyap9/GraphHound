"""Evaluate the trained baseline model and produce ranked output.

Usage::

    python model/baseline_lightgbm/evaluate.py \\
        --model   model/baseline_lightgbm/baseline.joblib \\
        --dataset labeling/labeled_dataset.csv \\
        --output  model/baseline_lightgbm/ranked_output_sample.csv

The script:
1. Loads the trained model and the labeled dataset.
2. Scores every path with the model.
3. Ranks paths by predicted probability.
4. Checks whether seeded ground-truth paths (label=1) appear in the top 20%.
5. Writes ``ranked_output_sample.csv`` for manual review.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_score, recall_score

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT))

from features.path_features import FEATURE_COLUMNS  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the baseline ranking model.")
    parser.add_argument(
        "--model",
        default="model/baseline_lightgbm/baseline.joblib",
        help="Path to the trained model .joblib file.",
    )
    parser.add_argument(
        "--dataset",
        default="labeling/labeled_dataset.csv",
        help="Path to labeled_dataset.csv.",
    )
    parser.add_argument(
        "--output",
        default="model/baseline_lightgbm/ranked_output_sample.csv",
        help="Path to write the ranked output CSV.",
    )
    args = parser.parse_args()

    # Load model.
    bundle = joblib.load(args.model)
    model = bundle["model"]
    feature_cols = bundle.get("feature_columns", FEATURE_COLUMNS)

    # Load dataset.
    df = pd.read_csv(args.dataset)
    available_features = [col for col in feature_cols if col in df.columns]
    x = df[available_features].values.astype(np.float64)

    # Score all paths.
    probabilities = model.predict_proba(x)[:, 1]
    df["model_score"] = probabilities
    df["model_rank"] = df["model_score"].rank(ascending=False, method="min").astype(int)

    # Sort by model score descending.
    df = df.sort_values("model_score", ascending=False).reset_index(drop=True)

    # --- Sanity Check: do seeded paths rank in top 20%? ---
    total_paths = len(df)
    top_20_cutoff = max(1, int(total_paths * 0.20))
    top_20_df = df.head(top_20_cutoff)

    positive_paths = df[df["label"] == 1]
    positives_in_top_20 = top_20_df[top_20_df["label"] == 1]

    total_positives = len(positive_paths)
    found_in_top_20 = len(positives_in_top_20)

    print("=" * 60)
    print("EVALUATION RESULTS")
    print("=" * 60)
    print(f"Total paths:            {total_paths}")
    print(f"Top 20% cutoff:         {top_20_cutoff}")
    print(f"Ground-truth positives: {total_positives}")
    print(f"Positives in top 20%:   {found_in_top_20}")
    print()

    if total_positives > 0:
        recall_at_20 = found_in_top_20 / total_positives
        print(f"Recall@20%:             {recall_at_20:.2%}")
    else:
        recall_at_20 = 0.0
        print("No positive labels in dataset — cannot compute recall.")

    # Sanity check verdict.
    if total_positives > 0 and found_in_top_20 == total_positives:
        verdict = "PASS — All seeded paths rank in top 20%"
    elif total_positives > 0 and found_in_top_20 > 0:
        verdict = f"PARTIAL — {found_in_top_20}/{total_positives} seeded paths in top 20%"
    elif total_positives > 0:
        verdict = "FAIL — No seeded paths in top 20%"
    else:
        verdict = "N/A — No positive labels"

    print(f"\nSanity Check:           {verdict}")
    print()

    # Full metrics.
    if total_positives > 0 and total_positives < total_paths:
        predictions = (probabilities >= 0.5).astype(int)
        labels = df["label"].values
        metrics = {
            "average_precision": float(average_precision_score(labels, probabilities)),
            "precision": float(precision_score(labels, predictions, zero_division=0)),
            "recall": float(recall_score(labels, predictions, zero_division=0)),
            "recall_at_20_pct": float(recall_at_20),
            "sanity_check": verdict,
        }
        print("Metrics:")
        print(json.dumps(metrics, indent=2))

    # Write ranked output.
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)
    print(f"\nRanked output written to: {output}")

    # Print top 10 paths.
    print(f"\nTop 10 ranked paths:")
    print("-" * 60)
    for i, row in df.head(10).iterrows():
        label_tag = " [SEEDED]" if row["label"] == 1 else ""
        print(f"  Rank {row['model_rank']:3d} | Score {row['model_score']:.4f} | {row['path_id']}{label_tag}")


if __name__ == "__main__":
    main()
