"""Train a LightGBM baseline ranking model on the labeled feature dataset.

Usage::

    python model/baseline_lightgbm/train.py \\
        --dataset labeling/labeled_dataset.csv \\
        --output  model/baseline_lightgbm/baseline.joblib

If ``--dataset`` is not provided, the script will first generate the dataset
from the default sample BloodHound JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split

# Add project root to path so local imports work when running as a script.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT))

from features.path_features import FEATURE_COLUMNS  # noqa: E402


def _ensure_dataset(dataset_path: Path) -> Path:
    """Generate the dataset if it doesn't exist yet."""
    if dataset_path.exists():
        return dataset_path
    print(f"Dataset not found at {dataset_path} — generating from sample data…")
    from ad_attack_path_predictor.pipeline import generate_labeled_dataset

    sample = _PROJECT_ROOT / "data" / "sample_bloodhound.json"
    rows = generate_labeled_dataset(sample)

    import csv

    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["path_id"] + FEATURE_COLUMNS + ["transparent_score", "label"]
    with dataset_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"  Generated {len(rows)} rows → {dataset_path}")
    return dataset_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a LightGBM baseline ranking model.")
    parser.add_argument(
        "--dataset",
        default="labeling/labeled_dataset.csv",
        help="Path to labeled_dataset.csv (default: labeling/labeled_dataset.csv).",
    )
    parser.add_argument(
        "--output",
        default="model/baseline_lightgbm/baseline.joblib",
        help="Path to save the trained model (default: model/baseline_lightgbm/baseline.joblib).",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.35,
        help="Fraction of data used for testing (default: 0.35).",
    )
    args = parser.parse_args()

    dataset_path = _ensure_dataset(Path(args.dataset))
    df = pd.read_csv(dataset_path)

    print(f"Loaded {len(df)} paths from {dataset_path}")
    print(f"  Positives: {(df['label'] == 1).sum()}")
    print(f"  Negatives: {(df['label'] == 0).sum()}")

    available_features = [col for col in FEATURE_COLUMNS if col in df.columns]
    if not available_features:
        raise SystemExit(f"No feature columns found in dataset. Expected: {FEATURE_COLUMNS}")

    x = df[available_features].values.astype(np.float64)
    y = df["label"].values.astype(int)

    if len(set(y.tolist())) < 2:
        raise SystemExit(
            "Need at least two label classes (positive and negative) for a meaningful "
            "baseline run. Adjust the --threshold in the labeler or add more paths."
        )
    if len(y) < 6:
        raise SystemExit("Need at least 6 labeled paths for train/test split.")

    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=args.test_size, random_state=7, stratify=y,
    )

    try:
        import lightgbm as lgb

        model = lgb.LGBMClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            random_state=7,
            verbosity=-1,
        )
        model_name = "LightGBM"
    except ImportError:
        print("WARNING: lightgbm not installed — falling back to sklearn HistGradientBoosting.")
        from sklearn.ensemble import HistGradientBoostingClassifier

        model = HistGradientBoostingClassifier(max_depth=4, random_state=7)
        model_name = "HistGradientBoosting (fallback)"

    model.fit(x_train, y_train)

    probabilities = model.predict_proba(x_test)[:, 1]
    predictions = (probabilities >= 0.5).astype(int)

    metrics = {
        "model": model_name,
        "features": available_features,
        "average_precision": float(average_precision_score(y_test, probabilities)),
        "precision": float(precision_score(y_test, predictions, zero_division=0)),
        "recall": float(recall_score(y_test, predictions, zero_division=0)),
        "train_size": int(len(y_train)),
        "test_size": int(len(y_test)),
        "positive_rate": float(y.mean()),
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "metrics": metrics, "feature_columns": available_features}, output)

    print(f"\nModel: {model_name}")
    print(f"Saved to: {output}")
    print(f"\nMetrics:")
    print(json.dumps(metrics, indent=2))
    print(f"\nClassification Report (test set):")
    print(classification_report(y_test, predictions, zero_division=0))


if __name__ == "__main__":
    main()
