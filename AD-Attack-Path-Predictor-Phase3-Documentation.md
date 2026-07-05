# AD Attack Path Predictor — Phase 3 Documentation
### (GNN Model, Production API, Dashboard & Generalization Test)

## 1. Status Recap — What's Already Implemented

- Bounded all-paths enumeration working (depth 6, capped per node).
- ATT&CK mapping and prevalence weights hardcoded in JSON (static reference).
- 14-feature extraction pipeline fully working.
- Synthetic labeling and `labeled_dataset.csv` generated.
- LightGBM baseline trained and evaluated — 50% accuracy on 10-path mock dataset (expected — data starvation, not a model failure).
- FastAPI server scaffolded (`api/main.py`) but not production-complete.
- React/Vite + Cytoscape.js dashboard scaffolded but not connected end-to-end.
- GNN model stub exists in `model/gnn/` but not implemented.

The 50% baseline accuracy is not a problem to fix with a better model — it's a data problem. Phase 3 solves it the right way: by generating a real, large-scale dataset from a properly configured vulnerable AD lab (GOAD), training the GNN on it, and validating against a second independent lab environment.

## 2. Problem Being Solved in This Phase

Three things are broken or incomplete right now:

- **The model has no real data to learn from.** 10 paths is not a training set — it's a smoke test. Everything downstream of this is invalid until you run against a real AD environment with hundreds of paths.
- **The API and dashboard are scaffolded but non-functional end-to-end.** A real user cannot currently open a browser, upload a BloodHound export, and see ranked results.
- **No generalization evidence.** The tool currently only proves it works on the exact data it was built on — not on a new environment it has never seen, which is the only proof that matters for a real deployment claim.

Phase 3 fixes all three.

## 3. Scope of This Phase

- Deploy GOAD (Game of Active Directory) as the real vulnerable AD lab to generate production-scale path data.
- Collect real SharpHound data from GOAD, retrain LightGBM baseline on it, establish a real accuracy benchmark.
- Implement the GNN model using PyTorch Geometric and compare it against the LightGBM baseline with real numbers.
- Integrate MLflow for experiment tracking across both models.
- Complete the FastAPI backend (file upload endpoint, ranked results endpoint, remediation endpoint).
- Complete the React + Cytoscape.js dashboard (upload flow, ranked graph visualization, remediation panel).
- Run the generalization test on a second, independently configured GOAD instance.

## 4. Architecture for This Phase

```
 ┌──────────────────────────┐     ┌────────────────────────────┐
 │  GOAD Lab Environment     │     │  Second GOAD Lab            │
 │  (real vulnerable AD)     │     │  (independent config,       │
 │  SharpHound collection    │     │  generalization test only)  │
 └──────────────────────────┘     └────────────────────────────┘
             │                                  │
             ▼                                  ▼
 ┌──────────────────────────────────────────────────────────┐
 │  Phase 2 Pipeline (enumeration → features → labels)       │
 │  now running on real data (hundreds of paths, not 10)     │
 └──────────────────────────────────────────────────────────┘
             │
             ▼
 ┌────────────────────────────────────┐
 │  MLflow Experiment Tracking         │
 │  logs params, metrics, artifacts    │
 │  for every model run               │
 └────────────────────────────────────┘
             │
      ┌──────┴───────┐
      ▼              ▼
 ┌──────────┐  ┌─────────────────────────┐
 │ LightGBM  │  │  GNN (PyTorch Geometric) │
 │ Baseline  │  │  trains on graph         │
 │ (retrained│  │  structure directly,     │
 │ on real   │  │  not just flat features  │
 │ data)     │  └─────────────────────────┘
 └──────────┘
      │              │
      └──────┬───────┘
             ▼
 ┌────────────────────────────┐
 │  FastAPI Backend (complete) │
 │  /upload  /rank  /remediate │
 └────────────────────────────┘
             │
             ▼
 ┌────────────────────────────────────────┐
 │  React + Cytoscape.js Dashboard         │
 │  upload → ranked graph → fix panel     │
 └────────────────────────────────────────┘
```

## 5. Folder Additions for This Phase

```
ad-attack-path-predictor/
├── lab/
│   ├── goad/                              # UPDATED: GOAD deployment config
│   │   ├── install.md                     # NEW: GOAD setup instructions
│   │   └── goad_config.yml                # NEW: lab topology config
│   └── scripts/
│       ├── collect_sharphound.ps1          # NEW: automates SharpHound collection from GOAD
│       └── reset_goad.sh                  # NEW: tears down and rebuilds GOAD cleanly
├── data/
│   ├── goad_export/                       # NEW: real SharpHound ZIPs from GOAD lab
│   └── goad_export_lab2/                  # NEW: second lab export for generalization
├── model/
│   ├── gnn/
│   │   ├── model_def.py                   # IMPLEMENTED: PyTorch Geometric GNN architecture
│   │   ├── graph_builder.py               # NEW: converts path feature table to PyG graph
│   │   ├── train.py                       # IMPLEMENTED: full training loop
│   │   └── evaluate.py                    # IMPLEMENTED: Precision@5, Precision@10, lift
│   ├── baseline_lightgbm/
│   │   └── train.py                       # UPDATED: retrained on real GOAD data
│   └── experiments/                       # NEW: MLflow run artifacts stored here
├── api/
│   ├── main.py                            # COMPLETED: all routes wired up
│   └── routers/
│       ├── paths.py                       # COMPLETED: /rank endpoint
│       ├── upload.py                      # NEW: /upload BloodHound ZIP endpoint
│       └── remediation.py                 # NEW: /remediate endpoint
├── dashboard/
│   └── src/
│       ├── components/
│       │   ├── UploadPanel.jsx            # NEW: drag-and-drop BloodHound ZIP upload
│       │   ├── GraphView.jsx              # NEW: Cytoscape.js ranked attack path graph
│       │   ├── PathList.jsx               # NEW: ranked path list with scores
│       │   └── RemediationPanel.jsx       # NEW: per-path fix recommendations
│       └── App.jsx                        # UPDATED: wires all components together
└── docs/
    └── phase3_methodology.md              # NEW: GNN architecture + generalization writeup
```

## 6. Step-by-Step Implementation Plan

### Step 1 — Deploy GOAD and collect real data
GOAD (Game of Active Directory) is an open-source project specifically designed to provision a realistic, intentionally vulnerable multi-domain AD lab using Vagrant and VirtualBox. It creates a realistic forest with multiple domains, trust relationships, service accounts, and common misconfigurations — far closer to a real enterprise environment than the minimal single-domain lab from Phase 1.

Deploy GOAD following the official instructions. Once running, execute SharpHound against all domains, collect the ZIP exports, and run the Phase 2 pipeline against this data. Target: at minimum 200–300 enumerated paths. If GOAD produces fewer, relax the hop depth limit to 8 temporarily.

This is the most critical step of Phase 3. Do not move to Step 2 until you have a real labeled dataset of 100+ paths with a reasonable positive/negative balance (aim for roughly 30–40% positive labels).

### Step 2 — Retrain LightGBM baseline on real data
Run `model/baseline_lightgbm/train.py` on the GOAD-generated `labeled_dataset.csv`. This is your new real accuracy benchmark — the 50% mock-data number is now obsolete. Expected outcome: 80–90%+ accuracy, with all seeded GOAD ground-truth paths ranking in the top 20%. If accuracy is below 75%, the problem is feature quality, not model quality — debug features before touching the model.

Wrap this run in MLflow: log the training dataset size, feature importances, Precision@5, Precision@10, and the top-20% sanity check result. This creates a permanent, reproducible record of your baseline.

### Step 3 — Implement the GNN model
The GNN is the architectural leap that separates this project from a flat feature-table scorer. Here's what to implement:

**Graph construction (`graph_builder.py`):**
Convert your path feature table into a PyTorch Geometric `Data` object. Each node in the graph is a principal (user/computer/group) with node features (degree centrality, betweenness centrality, whether it's a service account, whether it has AdminTo rights on anything). Each edge carries the ATT&CK risk weight and detectability score as edge attributes.

**Model architecture (`model_def.py`):**
Use a two-layer Graph Convolutional Network (GCN) or Graph Attention Network (GAT) — GAT is preferable because attention weights let the model learn which neighbor relationships matter most for each node, which maps directly to the "which edges in this path are actually dangerous" intuition. Output is a per-path risk score after global pooling over the nodes in each candidate path.

**Why GNN beats flat LightGBM here:**
LightGBM sees each path as an isolated vector and has no awareness that two paths share a common node (e.g., SvcAccount_Backup appearing in 40 different paths). The GNN learns node embeddings from the full graph structure, so it captures "SvcAccount_Backup is a high-centrality hub that many attack paths route through" as part of the representation itself, not as a hand-engineered centrality feature. This structural awareness is the genuine technical contribution of the GNN over the baseline.

Log this run in MLflow alongside the LightGBM run for direct metric comparison.

### Step 4 — Evaluate and compare both models
Compute for both models on the GOAD dataset:
- **Precision@5** — of the top 5 ranked paths, how many are genuinely high-risk?
- **Precision@10** — same for top 10.
- **Lift over shortest-path baseline** — how much better does each model rank compared to simply sorting by hop count?
- **Remediation impact** — simulate removing the top recommended fix, re-run enumeration, measure how many total paths collapse.

The comparison table between LightGBM and GNN (with real numbers, not mock-data numbers) is the centerpiece of your methodology writeup and your LinkedIn post. Even if the GNN's lift over LightGBM is modest (5–10% Precision@5 improvement), document it honestly — a real measured improvement with an explanation of why is far more credible than an overclaimed result.

### Step 5 — Complete the FastAPI backend
Three endpoints are needed for the dashboard to work end-to-end:

- `POST /upload` — accepts a BloodHound ZIP file, runs the Phase 2 pipeline (parse → ingest → enumerate → extract features), returns a session ID.
- `GET /rank/{session_id}?top_n=10` — runs the trained model against the session's paths, returns ranked results as JSON (path nodes/edges + risk score + ATT&CK techniques involved).
- `GET /remediate/{session_id}/{path_id}` — returns the specific remediation recommendation for a ranked path (e.g., "Remove GenericAll from SvcAccount_X on OU=Finance").

Add input validation (reject files that aren't valid BloodHound JSON schema) and basic error handling (what happens if enumeration returns zero paths — tell the user why, don't silently fail).

### Step 6 — Complete the React dashboard
Four components wire together into the user flow:

- **UploadPanel** — drag-and-drop BloodHound ZIP upload, calls `/upload`, shows a loading state while the pipeline runs.
- **PathList** — shows top-N ranked paths as a sortable list with risk scores and ATT&CK technique tags.
- **GraphView** — Cytoscape.js renders the selected path as an interactive node graph. Nodes are colored by type (user/computer/group) and edges are colored by risk weight (red = high, yellow = medium). Clicking a node shows its properties.
- **RemediationPanel** — for the selected path, shows the specific permission to remove and the estimated number of other paths that collapse if you do.

Keep the UI functional over decorative — a clean, usable tool that does one thing well is a stronger signal than an overdesigned dashboard that doesn't work reliably.

### Step 7 — Generalization test (second independent lab)
Provision a second GOAD instance with a different topology configuration (different domain names, different seeded misconfigurations, at minimum change the group memberships and service account assignments). Run the full pipeline — enumeration, feature extraction, ranking — using the model trained only on Lab 1 data. Do not retrain. Check whether the seeded paths in Lab 2 still rank in the top 20%.

If they do: the model generalizes — this is your strongest result and should be the headline of your writeup. If they don't: the model is overfitting to Lab 1's specific topology, which is itself a finding worth documenting honestly — it sets up a natural "future work" direction (e.g., domain-adaptive training, more diverse training labs).

## 7. Evaluation Criteria for This Phase

- Precision@5 and Precision@10 on GOAD data (target: 80%+ for both models).
- GNN vs LightGBM lift: measured, honest, documented in MLflow.
- Remediation impact number: at least one concrete "fixing X collapsed Y% of paths" result.
- Dashboard works end-to-end: upload a real BloodHound ZIP, see ranked results in the browser, no manual steps in between.
- Generalization test pass/fail documented with honest explanation of the result.

## 8. What Makes This Phase LinkedIn-Ready

After Phase 3 you will have: real accuracy numbers (not mock), a live demo-able dashboard, a GNN vs baseline comparison, and a generalization result. That combination — a working tool with measured results, demonstrated on real-scale data, tested for generalization, and honestly documented — is the artifact that makes senior security people stop scrolling. Specifically lead the post with the remediation-impact number and the generalization result, not the model architecture — practitioners care about what it does, researchers care about how.

## 9. What Comes After This Phase

Phase 4 (scaling, optional): multi-domain/multi-forest support, Azure AD / Entra ID identity graph support alongside on-prem AD, continuous re-collection scheduling, multi-tenant dashboard for MSSP use case.
