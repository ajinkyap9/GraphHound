# Methodology

The baseline ranker is deterministic and transparent. It intentionally favors explainability before model complexity.

Risk score inputs:

- Maximum impact of any edge in the path.
- Mean public prevalence proxy for the techniques involved.
- Mean noisiness penalty.
- Ratio of quiet relationships.
- Choke-point score based on how often intermediate nodes appear in candidate paths.
- Path length penalty.

Evaluation targets:

- Precision@5 and Precision@10 against injected lab ground truth.
- Lift over shortest-path ranking.
- Lift over the baseline gradient-boosted model.
- Remediation impact after removing the top recommended edge.

