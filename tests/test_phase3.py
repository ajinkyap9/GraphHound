from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from model.gnn.graph_builder import build_graph_data
from model.gnn.model_def import AttackPathGNN
from ad_attack_path_predictor.api.main import app

SAMPLE = ROOT / "data" / "sample_bloodhound.json"

class TestGNNPipeline:
    def test_build_graph_data_tensor_shapes(self):
        # Test on small sample graph first
        data = build_graph_data(SAMPLE)
        
        assert "X" in data
        assert "edge_index" in data
        assert "edge_attr" in data
        assert "path_nodes" in data
        assert "labels" in data
        
        # X: shape (N, 7)
        assert data["X"].dim() == 2
        assert data["X"].size(1) == 7
        
        # edge_index: shape (2, E)
        assert data["edge_index"].dim() == 2
        assert data["edge_index"].size(0) == 2
        
        # edge_attr: shape (E, 10)
        assert data["edge_attr"].dim() == 2
        assert data["edge_attr"].size(1) == 10
        
        assert len(data["path_nodes"]) == len(data["labels"])

    def test_gnn_model_forward_pass(self):
        import torch
        data = build_graph_data(SAMPLE)
        
        X = data["X"]
        edge_index = data["edge_index"]
        path_nodes = data["path_nodes"]
        
        # Instantiate GNN
        model = AttackPathGNN(node_feature_dim=7, hidden_dim=32)
        model.eval()
        
        with torch.no_grad():
            logits = model(X, edge_index, path_nodes)
            probs = torch.sigmoid(logits)
            
        assert logits.dim() == 1
        assert logits.size(0) == len(path_nodes)
        assert probs.dim() == 1
        assert probs.size(0) == len(path_nodes)
        assert torch.all(probs >= 0.0) and torch.all(probs <= 1.0)


class TestAPIEndpointsPhase3:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_api_health_check(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}

    def test_api_ranked_paths_deterministic(self, client):
        res = client.get("/api/ranked-paths?top=5&model=Deterministic")
        assert res.status_code == 200
        data = res.json()
        assert "paths" in data
        assert len(data["paths"]) <= 5
        assert "summary" in data

    def test_api_ranked_paths_lightgbm(self, client):
        res = client.get("/api/ranked-paths?top=5&model=LightGBM")
        assert res.status_code == 200
        data = res.json()
        assert "paths" in data
        # Even if LightGBM fails to load, it should fallback to Deterministic gracefully
        assert len(data["paths"]) > 0

    def test_api_ranked_paths_gnn(self, client):
        res = client.get("/api/ranked-paths?top=5&model=GNN")
        assert res.status_code == 200
        data = res.json()
        assert "paths" in data
        # Even if GNN fails to load, it should fallback to Deterministic gracefully
        assert len(data["paths"]) > 0

    def test_api_upload_file(self, client):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            f.write('{"nodes": [], "edges": []}')
            temp_name = f.name
            
        try:
            with open(temp_name, "rb") as file_data:
                res = client.post("/api/upload", files={"file": ("test_bh.json", file_data, "application/json")})
                
            assert res.status_code == 200
            assert res.json()["status"] == "uploaded"
            
            # Reset back to default graph to avoid polluting state
            reset_res = client.post("/api/reset")
            assert reset_res.status_code == 200
            assert reset_res.json() == {"status": "reset"}
        finally:
            Path(temp_name).unlink()
