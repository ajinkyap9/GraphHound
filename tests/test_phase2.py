"""Phase 2 tests — feature extraction, centrality, labeling, training, and evaluation.

Tests run against the existing ``data/sample_bloodhound.json`` so no external
database or lab export is required.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure project root is on the import path.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

SAMPLE = ROOT / "data" / "sample_bloodhound.json"


# ---------------------------------------------------------------------------
# Test: Centrality computation
# ---------------------------------------------------------------------------


class TestCentrality:
    def test_betweenness_centrality_returns_all_nodes(self):
        from ad_attack_path_predictor.ingest import load_bloodhound_json, to_networkx
        from features.centrality import compute_betweenness_centrality

        graph = load_bloodhound_json(SAMPLE)
        nx_graph = to_networkx(graph)
        centrality = compute_betweenness_centrality(nx_graph)

        assert len(centrality) == len(graph.nodes)
        assert all(isinstance(v, float) for v in centrality.values())
        assert all(0.0 <= v <= 1.0 for v in centrality.values())

    def test_degree_centrality_returns_all_nodes(self):
        from ad_attack_path_predictor.ingest import load_bloodhound_json, to_networkx
        from features.centrality import compute_degree_centrality

        graph = load_bloodhound_json(SAMPLE)
        nx_graph = to_networkx(graph)
        centrality = compute_degree_centrality(nx_graph)

        assert len(centrality) == len(graph.nodes)
        assert all(isinstance(v, float) for v in centrality.values())


# ---------------------------------------------------------------------------
# Test: Edge features
# ---------------------------------------------------------------------------


class TestEdgeFeatures:
    def test_known_edge_has_positive_risk_weight(self):
        from features.edge_features import edge_risk_weight

        weight = edge_risk_weight("GenericAll")
        assert weight > 0.0
        assert weight <= 1.0

    def test_unknown_edge_gets_default_weight(self):
        from features.edge_features import edge_risk_weight

        weight = edge_risk_weight("NonExistentEdgeType")
        assert weight == 0.15

    def test_edge_composition_score_with_real_edges(self):
        from features.edge_features import edge_composition_score

        result = edge_composition_score(["GenericAll", "MemberOf", "DCSync"])
        assert result["sum"] > 0.0
        assert result["mean"] > 0.0
        assert result["sum"] >= result["mean"]

    def test_edge_composition_score_empty(self):
        from features.edge_features import edge_composition_score

        result = edge_composition_score([])
        assert result["sum"] == 0.0
        assert result["mean"] == 0.0

    def test_loud_edge_detection(self):
        from features.edge_features import is_loud_edge

        assert is_loud_edge("DCSync") is True
        assert is_loud_edge("AllowedToDelegate") is True
        assert is_loud_edge("MemberOf") is False


# ---------------------------------------------------------------------------
# Test: Path features
# ---------------------------------------------------------------------------


class TestPathFeatures:
    def test_feature_vector_has_all_columns(self):
        from features.path_features import FEATURE_COLUMNS, compute_path_feature_vector

        features = compute_path_feature_vector(
            node_ids=["j.doe", "helpdesk", "svc.backup", "domain-admins"],
            edge_types=["MemberOf", "GenericAll", "AddMember"],
        )

        for col in FEATURE_COLUMNS:
            assert col in features, f"Missing feature column: {col}"
            assert features[col] is not None, f"Feature {col} is None"
            assert isinstance(features[col], (int, float)), f"Feature {col} is not numeric"

    def test_no_null_features(self):
        """Every feature must have a non-null value — Phase 2 evaluation criterion."""
        from features.path_features import FEATURE_COLUMNS, compute_path_feature_vector

        features = compute_path_feature_vector(
            node_ids=["j.doe", "sql01", "svc.sql", "server-ops", "dc01", "domain"],
            edge_types=["CanRDP", "HasSession", "GenericWrite", "AdminTo", "DCSync"],
        )

        for col in FEATURE_COLUMNS:
            assert features[col] is not None
            assert not (isinstance(features[col], float) and np.isnan(features[col]))

    def test_detectability_flag_set_for_dcsync(self):
        from features.path_features import compute_path_feature_vector

        features = compute_path_feature_vector(
            node_ids=["a", "b", "c"],
            edge_types=["MemberOf", "DCSync"],
        )
        assert features["detectability_flag"] == 1.0

    def test_detectability_flag_clear_for_quiet_path(self):
        from features.path_features import compute_path_feature_vector

        features = compute_path_feature_vector(
            node_ids=["a", "b", "c"],
            edge_types=["MemberOf", "MemberOf"],
        )
        assert features["detectability_flag"] == 0.0

    def test_centrality_used_when_provided(self):
        from features.path_features import compute_path_feature_vector

        centrality = {"a": 0.1, "b": 0.9, "c": 0.2}
        features = compute_path_feature_vector(
            node_ids=["a", "b", "c"],
            edge_types=["MemberOf", "GenericAll"],
            centrality_map=centrality,
        )
        assert features["max_centrality"] == 0.9
        assert features["mean_centrality"] > 0.0

    def test_high_value_steps_counted(self):
        from features.path_features import compute_path_feature_vector

        node_data = {
            "a": {"high_value": False},
            "b": {"high_value": True},
            "c": {"high_value": True},
        }
        features = compute_path_feature_vector(
            node_ids=["a", "b", "c"],
            edge_types=["MemberOf", "GenericAll"],
            node_data=node_data,
        )
        assert features["high_value_steps"] == 2.0


# ---------------------------------------------------------------------------
# Test: Labeled dataset generation
# ---------------------------------------------------------------------------


class TestLabeledDataset:
    def test_generate_labeled_dataset_produces_rows(self):
        from ad_attack_path_predictor.pipeline import generate_labeled_dataset
        from features.path_features import FEATURE_COLUMNS

        rows = generate_labeled_dataset(SAMPLE, max_paths=100)

        assert len(rows) > 0, "No paths generated"
        for row in rows:
            assert "path_id" in row
            assert "label" in row
            assert row["label"] in (0, 1)
            assert "transparent_score" in row
            for col in FEATURE_COLUMNS:
                assert col in row, f"Missing feature: {col}"
                assert row[col] is not None, f"Null feature: {col}"

    def test_label_distribution_has_both_classes(self):
        from ad_attack_path_predictor.pipeline import generate_labeled_dataset

        # Use a higher threshold (0.80) for the small sample graph since
        # all paths score >= 0.65 on this tiny graph.  On a real lab export
        # with hundreds of paths, the default 0.65 threshold works.
        rows = generate_labeled_dataset(SAMPLE, max_paths=100, label_threshold=0.80)
        labels = {row["label"] for row in rows}

        # The sample graph should produce both positive and negative labels.
        assert 1 in labels, "No positive labels — threshold may be too high"
        assert 0 in labels, "No negative labels — threshold may be too low"

    def test_feature_count_matches_spec(self):
        """Every row should have exactly the 14 feature columns defined in Phase 2."""
        from ad_attack_path_predictor.pipeline import generate_labeled_dataset
        from features.path_features import FEATURE_COLUMNS

        rows = generate_labeled_dataset(SAMPLE, max_paths=50)
        assert len(FEATURE_COLUMNS) == 14
        for row in rows:
            for col in FEATURE_COLUMNS:
                assert col in row


# ---------------------------------------------------------------------------
# Test: Training pipeline (end-to-end on sample data)
# ---------------------------------------------------------------------------


class TestTrainingPipeline:
    def test_model_trains_and_produces_metrics(self, tmp_path):
        """Train a model end-to-end on sample data and verify it produces metrics."""
        from ad_attack_path_predictor.pipeline import generate_labeled_dataset
        from features.path_features import FEATURE_COLUMNS

        rows = generate_labeled_dataset(SAMPLE, max_paths=100, label_threshold=0.80)

        # Write to temp CSV.
        csv_path = tmp_path / "test_dataset.csv"
        fieldnames = ["path_id"] + FEATURE_COLUMNS + ["transparent_score", "label"]
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

        import pandas as pd

        df = pd.read_csv(csv_path)
        available = [col for col in FEATURE_COLUMNS if col in df.columns]
        x = df[available].values.astype(np.float64)
        y = df["label"].values.astype(int)

        if len(set(y.tolist())) < 2 or len(y) < 6:
            pytest.skip("Not enough data variety for training test")

        from sklearn.model_selection import train_test_split

        x_train, x_test, y_train, y_test = train_test_split(
            x, y, test_size=0.35, random_state=7, stratify=y,
        )

        # Try LightGBM, fall back to sklearn.
        try:
            import lightgbm as lgb

            model = lgb.LGBMClassifier(n_estimators=50, max_depth=3, verbosity=-1, random_state=7)
        except ImportError:
            from sklearn.ensemble import HistGradientBoostingClassifier

            model = HistGradientBoostingClassifier(max_depth=3, random_state=7)

        model.fit(x_train, y_train)
        probs = model.predict_proba(x_test)[:, 1]

        assert probs.shape[0] == len(y_test)
        assert all(0.0 <= p <= 1.0 for p in probs)


# ---------------------------------------------------------------------------
# Test: Sanity check — seeded paths rank high
# ---------------------------------------------------------------------------


class TestSanityCheck:
    def test_seeded_paths_rank_in_top_half(self):
        """Seeded ground-truth paths should rank in the top 50% at minimum.

        Uses a higher label threshold (0.80) to create a meaningful split
        on the small sample graph.  The Phase 2 doc asks for top 20% on
        the full lab export — that check is in ``evaluate.py``.
        """
        from ad_attack_path_predictor.pipeline import generate_labeled_dataset

        rows = generate_labeled_dataset(SAMPLE, max_paths=100, label_threshold=0.80)
        # Sort by transparent score descending (proxy for model ranking).
        rows.sort(key=lambda r: r["transparent_score"], reverse=True)

        positives = [r for r in rows if r["label"] == 1]
        if not positives:
            pytest.skip("No positive labels in sample data")

        # On this small graph all positives should be in the top portion.
        top_half = max(len(positives), len(rows) // 2)
        top_half_ids = {r["path_id"] for r in rows[:top_half]}

        for pos in positives:
            assert pos["path_id"] in top_half_ids, (
                f"Seeded path not in top 50%: {pos['path_id']} "
                f"(score={pos['transparent_score']:.4f})"
            )


# ---------------------------------------------------------------------------
# Test: Existing Phase 1 tests still pass (regression check)
# ---------------------------------------------------------------------------


class TestPhase1Regression:
    def test_load_sample_graph(self):
        from ad_attack_path_predictor.ingest import load_bloodhound_json

        graph = load_bloodhound_json(SAMPLE)
        assert len(graph.nodes) == 11
        assert len(graph.edges) == 14

    def test_ranked_paths_sorted(self):
        from ad_attack_path_predictor.pipeline import rank_from_file

        response = rank_from_file(SAMPLE, top_n=5)
        scores = [p.score for p in response.paths]
        assert scores == sorted(scores, reverse=True)
