import numpy as np
import torch
from ad_attack_path_predictor.ingest import load_bloodhound_json, to_networkx
from ad_attack_path_predictor.enumerate_paths import enumerate_candidate_paths, resolve_start_nodes, resolve_target_nodes
from features.centrality import compute_betweenness_centrality, compute_degree_centrality
from features.path_features import compute_path_feature_vector
from ad_attack_path_predictor.features import node_choke_scores, path_identifier
from ad_attack_path_predictor.pipeline import rank_candidate_paths

def build_graph_data(graph_json_path, cutoff=6, max_paths=400, label_threshold=0.65, allow_edge_simulation=False, start=None):
    """Loads a BloodHound JSON, enumerates paths, computes centrality,
    and returns PyTorch tensors representing the full graph and paths.
    """
    graph = load_bloodhound_json(graph_json_path)
    
    # Resolve starting nodes
    starts = resolve_start_nodes(graph, start)
    targets = resolve_target_nodes(graph)
    
    # Check outbound edges for each start node (excluding MemberOf)
    outbound_counts = {s: 0 for s in starts}
    for edge in graph.edges:
        if edge.source in outbound_counts and edge.type != "MemberOf":
            outbound_counts[edge.source] += 1
            
    valid_starts = []
    for s in starts:
        if outbound_counts[s] == 0:
            s_node = next((n for n in graph.nodes if n.id == s), None)
            if allow_edge_simulation:
                # Find if backup is also in the graph
                backup_node = next((n for n in graph.nodes if "backup" in n.name.lower()), None)
                if backup_node:
                    from ad_attack_path_predictor.schemas import AttackEdge
                    graph.edges.append(AttackEdge(
                        source=s,
                        target=backup_node.id,
                        type="GenericAll",
                        properties={"RightName": "GenericAll", "IsInherited": False}
                    ))
                    s_node.owned = True
                    valid_starts.append(s)
        else:
            valid_starts.append(s)
            
    nx_graph = to_networkx(graph)
    candidates = enumerate_candidate_paths(
        graph, nx_graph, valid_starts, targets, cutoff=cutoff, max_paths=max_paths
    )
    
    # 1. Precompute centralities
    betweenness = compute_betweenness_centrality(nx_graph)
    degrees = compute_degree_centrality(nx_graph)
    choke_scores = node_choke_scores(candidates)
    
    # 2. Build Node ID mapping and Node Features matrix X
    # Features per node:
    # 0: kind is User (0/1)
    # 1: kind is Computer (0/1)
    # 2: kind is Group (0/1)
    # 3: owned (0/1)
    # 4: high_value (0/1)
    # 5: degree centrality
    # 6: betweenness centrality
    node_list = list(graph.nodes)
    node_id_to_idx = {node.id: idx for idx, node in enumerate(node_list)}
    
    X_list = []
    for node in node_list:
        kind_user = 1.0 if node.kind.value == "User" else 0.0
        kind_comp = 1.0 if node.kind.value == "Computer" else 0.0
        kind_group = 1.0 if node.kind.value == "Group" else 0.0
        owned = 1.0 if node.owned else 0.0
        high_val = 1.0 if node.high_value else 0.0
        deg = degrees.get(node.id, 0.0)
        bet = betweenness.get(node.id, 0.0)
        
        X_list.append([kind_user, kind_comp, kind_group, owned, high_val, deg, bet])
        
    X = torch.tensor(X_list, dtype=torch.float32)
    
    # 3. Build Adjacency edge_index (2, E)
    # We will map directed edges
    src_indices = []
    tgt_indices = []
    edge_attrs = []
    
    # Map edge types to an index
    edge_types_map = {
        "MemberOf": 0, "AdminTo": 1, "HasSession": 2, "GenericAll": 3,
        "GenericWrite": 4, "WriteDacl": 5, "WriteOwner": 6, "Owns": 7, "CanRDP": 8, "DCSync": 9
    }
    
    for edge in graph.edges:
        if edge.source in node_id_to_idx and edge.target in node_id_to_idx:
            src_indices.append(node_id_to_idx[edge.source])
            tgt_indices.append(node_id_to_idx[edge.target])
            # 1-hot vector for edge type
            vec = [0.0] * 10
            etype_idx = edge_types_map.get(edge.type, 0)
            vec[etype_idx] = 1.0
            edge_attrs.append(vec)
            
    edge_index = torch.tensor([src_indices, tgt_indices], dtype=torch.long)
    edge_attr = torch.tensor(edge_attrs, dtype=torch.float32)
    
    # 4. Generate Path mappings and labels
    # We compute labels using transparent score
    ranking = rank_candidate_paths(graph, candidates, starts, targets, top_n=len(candidates))
    score_lookup = {rp.path_id: rp.score for rp in ranking.paths}
    
    import sys
    small_graph = len(candidates) < 50
    if small_graph:
        sys.stderr.write(f"Small graph detected ({len(candidates)} paths) — using rank-based labeling. Precision metrics reflect relative ranking quality, not absolute exploitability.\n")
        sorted_candidates = sorted(candidates, key=lambda c: score_lookup.get(path_identifier(c[0], c[1]), 0.0), reverse=True)
        num_positives = max(1, int(len(candidates) * 0.3))
        positive_pids = {path_identifier(c[0], c[1]) for c in sorted_candidates[:num_positives]}

    path_nodes_list = []
    path_labels_list = []
    path_scores_list = []
    path_ids_list = []
    
    for nodes, edges in candidates:
        pid = path_identifier(nodes, edges)
        node_indices = [node_id_to_idx[n.id] for n in nodes]
        
        score = score_lookup.get(pid, 0.0)
        if small_graph:
            label = 1 if pid in positive_pids else 0
        else:
            label = 1 if score >= label_threshold else 0
        
        path_nodes_list.append(node_indices)
        path_labels_list.append(label)
        path_scores_list.append(score)
        path_ids_list.append(pid)
        
    return {
        "X": X,
        "edge_index": edge_index,
        "edge_attr": edge_attr,
        "path_nodes": path_nodes_list,
        "labels": torch.tensor(path_labels_list, dtype=torch.float32),
        "scores": torch.tensor(path_scores_list, dtype=torch.float32),
        "path_ids": path_ids_list,
        "candidates": candidates,
        "graph": graph
    }
