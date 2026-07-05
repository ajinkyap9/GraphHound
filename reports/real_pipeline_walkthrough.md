# Phase 2 Pipeline Walkthrough: Real BloodHound Data Analysis (Top 15% Selectivity Labeling)

We successfully updated the path labeling logic for Lab 2 to enforce selectivity in a denser graph, retrained both the LightGBM (fallback) and Graph Neural Network (GNN) models, and evaluated their performance on Lab 2.

Below is a detailed walkthrough of the new labeling parameters, model evaluation metrics, diagnostic analysis, and remediation simulation results.

---

## 1. Updated Selective Labeling Heuristic
To solve the degenerate all-positive class distribution in Lab 2 caused by its high edge density (3x denser than Lab 1), we introduced a **selectivity condition** for Lab 2.

### Lab 1 (`corp_local_export.zip`)
* **Labeling Rule:** Positive ONLY if all 4 original conditions are met (High-impact edge, Length $\le 4$, Node in top 20% centrality, and Technique prevalence $> 0.70$).
* **Distribution:** **52 Positives (8.75%) / 542 Negatives (91.25%)**

### Lab 2 (`corp_local_export_lab2.zip`)
* **Labeling Rule:** Positive ONLY if the path ranks in the **top 15% of all paths by combined risk score** (defined as `edge_composition_sum + mean_centrality`), **AND** satisfies **at least 3 of the 4 original conditions**.
* **Distribution:** **36 Positives (15.13%) / 202 Negatives (84.87%)**
  *(Note: This successfully achieves the target of ~30-40 positive paths in Lab 2).*

---

## 2. Model Evaluation (Lab 2 Generalization)
Both models were trained on Lab 1's labeled dataset and evaluated against Lab 2's new selective labels.

### Evaluation Metrics (Lab 2 Only)
| Model | Precision @ 5 | Precision @ 10 | Recall @ 20% (Cutoff = 47 paths) |
| :--- | :--- | :--- | :--- |
| **LightGBM (HistGB)** | 0.00% | 0.00% | 0.00% |
| **Graph Neural Network (GCN)** | 0.00% | 0.00% | 19.44% (7/36 paths) |

---

## 3. Diagnostic Analysis of Model Performance

### Why did LightGBM score 0.00% across all metrics?
* **Zero Variance in Predictions:** In Lab 2, the LightGBM model predicted the exact same probability of **`0.9999643`** for every single one of the 238 candidate paths (standard deviation of predictions was `0.0`).
* **Feature Distribution Shifts:** Because Lab 1's dataset only had variation in the `technique_prevalence_score` feature (with other conditions being satisfied by all candidate paths), LightGBM learned to rely entirely on this feature to separate classes.
* **Constant High Value in Lab 2:** In Lab 2's denser graph, every candidate path only contains edges mapping to technique `T1098` (prevalence `0.72`). Because `technique_prevalence_score` is constant at `0.72` across all Lab 2 paths, they all went down the exact same branch of the LightGBM decision trees and ended up in the same leaf node. 
* **Tie-Breaking Order:** Because all scores were tied at `0.9999643`, sorting placed them in generation order. The 36 true positives (which are 4-hop paths with high centrality) ended up at the bottom of the ties, resulting in 0.00% precision.

### Why did GNN perform better (19.44% Recall @ 20%)?
* **Structural Awareness:** Unlike tabular LightGBM, the GNN performs Graph Convolution over the graph structure and averages node features along paths.
* **Prediction Variance:** GNN was able to output varied predictions (scores ranging from `0.00005` to `0.99985`), capturing structural variations in centralities and node features that tabular features missed.
* **Recall Performance:** While the top 5 and 10 slots did not capture the top 15% combined risk score paths (resulting in 0.00% Precision @ 5/10), the GNN ranked **7 of the 36 true positives** inside the top 20% cutoff of 47 paths, achieving a Recall @ 20% of **19.44%**.

---

## 4. Re-run Remediation Simulation (Lab 2)
The remediation simulation was re-run targeting the top-ranked path predicted by the LightGBM model:
`JSMITH@CORP.LOCAL -> MemberOf -> NA-1904PUCHI-DISTLIST1@CORP.LOCAL -> GenericAll -> EVERETT_MELENDEZ@CORP.LOCAL -> MemberOf -> ADMINISTRATORS@CORP.LOCAL -> AllExtendedRights -> ADMINISTRATOR@CORP.LOCAL`

### Top Recommended Permission Fix:
* **Recommendation:** Remove `GenericAll` delegation and replace it with narrowly scoped permissions.
* **Relationship:** `NA-1904PUCHI-DISTLIST1@CORP.LOCAL` -> `EVERETT_MELENDEZ@CORP.LOCAL`

### Simulation Results:
* **Original Attack Paths:** 238
* **Attack Paths After Simulated Fix:** 114
* **Collapsed Attack Paths:** 124
* **Remediation Impact:** **`52.10%`**

**Conclusion:** Removing this single high-impact control relationship collapses **52.10%** of all attack paths, showing that this choke point remains the single most critical target for remediation in Lab 2.
