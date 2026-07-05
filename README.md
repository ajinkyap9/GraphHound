<div align="center">

<img src="https://img.shields.io/badge/Status-Research%20Tool-blueviolet?style=for-the-badge" alt="Status"/>
<img src="https://img.shields.io/badge/Lab-Windows%20Server%202019-0078D4?style=for-the-badge&logo=windows&logoColor=white" alt="Lab"/>
<img src="https://img.shields.io/badge/Ethics-Lab%20Only-critical?style=for-the-badge" alt="Ethics"/>

# 🛡️ GraphHound
### *AD Attack Path Predictor*

**Defensive prioritization for BloodHound-style Active Directory escalation paths — powered by GNN**

*BloodHound shows you everything. GraphHound tells you what to fix first — and how much risk each fix eliminates.*

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![PyTorch Geometric](https://img.shields.io/badge/PyTorch%20Geometric-GNN-EE4C2C?logo=pytorch&logoColor=white)](https://pyg.org)
[![LightGBM](https://img.shields.io/badge/LightGBM-Baseline-02569B?logo=microsoft&logoColor=white)](https://lightgbm.readthedocs.io)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-Dashboard-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![MLflow](https://img.shields.io/badge/MLflow-Experiment%20Tracking-0194E2?logo=mlflow&logoColor=white)](https://mlflow.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## 🔍 What Is This?

GraphHound ingests **BloodHound JSON exports** from Active Directory environments and produces a **ranked, risk-scored shortlist of attack paths** — telling defenders which paths to fix first and quantifying exactly how much attack surface each fix eliminates.

> **The problem with BloodHound alone:** it shows you *all* paths. With hundreds of escalation routes in a real enterprise, knowing which 5 to fix this week is the actual challenge. GraphHound solves that.

**What makes it different from GoodHound / PlumHound:**

| Capability | BloodHound CE | GoodHound | PlumHound | **GraphHound** |
|---|:---:|:---:|:---:|:---:|
| Path enumeration | ✅ | ✅ | ✅ | ✅ |
| Ranking by edge count | — | ✅ | ✅ | ✅ |
| Exploitation likelihood scoring | — | — | — | ✅ |
| ATT&CK technique mapping | — | — | — | ✅ |
| Graph Neural Network ranking | — | — | — | ✅ |
| **Remediation impact simulation** | — | — | — | **✅** |
| "Fix this, collapse X% of surface" | — | — | — | **✅** |

---

## 📸 Screenshots

### Dashboard Overview — 3,405 Nodes · 72,810 Edges · 123 Candidate Paths

![Dashboard Overview](docs/assets/dashboard-overview.png)

*The full GraphHound dashboard: upload a BloodHound JSON, get ranked attack paths visualized in an interactive graph with remediation recommendations on the right.*

---

### Path Ranking — Risk Score Explanation

![Path Ranking and Why It Ranked](docs/assets/path-ranking.png)

*Every ranked path includes a transparent explanation: high-impact control edges, detection noise level, and choke-point significance.*

---

### Remediation Panel — Actionable Fixes

![Remediation Panel](docs/assets/remediation-panel.png)

*Per-path, specific permission changes — not generic advice. Exact relationships to remove with source and target principals named.*

---

### Remediation Impact — 52.10% Risk Reduction from a Single Fix

![Remediation Impact](docs/assets/remediation-impact.png)

*One recommended fix collapsed 124 paths — **52.10% of total attack surface** — in the generalization test on an unseen lab.*

---

## 📊 Key Results

| Metric | Result | Notes |
|---|---|---|
| **Precision@5** | **100%** | Lab 1 — 594 paths, 3,405 nodes |
| **Precision@10** | **100%** | Lab 1 |
| **GNN Recall@20%** | **19.44%** | Unseen dense graph (Lab 2) |
| **LightGBM Recall@20%** | **0%** | Same unseen graph — complete failure |
| **Remediation impact** | **52.10%** | Single fix collapsed 124 / 238 paths |
| **Graph scale** | 3,405 nodes · 72,810 edges | Production-scale BadBlood synthetic AD |

> **Key finding:** The GNN maintains 19.44% Recall@20% on an unseen dense graph where LightGBM completely fails (0%) due to technique homogeneity — empirically proving that **graph structure carries independent signal beyond tabular features**.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     BloodHound JSON Export                   │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│              Graph Ingestion & Path Enumeration              │
│   Neo4j / NetworkX · Bounded depth-6 DFS · 3,405 nodes      │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                  Feature Engineering (14 features)           │
│  ATT&CK mapping · edge impact · prevalence · noise ·         │
│  choke-point score · privilege exposure · path length        │
└────────────────┬─────────────────────────┬───────────────────┘
                 │                         │
                 ▼                         ▼
┌───────────────────────┐     ┌───────────────────────────────┐
│   LightGBM Baseline   │     │  GNN (PyTorch Geometric)      │
│   Tabular features    │     │  Graph-aware node embeddings  │
│   Fast, interpretable │     │  GAT layers · global pooling  │
└──────────┬────────────┘     └──────────────┬────────────────┘
           │                                 │
           └────────────────┬────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                    MLflow Experiment Tracking                │
│          Precision@5 · Precision@10 · Lift · Recall@20%     │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                FastAPI Backend                               │
│     POST /upload  ·  GET /rank  ·  GET /remediate           │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│          React + Cytoscape.js Dashboard                      │
│  Upload panel · Ranked graph · Path list · Remediation panel │
└──────────────────────────────────────────────────────────────┘
```

---

## ⚡ Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- Neo4j (optional — in-memory graph works without it)

### Backend

```powershell
cd ad-attack-path-predictor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Rank top paths from a BloodHound export
python -m ad_attack_path_predictor.cli rank --input data\sample_bloodhound.json --top 5

# Start the API server
uvicorn ad_attack_path_predictor.api.main:app --reload --port 8000
```

API docs available at `http://127.0.0.1:8000/docs`

### Dashboard

```powershell
cd dashboard
npm install
npm run dev
```

Dashboard at `http://127.0.0.1:5173` — upload a BloodHound JSON and see ranked results immediately.

---

## 🖥️ CLI Usage

**Rank top paths:**
```powershell
python -m ad_attack_path_predictor.cli rank \
  --input data\sample_bloodhound.json \
  --start j.doe \
  --target "DOMAIN ADMINS" \
  --top 10
```

**Export a JSON report:**
```powershell
python -m ad_attack_path_predictor.cli rank \
  --input data\sample_bloodhound.json \
  --output reports\ranked_paths.json
```

---

## 📥 Input Format

GraphHound accepts BloodHound-style JSON exports:

```json
{
  "nodes": [
    {"id": "j.doe", "name": "j.doe", "kind": "User", "owned": true},
    {"id": "domain-admins", "name": "DOMAIN ADMINS", "kind": "Group", "high_value": true}
  ],
  "edges": [
    {"source": "j.doe", "target": "helpdesk", "type": "MemberOf"},
    {"source": "helpdesk", "target": "domain-admins", "type": "GenericAll"}
  ]
}
```

Common key aliases are supported (`ObjectIdentifier`, `Name`, `Label`, `StartNode`, `EndNode`, `RelationshipType`) for compatibility with real BloodHound exports.

---

## 🧠 Scoring Philosophy

The risk scorer is intentionally **transparent and explainable**:

| Factor | Direction | Rationale |
|---|---|---|
| High-impact edges (`GenericAll`, `WriteDacl`, `DCSync`, `AddMember`) | ↑ Score | Direct privilege escalation capability |
| Public ATT&CK prevalence of techniques | ↑ Score | Attacker tooling availability |
| Detection noise / monitoring coverage | ↓ Score | Quieter paths are higher real-world risk |
| Path length | ↓ Score (penalty) | Longer paths require more attacker steps |
| Choke-point nodes (high betweenness) | ↑ Score | Fixing these collapses many candidate paths |

This gives an immediately useful baseline and a clean target for the GNN upgrade path.

---

## 📁 Project Layout

```
ad-attack-path-predictor/
├── src/ad_attack_path_predictor/   # Python engine and FastAPI backend
│   ├── api/                        # FastAPI routes (/upload, /rank, /remediate)
│   ├── core/                       # Graph ingestion, path enumeration
│   └── features/                   # 14-feature extraction pipeline
├── dashboard/                      # React + Cytoscape.js UI
│   └── src/components/             # UploadPanel, GraphView, PathList, RemediationPanel
├── model/
│   ├── gnn/                        # PyTorch Geometric GNN (GAT architecture)
│   └── baseline_lightgbm/          # LightGBM baseline
├── data/                           # Sample BloodHound-style exports
├── features/                       # ATT&CK edge-to-technique mapping
├── graph_db/                       # Neo4j schema and Cypher queries
├── lab/                            # Lab setup scripts (GOAD / BadBlood)
├── labeling/                       # Synthetic ground-truth labeler
├── model/experiments/              # MLflow run artifacts
├── tests/                          # Pytest suite
├── docs/                           # Architecture, methodology, assets
│   └── assets/                     # Screenshots used in this README
├── reports/                        # Output reports and ranked path exports
└── ETHICS.md                       # Responsible use statement
```

---

## 🔬 Methodology

**Why GNN beats flat LightGBM here:**

LightGBM sees each path as an isolated feature vector — it has no awareness that two paths share a common node (e.g., `SVC_BACKUP@CORP.LOCAL` appearing in 40 different paths). The GNN learns node embeddings from the **full graph structure**, capturing "this node is a high-centrality hub that many attack paths route through" as part of the representation itself — not as a hand-engineered feature.

This structural awareness is the genuine technical contribution that explains the GNN's maintained recall on dense graphs where LightGBM collapses.

**Remediation impact simulation:**

For each top-ranked recommendation, the tool simulates removing that edge, re-runs path enumeration, and reports how many candidate paths collapse. This is the capability missing from every comparable open-source tool.

---

## ⚠️ Limitations

- **Dense homogeneous graphs:** GNN Recall@20% drops when technique diversity is very low (all paths use the same 2–3 edge types) — LightGBM and GNN both struggle, but GNN degrades more gracefully.
- **Heuristic labeling:** Ground-truth labels are generated from injected synthetic misconfigurations (BadBlood), not from real breach outcomes. Real-world calibration requires red team validation.
- **Single-domain tested:** Generalization to multi-domain forests and Azure AD / Entra ID hybrid environments is a planned future phase.
- **Collection dependency:** Requires a BloodHound-compatible JSON export — SharpHound, BloodHound CE, or hand-crafted synthetic data.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Graph DB** | Neo4j · NetworkX |
| **ML — GNN** | PyTorch Geometric · GAT architecture |
| **ML — Baseline** | LightGBM |
| **Experiment Tracking** | MLflow |
| **Backend API** | FastAPI |
| **Frontend** | React · Vite · Cytoscape.js |
| **Lab Data** | BadBlood synthetic AD · Windows Server 2019 Evaluation |
| **ATT&CK Mapping** | MITRE ATT&CK for Enterprise (static JSON reference) |

---

## 🧪 Running Tests

```powershell
pytest tests/ -v
```

The test suite includes sample data so the project runs immediately without a lab environment.

---

## ⚖️ Ethical Use

> **Lab-only. No real organizations targeted.**

This tool was built on:
- Windows Server 2019 Evaluation (lab VM)
- [BadBlood](https://github.com/davidprowe/BadBlood) synthetic Active Directory data
- No production or real-organization data was used at any stage

**Use this tool only when:**
- You own the environment, or have explicit written authorization to analyze it
- Collection data was obtained legally and per organizational policy
- Results are used to reduce risk, improve detection, or support defensive research

See [ETHICS.md](ETHICS.md) for the full responsible use statement.

---

## 🗺️ Roadmap

- [x] Phase 1 — Graph ingestion, path enumeration, baseline scorer
- [x] Phase 2 — Feature engineering, LightGBM baseline, synthetic labeling
- [x] Phase 3 — GNN (PyTorch Geometric), production API, React dashboard, generalization test
- [ ] Phase 4 — Multi-domain / multi-forest support
- [ ] Phase 4 — Azure AD / Entra ID hybrid graph support
- [ ] Phase 4 — Continuous re-collection scheduling
- [ ] Phase 4 — Multi-tenant dashboard for MSSP use case

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built for defenders, by a defender.**

*If you find this useful, star the repo — it helps others discover it.*

</div>
