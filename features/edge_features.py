"""Edge-level risk weighting for attack paths.

Maps each BloodHound edge type to a numeric risk weight derived from
the ATT&CK mapping (impact * prevalence). Provides functions to score
individual edges and compute path-level edge composition scores.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


_MAPPING_PATH = Path(__file__).resolve().parent / "attck_mapping.json"

# Edges where the underlying technique is inherently noisy / easy to detect.
LOUD_EDGE_TYPES = frozenset({"DCSync", "AllowedToDelegate"})


@lru_cache(maxsize=1)
def _load_mapping() -> dict[str, dict[str, Any]]:
    with _MAPPING_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def edge_risk_weight(edge_type: str) -> float:
    """Return a risk weight in [0, 1] for *edge_type*.

    The weight is ``impact * prevalence`` from the ATT&CK mapping.
    Unknown edge types get a conservative default of 0.15.
    """
    mapping = _load_mapping()
    profile = mapping.get(edge_type)
    if profile is None:
        return 0.15
    return profile["impact"] * profile["prevalence"]


def edge_composition_score(edge_types: list[str]) -> dict[str, float]:
    """Return sum and mean of risk weights for a sequence of edge types.

    Returns a dict with keys ``sum`` and ``mean``.
    """
    if not edge_types:
        return {"sum": 0.0, "mean": 0.0}
    weights = [edge_risk_weight(edge_type) for edge_type in edge_types]
    return {"sum": sum(weights), "mean": sum(weights) / len(weights)}


def is_loud_edge(edge_type: str) -> bool:
    """Return True if *edge_type* is an inherently noisy technique."""
    return edge_type in LOUD_EDGE_TYPES
