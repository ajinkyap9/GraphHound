# Architecture

The system has five layers:

1. Collection: SharpHound or a lab generator produces BloodHound-style JSON.
2. Ingestion: `ad_attack_path_predictor.ingest` normalizes nodes and edges.
3. Enumeration: NetworkX enumerates bounded simple paths from owned users to high-value targets.
4. Ranking: feature extraction maps edges to ATT&CK-informed risk profiles and scores each path.
5. Delivery: FastAPI exposes graph and ranking endpoints; React/Cytoscape.js visualizes prioritized paths.

Neo4j assets are included for teams that want to replace local NetworkX enumeration with database-backed path queries.

