"""Full path-level feature vector extraction for Phase 2.

Combines edge composition, hop count, technique prevalence, centrality,
detectability, and all Phase 1 features into a single flat feature dict
suitable for model training.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .edge_features import edge_composition_score, is_loud_edge

_MAPPING_PATH = Path(__file__).resolve().parent / "attck_mapping.json"
_PREVALENCE_PATH = Path(__file__).resolve().parent / "prevalence_weights.json"


@lru_cache(maxsize=1)
def _load_mapping() -> dict[str, dict[str, Any]]:
    with _MAPPING_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def _load_prevalence_weights() -> dict[str, dict[str, Any]]:
    with _PREVALENCE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# Feature column names — the model trains on exactly these numeric columns.
# ---------------------------------------------------------------------------

FEATURE_COLUMNS = [
    "hop_count",
    "unique_edge_types",
    "edge_composition_sum",
    "edge_composition_mean",
    "mean_prevalence",
    "mean_noisiness",
    "max_impact",
    "technique_prevalence_score",
    "max_centrality",
    "mean_centrality",
    "choke_point_score",
    "high_value_steps",
    "quiet_edge_ratio",
    "detectability_flag",
]


def compute_path_feature_vector(
    node_ids: list[str],
    edge_types: list[str],
    *,
    node_data: dict[str, dict[str, Any]] | None = None,
    centrality_map: dict[str, float] | None = None,
    choke_scores: dict[str, float] | None = None,
) -> dict[str, float]:
    """Return a flat dict of numeric features for one path.

    Parameters
    ----------
    node_ids:
        Ordered list of node IDs along the path.
    edge_types:
        Ordered list of edge (relationship) types along the path.
    node_data:
        Optional mapping of node ID → node attributes dict.  Used to read
        ``high_value`` flags.
    centrality_map:
        Optional betweenness centrality map (node ID → float).
    choke_scores:
        Optional choke-point scores (node ID → float).
    """
    mapping = _load_mapping()
    prevalence_weights = _load_prevalence_weights()
    centrality_map = centrality_map or {}
    choke_scores = choke_scores or {}
    node_data = node_data or {}

    # --- edge composition ---
    comp = edge_composition_score(edge_types)

    # --- per-edge ATT&CK profile stats ---
    prevalences: list[float] = []
    noisinesses: list[float] = []
    impacts: list[float] = []
    technique_ids: set[str] = set()

    for edge_type in edge_types:
        profile = mapping.get(edge_type, {})
        prevalences.append(profile.get("prevalence", 0.25))
        noisinesses.append(profile.get("noisiness", 0.55))
        impacts.append(profile.get("impact", 0.35))
        attack_id = profile.get("attack_id", "UNKNOWN")
        if attack_id != "UNKNOWN":
            technique_ids.add(attack_id)

    mean_prevalence = sum(prevalences) / len(prevalences) if prevalences else 0.0
    mean_noisiness = sum(noisinesses) / len(noisinesses) if noisinesses else 0.0
    max_impact = max(impacts) if impacts else 0.0

    # --- technique prevalence score (from prevalence_weights.json) ---
    tech_prev_scores = []
    for tid in technique_ids:
        entry = prevalence_weights.get(tid)
        if entry:
            tech_prev_scores.append(entry["prevalence"])
    technique_prevalence_score = (
        sum(tech_prev_scores) / len(tech_prev_scores) if tech_prev_scores else 0.0
    )

    # --- centrality ---
    node_centralities = [centrality_map.get(nid, 0.0) for nid in node_ids]
    max_centrality = max(node_centralities) if node_centralities else 0.0
    mean_centrality = (
        sum(node_centralities) / len(node_centralities) if node_centralities else 0.0
    )

    # --- choke point ---
    inner_nodes = node_ids[1:-1]
    choke_point_score = (
        max(choke_scores.get(nid, 0.0) for nid in inner_nodes) if inner_nodes else 0.0
    )

    # --- high value ---
    high_value_steps = sum(
        1 for nid in node_ids if node_data.get(nid, {}).get("high_value", False)
    )

    # --- quiet edge ratio ---
    quiet_count = sum(1 for n in noisinesses if n <= 0.45)
    quiet_edge_ratio = quiet_count / len(noisinesses) if noisinesses else 0.0

    # --- detectability ---
    detectability_flag = 1.0 if any(is_loud_edge(et) for et in edge_types) else 0.0

    return {
        "hop_count": float(len(edge_types)),
        "unique_edge_types": float(len(set(edge_types))),
        "edge_composition_sum": comp["sum"],
        "edge_composition_mean": comp["mean"],
        "mean_prevalence": mean_prevalence,
        "mean_noisiness": mean_noisiness,
        "max_impact": max_impact,
        "technique_prevalence_score": technique_prevalence_score,
        "max_centrality": max_centrality,
        "mean_centrality": mean_centrality,
        "choke_point_score": choke_point_score,
        "high_value_steps": float(high_value_steps),
        "quiet_edge_ratio": quiet_edge_ratio,
        "detectability_flag": detectability_flag,
    }
