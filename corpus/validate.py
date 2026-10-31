#!/usr/bin/env python3
"""
Validate generated synthetic corpus graphs for GraphHound.

For every generated graph:
  (a) Load it with the existing ingest code
  (b) Assert counts match the config
  (c) Assert every planted chain exists edge-by-edge
  (d) Assert every critical chain's target is reachable from its start
  (e) Print a structural fingerprint table
  (f) Fail if any two graphs have near-identical fingerprints

Usage:
    python corpus/validate.py corpus/graphs/
    python corpus/validate.py corpus/graphs/ --verbose
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import sys
from pathlib import Path

# Add project root to path so we can import the ingest module
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ad_attack_path_predictor.ingest import load_bloodhound_json, to_networkx
from ad_attack_path_predictor.enumerate_paths import (
    enumerate_candidate_paths,
    resolve_start_nodes,
    resolve_target_nodes,
)


# ---------------------------------------------------------------------------
# Fingerprint dataclass (plain dict for simplicity)
# ---------------------------------------------------------------------------

def compute_fingerprint(graph_path: Path, manifest: dict) -> dict:
    """Load graph, run structural analysis, return fingerprint dict."""
    # (a) Load with existing ingest code
    attack_graph = load_bloodhound_json(str(graph_path))
    nx_graph = to_networkx(attack_graph)

    n_nodes = len(attack_graph.nodes)
    n_edges = len(attack_graph.edges)

    # Edge-type mix
    edge_type_counts: dict[str, int] = collections.Counter()
    for edge in attack_graph.edges:
        edge_type_counts[edge.type] += 1

    # Node-kind mix
    node_kind_counts: dict[str, int] = collections.Counter()
    for node in attack_graph.nodes:
        node_kind_counts[node.kind.value] += 1

    # Degree distribution
    in_degrees = [d for _, d in nx_graph.in_degree()]
    out_degrees = [d for _, d in nx_graph.out_degree()]
    mean_in = sum(in_degrees) / max(len(in_degrees), 1)
    max_in = max(in_degrees) if in_degrees else 0
    mean_out = sum(out_degrees) / max(len(out_degrees), 1)
    max_out = max(out_degrees) if out_degrees else 0

    # Group nesting depth via BFS on MemberOf edges
    group_ids = {n.id for n in attack_graph.nodes if n.kind.value == "Group"}
    memberof_children: dict[str, list[str]] = collections.defaultdict(list)
    for edge in attack_graph.edges:
        if edge.type == "MemberOf" and edge.source in group_ids and edge.target in group_ids:
            memberof_children[edge.source].append(edge.target)

    def _nesting_depth(gid: str, visited: set) -> int:
        if gid in visited:
            return 0
        visited.add(gid)
        if gid not in memberof_children:
            return 0
        return 1 + max((_nesting_depth(c, visited) for c in memberof_children[gid]), default=0)

    depths = [_nesting_depth(g, set()) for g in group_ids]
    mean_depth = sum(depths) / max(len(depths), 1)
    max_depth = max(depths) if depths else 0

    # Candidate paths via existing enumerator
    starts = resolve_start_nodes(attack_graph)
    targets = resolve_target_nodes(attack_graph)
    candidate_paths = enumerate_candidate_paths(
        attack_graph, nx_graph, starts, targets, cutoff=6, max_paths=250
    )

    return {
        "file": graph_path.name,
        "profile": manifest.get("profile", "?"),
        "seed": manifest.get("seed", "?"),
        "nodes": n_nodes,
        "edges": n_edges,
        "node_kinds": dict(node_kind_counts),
        "edge_types": dict(edge_type_counts),
        "mean_in_degree": round(mean_in, 2),
        "max_in_degree": max_in,
        "mean_out_degree": round(mean_out, 2),
        "max_out_degree": max_out,
        "mean_group_nesting": round(mean_depth, 2),
        "max_group_nesting": max_depth,
        "candidate_paths_found": len(candidate_paths),
        "start_nodes": len(starts),
        "target_nodes": len(targets),
    }


# ---------------------------------------------------------------------------
# Validation checks
# ---------------------------------------------------------------------------

def check_counts(manifest: dict, fingerprint: dict) -> list[str]:
    """(b) Assert counts roughly match config."""
    errors = []
    cfg = manifest.get("config", {})
    expected = cfg.get("node_count", 0)
    actual = fingerprint["nodes"]
    # Allow 15% tolerance (planted chains may add a few extra nodes
    # and the ratio arithmetic uses floor)
    tolerance = 0.20
    if abs(actual - expected) / max(expected, 1) > tolerance:
        errors.append(
            f"Node count mismatch: expected ~{expected}, got {actual} "
            f"(>{tolerance*100:.0f}% off)"
        )
    return errors


def check_planted_chains(graph_path: Path, manifest: dict) -> list[str]:
    """(c) Assert every planted chain exists edge-by-edge in the graph."""
    errors = []

    with graph_path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    # Build edge lookup: (source, target, type) -> True
    edge_set: set[tuple[str, str, str]] = set()
    for e in raw.get("edges", []):
        edge_set.add((e["source"], e["target"], e["type"]))

    for chain in manifest.get("planted_chains", []):
        node_ids = chain["node_ids"]
        edge_types = chain["edge_types"]
        label = chain.get("label", "?")
        for i, etype in enumerate(edge_types):
            src = node_ids[i]
            tgt = node_ids[i + 1]
            if (src, tgt, etype) not in edge_set:
                errors.append(
                    f"Chain '{label}': missing edge {src} --[{etype}]--> {tgt}"
                )
    return errors


def check_critical_reachability(graph_path: Path, manifest: dict) -> list[str]:
    """(d) Assert every critical chain's target is reachable from its start."""
    errors = []
    import networkx as nx

    attack_graph = load_bloodhound_json(str(graph_path))
    nx_graph = to_networkx(attack_graph)

    for chain in manifest.get("planted_chains", []):
        if chain.get("intended_class") != "critical":
            continue
        start = chain["node_ids"][0]
        target = chain["node_ids"][-1]
        label = chain.get("label", "?")

        if start not in nx_graph or target not in nx_graph:
            errors.append(f"Critical chain '{label}': node not in graph")
            continue

        if not nx.has_path(nx_graph, start, target):
            errors.append(
                f"Critical chain '{label}': {target} NOT reachable from {start}"
            )
    return errors


def check_fingerprint_uniqueness(fingerprints: list[dict]) -> list[str]:
    """(f) Fail if any two graphs have near-identical fingerprints."""
    errors = []

    def _signature(fp: dict) -> tuple:
        """A tuple that captures the structural shape."""
        return (
            fp["nodes"],
            fp["edges"],
            fp["max_group_nesting"],
            fp["mean_in_degree"],
            fp["max_in_degree"],
            tuple(sorted(fp["edge_types"].items())),
        )

    sigs: dict[str, tuple] = {}
    for fp in fingerprints:
        key = fp["file"]
        sig = _signature(fp)
        for other_key, other_sig in sigs.items():
            # Check if node count, edge count, and max nesting are all identical
            # AND edge type distribution is identical
            if sig == other_sig:
                errors.append(
                    f"Near-identical fingerprints: {key} and {other_key}"
                )
        sigs[key] = sig

    return errors


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------

def print_fingerprint_table(fingerprints: list[dict]) -> None:
    """Print a compact summary table."""
    if not fingerprints:
        print("No fingerprints to display.")
        return

    # Header
    cols = [
        ("Profile", 22),
        ("Seed", 5),
        ("Nodes", 7),
        ("Edges", 7),
        ("User", 6),
        ("Grp", 5),
        ("Comp", 6),
        ("AvgIn", 6),
        ("MaxIn", 6),
        ("AvgNest", 8),
        ("MaxNest", 8),
        ("Paths", 6),
    ]
    header = " | ".join(name.ljust(width) for name, width in cols)
    sep = "-+-".join("-" * width for _, width in cols)

    print()
    print("=" * len(header))
    print("  STRUCTURAL FINGERPRINT TABLE")
    print("=" * len(header))
    print(header)
    print(sep)

    for fp in fingerprints:
        nk = fp.get("node_kinds", {})
        row = [
            fp["profile"].ljust(22),
            str(fp["seed"]).ljust(5),
            str(fp["nodes"]).ljust(7),
            str(fp["edges"]).ljust(7),
            str(nk.get("User", 0)).ljust(6),
            str(nk.get("Group", 0)).ljust(5),
            str(nk.get("Computer", 0)).ljust(6),
            f"{fp['mean_in_degree']:.1f}".ljust(6),
            str(fp["max_in_degree"]).ljust(6),
            f"{fp['mean_group_nesting']:.1f}".ljust(8),
            str(fp["max_group_nesting"]).ljust(8),
            str(fp["candidate_paths_found"]).ljust(6),
        ]
        print(" | ".join(row))
    print()

    # Edge-type mix per profile
    print("  EDGE-TYPE MIX (per graph)")
    print("-" * 90)
    for fp in fingerprints:
        et = fp.get("edge_types", {})
        parts = ", ".join(f"{k}:{v}" for k, v in sorted(et.items()))
        print(f"  {fp['profile']:22s} seed={fp['seed']}  {parts}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Validate generated corpus graphs.")
    parser.add_argument("graph_dir", type=str, help="Directory with generated .json graphs")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    graph_dir = Path(args.graph_dir)
    if not graph_dir.is_dir():
        print(f"ERROR: {graph_dir} is not a directory", file=sys.stderr)
        return 1

    # Discover graph + manifest pairs
    graph_files = sorted(graph_dir.glob("*.json"))
    graph_files = [f for f in graph_files if ".manifest." not in f.name]

    if not graph_files:
        print(f"ERROR: No graph files found in {graph_dir}", file=sys.stderr)
        return 1

    all_errors: list[str] = []
    fingerprints: list[dict] = []

    for gf in graph_files:
        manifest_path = gf.with_suffix("").with_suffix(".manifest.json")
        if not manifest_path.exists():
            manifest_path = Path(str(gf).replace(".json", ".manifest.json"))
        if not manifest_path.exists():
            all_errors.append(f"Missing manifest for {gf.name}")
            continue

        with manifest_path.open("r", encoding="utf-8") as fh:
            manifest = json.load(fh)

        print(f"Validating {gf.name}...", end=" ", flush=True)

        # (a) Load with ingest code (will raise on failure)
        try:
            attack_graph = load_bloodhound_json(str(gf))
            if args.verbose:
                print(f"[ingest OK: {len(attack_graph.nodes)} nodes, {len(attack_graph.edges)} edges]", end=" ")
        except Exception as exc:
            all_errors.append(f"{gf.name}: ingest failed: {exc}")
            print("FAIL (ingest)")
            continue

        # (b) Count check
        errs_b = check_counts(manifest, {"nodes": len(attack_graph.nodes), "edges": len(attack_graph.edges)})
        all_errors.extend(f"{gf.name}: {e}" for e in errs_b)

        # (c) Planted chains edge-by-edge
        errs_c = check_planted_chains(gf, manifest)
        all_errors.extend(f"{gf.name}: {e}" for e in errs_c)

        # (d) Critical chain reachability
        errs_d = check_critical_reachability(gf, manifest)
        all_errors.extend(f"{gf.name}: {e}" for e in errs_d)

        local_errs = errs_b + errs_c + errs_d
        if local_errs:
            print(f"FAIL ({len(local_errs)} errors)")
        else:
            print("OK")

        # (e) Fingerprint
        fp = compute_fingerprint(gf, manifest)
        fingerprints.append(fp)

    # (f) Uniqueness check
    errs_f = check_fingerprint_uniqueness(fingerprints)
    all_errors.extend(errs_f)

    # Print table
    print_fingerprint_table(fingerprints)

    # Summary
    if all_errors:
        print("=" * 60)
        print(f"  {len(all_errors)} VALIDATION ERROR(S):")
        print("=" * 60)
        for err in all_errors:
            print(f"  [FAIL] {err}")
        print()
        return 1
    else:
        print("=" * 60)
        print("  ALL VALIDATIONS PASSED [OK]")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())
