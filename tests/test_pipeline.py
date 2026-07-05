from pathlib import Path

from ad_attack_path_predictor.ingest import load_bloodhound_json
from ad_attack_path_predictor.pipeline import rank_from_file


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample_bloodhound.json"


def test_load_sample_graph():
    graph = load_bloodhound_json(SAMPLE)
    assert len(graph.nodes) == 11
    assert len(graph.edges) == 14
    assert any(node.owned for node in graph.nodes)
    assert any(node.high_value for node in graph.nodes)


def test_ranked_paths_are_sorted():
    response = rank_from_file(SAMPLE, top_n=5)
    scores = [path.score for path in response.paths]
    assert response.summary.candidate_paths >= 1
    assert scores == sorted(scores, reverse=True)
    assert response.paths[0].remediation

