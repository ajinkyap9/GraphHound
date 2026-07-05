from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import rank_from_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rank BloodHound-style AD attack paths.")
    sub = parser.add_subparsers(dest="command", required=True)
    rank = sub.add_parser("rank", help="Rank candidate attack paths")
    rank.add_argument("--input", required=True, help="BloodHound-style JSON file")
    rank.add_argument("--start", help="Start node id or name. Defaults to owned principals.")
    rank.add_argument("--target", help="Target node id or name. Defaults to high-value nodes.")
    rank.add_argument("--top", type=int, default=10, help="Number of ranked paths to return")
    rank.add_argument("--cutoff", type=int, default=6, help="Maximum path length")
    rank.add_argument("--output", help="Optional JSON report path")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "rank":
        response = rank_from_file(args.input, start=args.start, target=args.target, top_n=args.top, cutoff=args.cutoff)
        payload = response.model_dump(mode="json")
        rendered = json.dumps(payload, indent=2)
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered)


if __name__ == "__main__":
    main()

