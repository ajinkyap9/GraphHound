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
    allow_edge_simulation: bool = False,
) -> RankingResponse:
    import sys
    
    graph = load_bloodhound_json(input_path)
    
    # Issue 4: HasSession check
    has_session = any(edge.type == "HasSession" for edge in graph.edges)
    if not has_session:
        sys.stderr.write("WARNING: No HasSession edges detected in graph.\n"
                         "Lateral movement paths through active sessions\n"
                         "are not visible. Re-collect with SharpHound\n"
                         "using -c All flag for complete session data.\n")
        
    has_acl = any(edge.type in {"GenericAll", "GenericWrite", "WriteDacl", "WriteOwner", "AllExtendedRights", "Owns"} for edge in graph.edges)
    has_gpo = any(edge.type == "GPLink" for edge in graph.edges)
    
    # Environment detection
    env_type = "Unknown"
    domain_names = {node.properties.get("domain", "").lower() for node in graph.nodes if node.properties.get("domain")}
    node_names = {node.name.lower() for node in graph.nodes}
    
    if any("spookysec" in d or "spookysec" in n for d in domain_names for n in node_names):
        env_type = "THM"
    elif any("corp.local" in d or "goad" in d for d in domain_names):
        env_type = "Synthetic"
    
    # Issue 2: Detect dead-end owned nodes
    # Resolve starting nodes
    starts = resolve_start_nodes(graph, start)
    targets = resolve_target_nodes(graph, target)
    
    # We build a temporary nx_graph to check connectivity for each start node
    temp_nx_graph = to_networkx(graph)
    
    edge_simulation_used = False
    valid_starts = []
    
    for s in starts:
        # Check if this start node has any outbound ACL edges (excluding MemberOf)
        has_outbound_acl = any(edge.source == s and edge.type != "MemberOf" for edge in graph.edges)
        
        # Test if it can reach any targets in the current graph
        temp_paths = enumerate_candidate_paths(graph, temp_nx_graph, [s], targets, cutoff=cutoff, max_paths=1)
        
        if not has_outbound_acl and len(temp_paths) == 0:
            s_node = next((n for n in graph.nodes if n.id == s), None)
            s_name = s_node.name if s_node else s
            if allow_edge_simulation:
                # Find if backup is also in the graph
                backup_node = next((n for n in graph.nodes if "backup" in n.name.lower()), None)
                if backup_node:
                    from .schemas import AttackEdge
                    graph.edges.append(AttackEdge(
                        source=s,
                        target=backup_node.id,
                        type="GenericAll",
                        properties={"RightName": "GenericAll", "IsInherited": False}
                    ))
                    # Mark it as owned to ensure it resolves
                    s_node.owned = True
                    edge_simulation_used = True
                    sys.stderr.write(f"NOTE: Simulated edge injected for validation purposes. Results reflect downstream chain validation only, not initial access discovery.\n")
                    valid_starts.append(s)
            else:
                sys.stderr.write(f"WARNING: {s_name} has no outbound ACL edges in the BloodHound graph. This node may require out-of-band credential context (SMB shares, password spraying etc.) not captured in ACL graphs. Skipping automatic path enumeration from this node.\n")
        else:
            valid_starts.append(s)
            
    nx_graph = to_networkx(graph)
    candidates = enumerate_candidate_paths(graph, nx_graph, valid_starts, targets, cutoff=cutoff, max_paths=max_paths)
    
    res = rank_candidate_paths(graph, candidates, valid_starts, targets, top_n=top_n)
    
    # Update summary metadata
    res.summary.has_session = has_session
    res.summary.has_acl = has_acl
    res.summary.has_gpo = has_gpo
    res.summary.environment_type = env_type
    res.summary.edge_simulation_used = edge_simulation_used
    
    return res



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

    # Issue 3: rank-based labeling on small graphs (< 50 paths)
    small_graph = len(candidates) < 50
    if small_graph:
        sys.stderr.write(f"Small graph detected ({len(candidates)} paths) — using rank-based labeling. Precision metrics reflect relative ranking quality, not absolute exploitability.\n")
        # Sort candidates by score descending to find the top 30% cutoff
        sorted_candidates = sorted(candidates, key=lambda c: score_lookup.get(path_identifier(c[0], c[1]), 0.0), reverse=True)
        num_positives = max(1, int(len(candidates) * 0.3))
        positive_pids = {path_identifier(c[0], c[1]) for c in sorted_candidates[:num_positives]}

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
        if small_graph:
            label = 1 if pid in positive_pids else 0
        else:
            label = 1 if transparent_score >= label_threshold else 0

        row = {"path_id": pid, **features, "transparent_score": transparent_score, "label": label}
        rows.append(row)

    return rows
