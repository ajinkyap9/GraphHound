from __future__ import annotations

import math

from .features import extract_path_features, node_choke_scores
from .remediation import explain_path, recommend_remediation
from .schemas import AttackEdge, AttackGraph, AttackNode, RankedPath, RankingResponse, RankingSummary


def score_features(
    mean_prevalence: float,
    mean_noisiness: float,
    max_impact: float,
    choke_point_score: float,
    quiet_edge_ratio: float,
    length: int,
) -> float:
    length_penalty = min(0.28, max(0, length - 2) * 0.055)
    raw = (
        0.34 * max_impact
        + 0.25 * mean_prevalence
        + 0.16 * quiet_edge_ratio
        + 0.15 * choke_point_score
        + 0.10 * (1 - mean_noisiness)
        - length_penalty
    )
    calibrated = 1 / (1 + math.exp(-6 * (raw - 0.42)))
    return round(max(0.0, min(1.0, calibrated)), 4)


def confidence_for(score: float, length: int) -> str:
    if score >= 0.75 and length <= 5:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def rank_candidate_paths(
    graph: AttackGraph,
    candidate_paths: list[tuple[list[AttackNode], list[AttackEdge]]],
    starts: list[str],
    targets: list[str],
    top_n: int = 10,
) -> RankingResponse:
    choke_scores = node_choke_scores(candidate_paths)
    ranked: list[RankedPath] = []

    for nodes, edges in candidate_paths:
        features = extract_path_features(nodes, edges, choke_scores)
        score = score_features(
            features.mean_prevalence,
            features.mean_noisiness,
            features.max_impact,
            features.choke_point_score,
            features.quiet_edge_ratio,
            features.length,
        )
        ranked.append(
            RankedPath(
                rank=0,
                path_id=features.path_id,
                score=score,
                confidence=confidence_for(score, features.length),
                nodes=nodes,
                edges=edges,
                features=features,
                explanations=explain_path(features),
                remediation=recommend_remediation(nodes, edges),
            )
        )

    ranked.sort(key=lambda item: (item.score, -item.features.length), reverse=True)
    selected = ranked[:top_n]
    for index, path in enumerate(selected, start=1):
        path.rank = index

    return RankingResponse(
        summary=RankingSummary(
            graph_nodes=len(graph.nodes),
            graph_edges=len(graph.edges),
            candidate_paths=len(candidate_paths),
            returned_paths=len(selected),
            start_nodes=starts,
            target_nodes=targets,
            top_score=selected[0].score if selected else None,
        ),
        paths=selected,
    )

