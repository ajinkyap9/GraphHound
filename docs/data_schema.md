# Data Schema

## Node

- `id`: stable unique identifier.
- `name`: human-readable object name.
- `kind`: `User`, `Group`, `Computer`, `Domain`, `OU`, `GPO`, or `Unknown`.
- `owned`: whether this is a known starting principal.
- `high_value`: whether this is a privileged target.
- `properties`: source-specific metadata.

## Edge

- `source`: source node id.
- `target`: target node id.
- `type`: BloodHound relationship type.
- `properties`: source-specific metadata.

## Ranking Output

Each ranked path contains a calibrated score, confidence, feature vector, ATT&CK technique IDs, explanations, and remediation suggestions.

