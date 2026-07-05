from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare Neo4j bulk-load JSONL files from normalized graph JSON.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    graph = json.loads(Path(args.input).read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "nodes.jsonl").write_text(
        "\n".join(json.dumps(node) for node in graph["nodes"]) + "\n",
        encoding="utf-8",
    )
    (out_dir / "edges.jsonl").write_text(
        "\n".join(json.dumps(edge) for edge in graph["edges"]) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

