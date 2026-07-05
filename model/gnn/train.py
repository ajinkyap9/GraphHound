import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT))

import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.model_selection import train_test_split

from model.gnn.graph_builder import build_graph_data
from model.gnn.model_def import AttackPathGNN

def train_gnn(dataset_path, model_output_path, epochs=150, lr=0.005, weight_decay=1e-4):
    print(f"Loading and processing graph data from {dataset_path}...")
    data = build_graph_data(dataset_path)
    
    X = data["X"]
    edge_index = data["edge_index"]
    path_nodes = data["path_nodes"]
    labels = data["labels"]
    
    num_paths = len(path_nodes)
    print(f"Loaded graph with {X.size(0)} nodes and {edge_index.size(1)} edges.")
    print(f"Total enumerated paths: {num_paths}")
    print(f"  Positives (label=1): {int(labels.sum().item())}")
    print(f"  Negatives (label=0): {num_paths - int(labels.sum().item())}")

    if num_paths < 6:
        print("Error: Too few paths for training.")
        return

    # Split path indices into train and test sets
    path_indices = list(range(num_paths))
    train_idx, val_idx = train_test_split(
        path_indices, test_size=0.3, random_state=42, stratify=labels.numpy()
    )
    
    train_labels = labels[train_idx]
    val_labels = labels[val_idx]
    
    # Initialize GNN model
    # X has 7 node features: [kind_user, kind_comp, kind_group, owned, high_val, deg, bet]
    model = AttackPathGNN(node_feature_dim=7, hidden_dim=64)
    criterion = nn.BCEWithLogitsLoss()
    optimizer = optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    
    best_val_loss = float("inf")
    
    for epoch in range(1, epochs + 1):
        model.train()
        optimizer.zero_grad()
        
        # Forward pass on all paths
        logits = model(X, edge_index, path_nodes)
        
        # Calculate loss on training indices only
        train_logits = logits[train_idx]
        loss = criterion(train_logits, train_labels)
        
        loss.backward()
        optimizer.step()
        
        # Validation
        model.eval()
        with torch.no_grad():
            val_logits = logits[val_idx]
            val_loss = criterion(val_logits, val_labels)
            
            # Compute train & val accuracy
            train_preds = (torch.sigmoid(train_logits) >= 0.5).float()
            val_preds = (torch.sigmoid(val_logits) >= 0.5).float()
            
            train_acc = (train_preds == train_labels).float().mean().item()
            val_acc = (val_preds == val_labels).float().mean().item()
            
        if epoch % 10 == 0 or epoch == 1:
            print(f"Epoch {epoch:3d} | Train Loss: {loss.item():.4f} | Val Loss: {val_loss.item():.4f} | Train Acc: {train_acc:.2%} | Val Acc: {val_acc:.2%}")
            
        if val_loss.item() < best_val_loss:
            best_val_loss = val_loss.item()
            # Save best checkpoint
            torch.save({
                "model_state_dict": model.state_dict(),
                "node_feature_dim": 7,
                "hidden_dim": 64,
                "train_metrics": {"loss": loss.item(), "acc": train_acc},
                "val_metrics": {"loss": val_loss.item(), "acc": val_acc}
            }, model_output_path)

    print(f"\nGNN training complete. Best model checkpoint saved to: {model_output_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Train GNN model on simulated GOAD dataset.")
    parser.add_argument(
        "--dataset",
        default="data/goad_export/goad_bloodhound.json",
        help="Path to simulated BloodHound JSON data."
    )
    parser.add_argument(
        "--output",
        default="model/gnn/gnn_model.pt",
        help="Path to save trained GNN checkpoint."
    )
    parser.add_argument("--epochs", type=int, default=150, help="Number of epochs to train.")
    args = parser.parse_args()
    
    # Create directory if needed
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    
    train_gnn(args.dataset, args.output, epochs=args.epochs)
