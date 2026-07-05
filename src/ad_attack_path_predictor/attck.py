from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .schemas import EdgeRiskProfile

DEFAULT_MAPPING_PATH = Path(__file__).resolve().parents[2] / "features" / "attck_mapping.json"


@lru_cache(maxsize=4)
def load_edge_profiles(mapping_path: str | None = None) -> dict[str, EdgeRiskProfile]:
    path = Path(mapping_path) if mapping_path else DEFAULT_MAPPING_PATH
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return {
        edge_type: EdgeRiskProfile(edge_type=edge_type, **profile)
        for edge_type, profile in raw.items()
    }


def get_profile(edge_type: str, profiles: dict[str, EdgeRiskProfile] | None = None) -> EdgeRiskProfile:
    table = profiles or load_edge_profiles()
    if edge_type in table:
        return table[edge_type]
    return EdgeRiskProfile(
        edge_type=edge_type,
        attack_id="UNKNOWN",
        tactic="Unknown",
        prevalence=0.25,
        noisiness=0.55,
        impact=0.35,
        remediation=f"Review and validate the {edge_type} relationship; remove it if unnecessary.",
    )

