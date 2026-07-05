from __future__ import annotations

import argparse

from ad_attack_path_predictor.ingest import dump_graph, load_bloodhound_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize a BloodHound-style JSON export.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    dump_graph(load_bloodhound_json(args.input), args.output)


if __name__ == "__main__":
    main()

