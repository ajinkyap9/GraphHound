from __future__ import annotations

from collections import Counter

from .attck import get_profile, load_edge_profiles
from .schemas import AttackEdge, AttackNode, PathFeatures


def path_identifier(nodes: list[AttackNode], edges: list[AttackEdge]) -> str:
    material = []
    for index, node in enumerate(nodes):
        material.append(node.id)
        if index < len(edges):
            material.append(edges[index].type)
    return " -> ".join(material)


def node_choke_scores(paths: list[tuple[list[AttackNode], list[AttackEdge]]]) -> dict[str, float]:
    counts: Counter[str] = Counter()
    for nodes, _ in paths:
        for node in nodes[1:-1]:
            counts[node.id] += 1
    if not counts:
        return {}
    max_count = max(counts.values())
    return {node_id: count / max_count for node_id, count in counts.items()}


def extract_path_features(
    nodes: list[AttackNode],
    edges: list[AttackEdge],
    choke_scores: dict[str, float] | None = None,
) -> PathFeatures:
    profiles = load_edge_profiles()
    edge_profiles = [get_profile(edge.type, profiles) for edge in edges]
    prevalence = [profile.prevalence for profile in edge_profiles]
    noisiness = [profile.noisiness for profile in edge_profiles]
    impacts = [profile.impact for profile in edge_profiles]
    techniques = sorted({profile.attack_id for profile in edge_profiles if profile.attack_id != "UNKNOWN"})
    edge_types = [edge.type for edge in edges]
    inner_nodes = nodes[1:-1]
    choke = max((choke_scores or {}).get(node.id, 0.0) for node in inner_nodes) if inner_nodes else 0.0

    return PathFeatures(
        path_id=path_identifier(nodes, edges),
        node_ids=[node.id for node in nodes],
        edge_types=edge_types,
        length=len(edges),
        unique_edge_types=len(set(edge_types)),
        mean_prevalence=sum(prevalence) / len(prevalence) if prevalence else 0.0,
        mean_noisiness=sum(noisiness) / len(noisiness) if noisiness else 0.0,
        max_impact=max(impacts) if impacts else 0.0,
        choke_point_score=choke,
        high_value_steps=sum(1 for node in nodes if node.high_value),
        quiet_edge_ratio=sum(1 for value in noisiness if value <= 0.45) / len(noisiness) if noisiness else 0.0,
        technique_ids=techniques,
    )

