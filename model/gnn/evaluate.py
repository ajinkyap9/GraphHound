import sys
import json
import joblib
import pandas as pd
import numpy as np
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT))

import torch
from model.gnn.graph_builder import build_graph_data
from model.gnn.model_def import AttackPathGNN

def evaluate_models():
    # 1. Paths configuration
    model_path = Path("model/gnn/gnn_model.pt")
    lgb_model_path = Path("model/baseline_lightgbm/baseline.joblib")
    
    lab1_json = Path("data/goad_export/goad_bloodhound.json")
    lab2_json = Path("data/goad_export_lab2/goad_bloodhound_lab2.json")
    
    if not model_path.exists():
        print(f"Error: GNN model checkpoint not found at {model_path}. Please run train.py first.")
        return
        
    # 2. Load GNN Model
    checkpoint = torch.load(model_path)
    gnn_model = AttackPathGNN(
        node_feature_dim=checkpoint["node_feature_dim"],
        hidden_dim=checkpoint["hidden_dim"]
    )
    gnn_model.load_state_dict(checkpoint["model_state_dict"])
    gnn_model.eval()
    
    # 3. Load LightGBM Model if available
    lgb_model = None
    if lgb_model_path.exists():
        lgb_bundle = joblib.load(lgb_model_path)
        lgb_model = lgb_bundle["model"]
        lgb_features = lgb_bundle["feature_columns"]
        print("Loaded LightGBM baseline model.")
    else:
        print("LightGBM baseline model not found.")

    print("\n" + "=" * 60)
    print("EVALUATING ON LAB 1 (IN-DISTRIBUTION)")
    print("=" * 60)
    lab1_results = evaluate_dataset(
        lab1_json, gnn_model, lgb_model, lgb_features if lgb_model else None, "lab1"
    )

    print("\n" + "=" * 60)
    print("EVALUATING ON LAB 2 (OUT-OF-DISTRIBUTION / GENERALIZATION TEST)")
    print("=" * 60)
    lab2_results = evaluate_dataset(
        lab2_json, gnn_model, lgb_model, lgb_features if lgb_model else None, "lab2"
    )

    # 4. Comparative Metrics Summary
    print("\n" + "=" * 60)
    print("COMPARATIVE METRICS TABLE")
    print("=" * 60)
    
    comparison = {
        "Metric": [
            "Total Paths",
            "Positive Paths",
            "GNN Precision@5",
            "GNN Precision@10",
            "GNN Recall@20%",
            "LGB Precision@5",
            "LGB Precision@10",
            "LGB Recall@20%"
        ],
        "Lab 1 (Train Env)": [
            lab1_results["total_paths"],
            lab1_results["positives"],
            f"{lab1_results['gnn_p5']:.2%}",
            f"{lab1_results['gnn_p10']:.2%}",
            f"{lab1_results['gnn_recall20']:.2%}",
            f"{lab1_results['lgb_p5']:.2%}" if lgb_model else "N/A",
            f"{lab1_results['lgb_p10']:.2%}" if lgb_model else "N/A",
            f"{lab1_results['lgb_recall20']:.2%}" if lgb_model else "N/A"
        ],
        "Lab 2 (Generalization Env)": [
            lab2_results["total_paths"],
            lab2_results["positives"],
            f"{lab2_results['gnn_p5']:.2%}",
            f"{lab2_results['gnn_p10']:.2%}",
            f"{lab2_results['gnn_recall20']:.2%}",
            f"{lab2_results['lgb_p5']:.2%}" if lgb_model else "N/A",
            f"{lab2_results['lgb_p10']:.2%}" if lgb_model else "N/A",
            f"{lab2_results['lgb_recall20']:.2%}" if lgb_model else "N/A"
        ]
    }
    
    df_comp = pd.DataFrame(comparison)
    print(df_comp.to_string(index=False))

    # Save comparative metrics summary
    summary_path = Path("model/experiments/metrics_summary.json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)

def evaluate_dataset(json_path, gnn_model, lgb_model, lgb_features, dataset_name):
    data = build_graph_data(json_path)
    X = data["X"]
    edge_index = data["edge_index"]
    path_nodes = data["path_nodes"]
    labels = data["labels"].numpy()
    path_ids = data["path_ids"]
    candidates = data["candidates"]
    graph = data["graph"]

    total_paths = len(path_nodes)
    positives = int(labels.sum())

    # Get GNN predictions
    with torch.no_grad():
        logits = gnn_model(X, edge_index, path_nodes)
        gnn_probs = torch.sigmoid(logits).numpy()

    # Ranks paths by GNN score
    df = pd.DataFrame({
        "path_id": path_ids,
        "label": labels,
        "gnn_score": gnn_probs
    })
    
    # Get LightGBM predictions
    if lgb_model and lgb_features:
        # Load features through features pipeline
        from features.path_features import compute_path_feature_vector
        from ad_attack_path_predictor.features import node_choke_scores
        from features.centrality import compute_betweenness_centrality
        from ad_attack_path_predictor.ingest import to_networkx
        nx_graph = to_networkx(graph)
        centrality_map = compute_betweenness_centrality(nx_graph)
        choke_scores = node_choke_scores(candidates)
        node_data = {node.id: node.model_dump() for node in graph.nodes}
        
        lgb_rows = []
        for nodes, edges in candidates:
            node_ids = [n.id for n in nodes]
            edge_types = [e.type for e in edges]
            feats = compute_path_feature_vector(
                node_ids, edge_types, node_data=node_data,
                centrality_map=centrality_map, choke_scores=choke_scores
            )
            lgb_rows.append(feats)
            
        df_feats = pd.DataFrame(lgb_rows)
        # Select matching columns
        X_lgb = df_feats[lgb_features].values.astype(np.float64)
        lgb_probs = lgb_model.predict_proba(X_lgb)[:, 1]
        df["lgb_score"] = lgb_probs

    # GNN Metrics
    df_gnn = df.sort_values("gnn_score", ascending=False).reset_index(drop=True)
    df_gnn["gnn_rank"] = df_gnn.index + 1
    
    p5_gnn = df_gnn.head(5)["label"].mean()
    p10_gnn = df_gnn.head(10)["label"].mean()
    
    top_20_cutoff = max(1, int(total_paths * 0.20))
    positives_in_top_20_gnn = df_gnn.head(top_20_cutoff)["label"].sum()
    recall20_gnn = positives_in_top_20_gnn / positives if positives > 0 else 0.0

    # LGB Metrics
    p5_lgb, p10_lgb, recall20_lgb = 0.0, 0.0, 0.0
    if lgb_model:
        df_lgb = df.sort_values("lgb_score", ascending=False).reset_index(drop=True)
        df_lgb["lgb_rank"] = df_lgb.index + 1
        
        p5_lgb = df_lgb.head(5)["label"].mean()
        p10_lgb = df_lgb.head(10)["label"].mean()
        
        positives_in_top_20_lgb = df_lgb.head(top_20_cutoff)["label"].sum()
        recall20_lgb = positives_in_top_20_lgb / positives if positives > 0 else 0.0

    # Print results
    print(f"Total paths:            {total_paths}")
    print(f"Ground-truth positives: {positives}")
    print(f"Top 20% cutoff:         {top_20_cutoff}")
    print(f"\nGNN Model:")
    print(f"  Precision@5:          {p5_gnn:.2%}")
    print(f"  Precision@10:         {p10_gnn:.2%}")
    print(f"  Recall@20%:           {recall20_gnn:.2%}")
    
    if lgb_model:
        print(f"\nLightGBM Model:")
        print(f"  Precision@5:          {p5_lgb:.2%}")
        print(f"  Precision@10:         {p10_lgb:.2%}")
        print(f"  Recall@20%:           {recall20_lgb:.2%}")

    # Write GNN ranked output file
    out_dir = Path("model/gnn")
    out_dir.mkdir(parents=True, exist_ok=True)
    df_gnn.to_csv(out_dir / f"ranked_output_gnn_{dataset_name}.csv", index=False)
    print(f"\nRanked GNN output written to: {out_dir / f'ranked_output_gnn_{dataset_name}.csv'}")
    
    return {
        "total_paths": total_paths,
        "positives": positives,
        "gnn_p5": p5_gnn,
        "gnn_p10": p10_gnn,
        "gnn_recall20": recall20_gnn,
        "lgb_p5": p5_lgb,
        "lgb_p10": p10_lgb,
        "lgb_recall20": recall20_lgb
    }

if __name__ == "__main__":
    evaluate_models()
