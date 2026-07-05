from __future__ import annotations

import torch
import torch.nn as nn

class SimpleGraphConv(nn.Module):
    """A pure PyTorch implementation of a normalized Graph Convolutional network layer.
    
    Avoids binary dependencies like torch-scatter or torch-sparse on Windows.
    """
    def __init__(self, in_features: int, out_features: int):
        super().__init__()
        self.linear = nn.Linear(in_features, out_features, bias=False)
        self.bias = nn.Parameter(torch.zeros(out_features))

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        num_nodes = x.size(0)
        h = self.linear(x)
        
        # Add self-loops
        device = x.device
        loop_index = torch.stack([torch.arange(num_nodes, device=device)] * 2, dim=0)
        edge_index = torch.cat([edge_index, loop_index], dim=1)
        
        # Compute degrees
        row, col = edge_index
        deg = torch.zeros(num_nodes, device=device)
        deg.scatter_add_(0, row, torch.ones_like(row, dtype=torch.float32))
        deg_inv_sqrt = deg.pow(-0.5)
        deg_inv_sqrt[torch.isinf(deg_inv_sqrt)] = 0
        
        # Normalize edge messages
        norm = deg_inv_sqrt[row] * deg_inv_sqrt[col]
        
        # Propagate messages using scatter_add
        out = torch.zeros((num_nodes, h.size(1)), device=device)
        msg = h[row] * norm.unsqueeze(-1)
        out.scatter_add_(0, col.unsqueeze(-1).expand_as(msg), msg)
        
        return out + self.bias

class AttackPathGNN(nn.Module):
    """Path-pooling Graph Neural Network.
    
    Performs GCN message passing over nodes, then aggregates node features
    along paths to output path-level risk predictions.
    """
    def __init__(self, node_feature_dim: int, hidden_dim: int = 64):
        super().__init__()
        self.conv1 = SimpleGraphConv(node_feature_dim, hidden_dim)
        self.conv2 = SimpleGraphConv(hidden_dim, hidden_dim)
        self.classifier = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim // 2, 1),
        )

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor, path_nodes: list[list[int]]) -> torch.Tensor:
        # Node convolution
        h = self.conv1(x, edge_index).relu()
        h = self.conv2(h, edge_index).relu()
        
        # Aggregate path features via mean pooling along path nodes
        path_embs = []
        for path in path_nodes:
            path_idx = torch.tensor(path, dtype=torch.long, device=x.device)
            path_emb = h[path_idx].mean(dim=0)
            path_embs.append(path_emb)
            
        path_embs = torch.stack(path_embs, dim=0)
        
        # Classify paths
        logits = self.classifier(path_embs).squeeze(-1)
        return logits
