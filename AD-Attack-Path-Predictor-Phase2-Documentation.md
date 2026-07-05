# AD Attack Path Predictor — Phase 2 Documentation
### (Feature Engineering, Labeling & Baseline Ranking Model)

## 1. Status Recap — What's Already Implemented

- Lab AD environment provisioned and operational.
- SharpHound collection working against the lab domain.
- BloodHound JSON parsed and loaded into Neo4j.
- Path enumeration query running (currently `shortestPath()` only — single path per starting node).

This phase fixes the enumeration gap and builds everything needed to go from "a graph in Neo4j" to "a ranked, scored list of attack paths."

## 2. Problem Being Solved in This Phase

Right now the tool can show *a* path, not *the most dangerous* path among many. Phase 2 builds the three things required to rank: (1) multiple candidate paths per target, (2) numeric features describing how risky each one is, and (3) a trained model that scores them. Without this phase, there is nothing to prioritize — this is the core differentiator from plain BloodHound, so it's the most important phase in the whole project.

## 3. Scope of This Phase

- Fix path enumeration to return all paths (bounded depth), not just shortest.
- Build the ATT&CK technique mapping and risk-weighting reference data.
- Build the feature extraction pipeline (per-path feature vectors).
- Seed and label a small ground-truth dataset in the lab.
- Train and evaluate a LightGBM baseline ranking model.

GNN modeling, the dashboard, and the second-lab generalization test are explicitly **out of scope** for this phase — they depend on this phase succeeding first.

## 4. Architecture for This Phase

```
 ┌────────────────────┐
 │   Neo4j Graph DB     │   (already populated)
 └────────────────────┘
            │
            ▼
 ┌────────────────────────────┐
 │  Path Enumeration (fixed)   │   all paths, bounded depth, capped per node
 └────────────────────────────┘
            │
            ▼
 ┌────────────────────────────┐      ┌───────────────────────────┐
 │  Feature Extraction         │ ◀──▶ │  ATT&CK Mapping Reference   │
 │  (edge weights, hop count,  │      │  (attck_mapping.json,      │
 │  centrality, prevalence)    │      │  prevalence_weights.json)  │
 └────────────────────────────┘      └───────────────────────────┘
            │
            ▼
 ┌────────────────────────────┐
 │  Synthetic Labeling          │   seeded "known exploitable" chains
 │  (labeled path dataset)      │   + prevalence-based heuristics
 └────────────────────────────┘
            │
            ▼
 ┌────────────────────────────┐
 │  LightGBM Baseline Model     │   trains on features → label
 │  (train.py / evaluate.py)    │
 └────────────────────────────┘
            │
            ▼
 ┌────────────────────────────┐
 │  Ranked Path Output (CSV/   │   sanity-check: do seeded paths
 │  JSON) — manual review       │   rank near the top?
 └────────────────────────────┘
```

## 5. Folder Additions for This Phase

```
ad-attack-path-predictor/
├── graph_db/
│   └── queries/
│       └── path_enumeration.cypher        # UPDATED: all-paths, bounded depth
├── features/
│   ├── edge_features.py                   # NEW: edge-type risk weighting
│   ├── path_features.py                   # NEW: hop count, centrality, prevalence
│   ├── centrality.py                      # NEW: wraps Neo4j GDS centrality calls
│   └── attck_mapping.json                 # NEW: edge type → ATT&CK technique ID
│   └── prevalence_weights.json            # NEW: technique → real-world frequency score
├── labeling/
│   ├── seed_paths.md                      # NEW: documents the deliberately seeded chains
│   ├── synthetic_labeler.py               # NEW: assigns labels to extracted paths
│   └── labeled_dataset.csv                # NEW: output — path features + label
├── model/
│   └── baseline_lightgbm/
│       ├── train.py                       # NEW
│       ├── evaluate.py                    # NEW
│       └── ranked_output_sample.csv        # NEW: manual sanity-check artifact
└── docs/
    └── phase2_methodology.md              # NEW: write-up of this phase's approach
```

## 6. Step-by-Step Implementation Plan

### Step 1 — Fix path enumeration
Replace the `shortestPath()` query with an all-paths query bounded by hop depth and result count:

```cypher
MATCH p = (n)-[*1..6]->(m:Group {name:"DOMAIN ADMINS@YOURDOMAIN"})
WHERE n.owned = true
RETURN p
LIMIT 500
```

Validate: confirm dozens-to-hundreds of distinct paths return per starting node instead of one. If the query is too slow or returns too many results, tighten the hop range before adding a `LIMIT`, not after — pruning depth first keeps results meaningful rather than arbitrarily truncated.

### Step 2 — Build the ATT&CK mapping
Create `attck_mapping.json`: one entry per BloodHound edge type your graph contains (`GenericAll`, `WriteDacl`, `DCSync`, `AddMember`, `AdminTo`, `HasSession`, `MemberOf`, etc.) mapped to its MITRE ATT&CK technique ID. Pair this with `prevalence_weights.json`, a numeric score per technique pulled from a public source (MITRE ATT&CK technique usage data, a published annual threat detection report). This is a static reference table — get it right once, since every downstream feature depends on it.

### Step 3 — Feature extraction
For every path from Step 1, compute:
- **Edge composition score** — sum/average of edge-type risk weights along the path.
- **Hop count** — raw path length, used as one input, not the ranking driver.
- **Technique prevalence score** — average prevalence weight of the ATT&CK techniques involved.
- **Centrality** — for each node in the path, pull betweenness or degree centrality using Neo4j's Graph Data Science (GDS) library rather than computing it manually; a node many other paths also pass through scores higher.
- **Detectability proxy** — flag whether the path contains any inherently "loud" technique (e.g., DCSync) versus only quiet ones (e.g., group membership).

Output one row per path into a flat feature table — this is the input your model trains on.

### Step 4 — Seed and label ground truth
Before labeling, go back into the lab and deliberately configure 2–3 realistic vulnerable chains (document them in `seed_paths.md` so you know exactly what "should" rank highly). Label paths as positive if they match a seeded chain or closely match high-prevalence technique patterns; label as negative if they're long, rare-technique, low-centrality paths. Aim for 30–50 labeled examples to start — this is enough for a meaningful first baseline, not thousands.

### Step 5 — Train the LightGBM baseline
Train on the Step 3 feature table against the Step 4 labels. This is the key checkpoint of the entire phase.

### Step 6 — Evaluate
Check whether your seeded "known exploitable" paths rank near the top of the model's output. If yes, the feature design is validated and Phase 3 (GNN, dashboard) can proceed. If not, iterate on feature weights (e.g., separate detectability from prevalence) before adding model complexity — don't jump to a more complex model to fix a feature engineering problem.

## 7. Evaluation Criteria for This Phase

- **Sanity check pass/fail:** do all seeded ground-truth paths appear in the top 20% of ranked output?
- **Path count check:** does enumeration now return a realistic distribution (tens to hundreds) of paths per starting node, rather than one?
- **Feature completeness:** does every path have a non-null value for each feature (no silent gaps from missing ATT&CK mappings)?

## 8. What Comes After This Phase

Once the baseline ranks the seeded paths correctly, move to: GNN model trained on the same feature set (compared directly against this LightGBM baseline), FastAPI + dashboard to visualize ranked output, and the second independent lab for the generalization test — in that order, as outlined in the original documentation's Section 9.
