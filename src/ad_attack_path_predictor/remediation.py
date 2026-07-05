from __future__ import annotations

from collections import OrderedDict

from .attck import get_profile, load_edge_profiles
from .schemas import AttackEdge, AttackNode, PathFeatures


def explain_path(features: PathFeatures) -> list[str]:
    explanations: list[str] = []
    if features.max_impact >= 0.85:
        explanations.append("Contains at least one high-impact control edge that can materially change privilege.")
    if features.mean_prevalence >= 0.6:
        explanations.append("Uses techniques with strong public incident prevalence.")
    if features.quiet_edge_ratio >= 0.5:
        explanations.append("Mostly quiet relationships, so the path may be harder to detect in real time.")
    if features.choke_point_score >= 0.7:
        explanations.append("Passes through a graph choke point that appears in many candidate paths.")
    if features.length <= 3:
        explanations.append("Short path with few required steps.")
    if not explanations:
        explanations.append("Risk is driven by the combined path structure and edge profile.")
    return explanations


def recommend_remediation(nodes: list[AttackNode], edges: list[AttackEdge]) -> list[str]:
    profiles = load_edge_profiles()
    recommendations: OrderedDict[str, None] = OrderedDict()
    for edge in sorted(edges, key=lambda item: get_profile(item.type, profiles).impact, reverse=True):
        source = next((node for node in nodes if node.id == edge.source), None)
        target = next((node for node in nodes if node.id == edge.target), None)
        profile = get_profile(edge.type, profiles)
        source_name = source.name if source else edge.source
        target_name = target.name if target else edge.target
        recommendations[f"{profile.remediation} Relationship: {source_name} -> {target_name}."] = None
    return list(recommendations.keys())[:4]

