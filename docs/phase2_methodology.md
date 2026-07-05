# Phase 2 Methodology — Feature Engineering, Labeling & Baseline Ranking Model

## Overview

Phase 2 transforms the raw graph-in-Neo4j (or in-memory NetworkX) into a
**ranked, scored list of attack paths**.  It delivers three capabilities that
Phase 1 lacked:

1. **Multiple candidate paths** per starting node (bounded depth enumeration).
2. **Numeric feature vectors** describing how risky each path is.
3. **A trained LightGBM model** that scores and ranks paths.

## Feature Engineering

### Feature Set

Every path is described by **14 numeric features**:

| Feature                    | Source                        | Rationale                                              |
| -------------------------- | ----------------------------- | ------------------------------------------------------ |
| `hop_count`                | Path length                   | Shorter paths are easier to exploit                    |
| `unique_edge_types`        | Edge set                      | More diverse techniques suggest a skilled attacker      |
| `edge_composition_sum`     | `attck_mapping.json`          | Cumulative risk weight along the path                  |
| `edge_composition_mean`    | `attck_mapping.json`          | Average risk per hop                                   |
| `mean_prevalence`          | `attck_mapping.json`          | How common the techniques are in real incidents        |
| `mean_noisiness`           | `attck_mapping.json`          | How detectable the techniques are                      |
| `max_impact`               | `attck_mapping.json`          | Worst-case impact of any single edge                   |
| `technique_prevalence_score` | `prevalence_weights.json`   | Real-world frequency of ATT&CK techniques involved    |
| `max_centrality`           | NetworkX betweenness           | Maximum centrality of any node in the path             |
| `mean_centrality`          | NetworkX betweenness           | Average centrality across all path nodes               |
| `choke_point_score`        | Cross-path analysis            | How many other paths pass through this path's nodes    |
| `high_value_steps`         | Node attributes                | Count of high-value/privileged nodes traversed         |
| `quiet_edge_ratio`         | `attck_mapping.json`          | Fraction of edges that are hard to detect              |
| `detectability_flag`       | Edge type classification       | 1 if path contains any inherently "loud" technique     |

### Centrality Computation

Betweenness centrality is computed using NetworkX on the full graph.  This is
equivalent to Neo4j GDS centrality but does not require a running Neo4j
instance.  A node with high betweenness centrality is a key transit point
that many attack paths pass through — fixing it collapses many paths at once.

### Edge Risk Weighting

Each edge type is assigned a risk weight = `impact × prevalence` from the
ATT&CK mapping.  The path's **edge composition score** is the sum and average
of these weights.

## Labeling Strategy

### Transparent Score Labeling

Paths are labeled using the Phase 1 deterministic ranker's transparent score
as a proxy:

- **Positive (label=1):** score ≥ 0.65 (configurable threshold)
- **Negative (label=0):** score < 0.65

This creates a supervised dataset without manual annotation.  The threshold
is calibrated so that the 3 known seeded chains in the sample data all
receive positive labels.

### Seeded Ground Truth

Three realistic attack chains are documented in `labeling/seed_paths.md`.
The evaluation checks whether ALL seeded paths appear in the top 20% of
the model's ranked output.

## Model Selection

### LightGBM Baseline

LightGBM was chosen because:

1. **Fast training** on small datasets (30–500 paths).
2. **Feature importance** is immediately interpretable.
3. **Gradient boosting** handles the feature interactions (e.g., short path +
   high impact = more dangerous than either alone).
4. **Direct comparison target** for the Phase 3 GNN model.

If LightGBM is not installed, the training script falls back to sklearn's
`HistGradientBoostingClassifier` (similar algorithm, fewer tuning options).

### Hyperparameters

- `n_estimators=100`, `max_depth=4`, `learning_rate=0.1`
- Train/test split: 65/35 with stratification
- Random seed: 7 for reproducibility

## Evaluation Criteria

1. **Sanity check (pass/fail):** Do ALL seeded ground-truth paths appear in
   the top 20% of ranked output?
2. **Path count check:** Does enumeration return tens-to-hundreds of distinct
   paths per starting node?
3. **Feature completeness:** Does every path have a non-null value for every
   feature column?
4. **Metrics:** Average precision, precision, recall, recall@20%.

## What Comes Next

Once the baseline ranks seeded paths correctly, Phase 3 builds:

1. GNN model trained on the same feature set (compared against this baseline).
2. FastAPI + dashboard to visualize ranked output.
3. Second independent lab for the generalization test.
