from __future__ import annotations

from pathlib import Path
from typing import Any

from .enumerate_paths import enumerate_candidate_paths, resolve_start_nodes, resolve_target_nodes
from .ingest import load_bloodhound_json, to_networkx
from .ranker import rank_candidate_paths
from .schemas import RankingResponse


def rank_from_file(
    input_path: str | Path,
    start: str | None = None,
    target: str | None = None,
    top_n: int = 10,
    cutoff: int = 6,
    max_paths: int = 250,
) -> RankingResponse:
    graph = load_bloodhound_json(input_path)
    nx_graph = to_networkx(graph)
    starts = resolve_start_nodes(graph, start)
    targets = resolve_target_nodes(graph, target)
    candidates = enumerate_candidate_paths(graph, nx_graph, starts, targets, cutoff=cutoff, max_paths=max_paths)
    return rank_candidate_paths(graph, candidates, starts, targets, top_n=top_n)


def generate_labeled_dataset(
    input_path: str | Path,
    *,
    cutoff: int = 6,
    max_paths: int = 500,
    label_threshold: float = 0.65,
) -> list[dict[str, Any]]:
    """Run the full pipeline and return a list of feature-vector dicts with labels.

    Each dict contains every column from ``FEATURE_COLUMNS`` plus:
    - ``path_id``: human-readable path identifier
    - ``label``: 1 (high-risk) or 0 (low-risk) based on the transparent score
    - ``transparent_score``: the deterministic ranker score for reference

    This output is written to ``labeled_dataset.csv`` by the synthetic labeler.
    """
    # Local imports to avoid circular dependency issues at module level.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

    from features.centrality import compute_betweenness_centrality
    from features.path_features import FEATURE_COLUMNS, compute_path_feature_vector

    graph = load_bloodhound_json(input_path)
    nx_graph = to_networkx(graph)
    starts = resolve_start_nodes(graph)
    targets = resolve_target_nodes(graph)
    candidates = enumerate_candidate_paths(
        graph, nx_graph, starts, targets, cutoff=cutoff, max_paths=max_paths,
    )

    # Pre-compute centrality once for the whole graph.
    centrality_map = compute_betweenness_centrality(nx_graph)

    # Pre-compute choke-point scores.
    from .features import node_choke_scores, path_identifier
    choke_scores = node_choke_scores(candidates)

    # Build node data lookup for high_value flags.
    node_data = {node.id: node.model_dump() for node in graph.nodes}

    # Compute the transparent ranker score for labeling.
    ranking = rank_candidate_paths(graph, candidates, starts, targets, top_n=len(candidates))

    # Build a score lookup by path_id.
    score_lookup: dict[str, float] = {}
    for rp in ranking.paths:
        score_lookup[rp.path_id] = rp.score

    rows: list[dict[str, Any]] = []
    for nodes, edges in candidates:
        pid = path_identifier(nodes, edges)
        node_ids = [n.id for n in nodes]
        edge_types = [e.type for e in edges]

        features = compute_path_feature_vector(
            node_ids,
            edge_types,
            node_data=node_data,
            centrality_map=centrality_map,
            choke_scores=choke_scores,
        )

        transparent_score = score_lookup.get(pid, 0.0)
        label = 1 if transparent_score >= label_threshold else 0

        row = {"path_id": pid, **features, "transparent_score": transparent_score, "label": label}
        rows.append(row)

    return rows
