#!/usr/bin/env python3
"""
Deterministic synthetic AD graph generator for GraphHound.

Usage:
    python corpus/generate.py --profile small_clean --seed 1 --out corpus/graphs/
    python corpus/generate.py --all --seed 1 --out corpus/graphs/

Same profile + seed always produces byte-identical output.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Profile loader (pure stdlib – reads the YAML subset we actually use)
# ---------------------------------------------------------------------------

def _load_profiles(path: Path) -> dict[str, dict[str, Any]]:
    """Minimal YAML-subset parser for the profiles file.

    Handles only the flat-mapping structure we use: top-level ``profiles:``
    key followed by named entries whose values are ``key: value`` pairs
    (str, int, float).  No anchors, no flow collections, no multi-line.
    """
    profiles: dict[str, dict[str, Any]] = {}
    current: str | None = None

    with path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n\r")
            stripped = line.lstrip()

            # skip blanks / comments
            if not stripped or stripped.startswith("#"):
                continue

            # top-level key "profiles:"
            if stripped == "profiles:":
                continue

            indent = len(line) - len(stripped)
            key_val = stripped.split(":", 1)
            if len(key_val) != 2:
                continue

            key = key_val[0].strip()
            val = key_val[1].strip().strip('"').strip("'")

            if indent == 2:
                # profile name
                current = key
                profiles[current] = {}
            elif indent >= 4 and current is not None:
                # Try int, float, then str
                try:
                    profiles[current][key] = int(val)
                except ValueError:
                    try:
                        profiles[current][key] = float(val)
                    except ValueError:
                        profiles[current][key] = val
    return profiles


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACL_EDGE_TYPES = [
    "GenericAll", "GenericWrite", "WriteDacl", "WriteOwner",
    "Owns", "AddMember", "AllowedToDelegate",
]

# Weights used when randomly selecting ACL edge types
ACL_WEIGHTS = [0.20, 0.20, 0.15, 0.10, 0.10, 0.15, 0.10]

DOMAIN_SUFFIX = "@corp.test"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_id(kind: str, index: int) -> str:
    """Create a deterministic, human-readable node id."""
    return f"{kind.lower()}{index:04d}"


def _make_name(kind: str, index: int) -> str:
    if kind == "User":
        return f"user{index:04d}{DOMAIN_SUFFIX}"
    if kind == "Group":
        return f"GRP-{index:04d}"
    if kind == "Computer":
        return f"COMP{index:04d}.corp.test"
    if kind == "Domain":
        return "corp.test"
    if kind == "OU":
        return f"OU-{index:04d}"
    if kind == "GPO":
        return f"GPO-{index:04d}"
    return f"node{index:04d}"


# ---------------------------------------------------------------------------
# Core generator
# ---------------------------------------------------------------------------

class GraphGenerator:
    """Builds a synthetic AD graph from a profile config dict."""

    def __init__(self, config: dict[str, Any], seed: int):
        self.cfg = config
        self.seed = seed
        self.rng = random.Random(seed)

        self.nodes: list[dict[str, Any]] = []
        self.edges: list[dict[str, Any]] = []
        self.node_index: dict[str, dict[str, Any]] = {}

        # O(1) edge-existence index
        self._edge_set: set[tuple[str, str, str]] = set()

        # Categorised id lists filled during node creation
        self.users: list[str] = []
        self.groups: list[str] = []
        self.computers: list[str] = []
        self.domains: list[str] = []
        self.ous: list[str] = []
        self.gpos: list[str] = []

        self.tier0_ids: list[str] = []
        self.owned_ids: list[str] = []

        # planted chains for manifest
        self.planted_chains: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Node / edge helpers
    # ------------------------------------------------------------------

    def _add_node(self, nid: str, name: str, kind: str,
                  owned: bool = False, high_value: bool = False) -> dict[str, Any]:
        node = {
            "id": nid,
            "name": name,
            "kind": kind,
            "owned": owned,
            "high_value": high_value,
        }
        self.nodes.append(node)
        self.node_index[nid] = node
        return node

    def _add_edge(self, src: str, tgt: str, etype: str) -> None:
        key = (src, tgt, etype)
        if key in self._edge_set:
            return
        self._edge_set.add(key)
        self.edges.append({"source": src, "target": tgt, "type": etype})

    def _has_edge(self, src: str, tgt: str, etype: str) -> bool:
        return (src, tgt, etype) in self._edge_set

    # ------------------------------------------------------------------
    # Phase 1: Create nodes
    # ------------------------------------------------------------------

    def _create_nodes(self) -> None:
        n = self.cfg["node_count"]
        ur = self.cfg["user_ratio"]
        gr = self.cfg["group_ratio"]
        cr = self.cfg["computer_ratio"]

        n_users = max(2, int(n * ur))
        n_groups = max(2, int(n * gr))
        n_computers = max(2, int(n * cr))
        remainder = max(0, n - n_users - n_groups - n_computers - 1)  # -1 for domain
        n_ous = max(1, remainder // 2)
        n_gpos = max(1, remainder - n_ous)

        # Domain node (always exactly one)
        domain_id = "domain0000"
        self._add_node(domain_id, "corp.test", "Domain", high_value=True)
        self.domains.append(domain_id)

        for i in range(n_users):
            nid = _make_id("User", i)
            self._add_node(nid, _make_name("User", i), "User")
            self.users.append(nid)

        for i in range(n_groups):
            nid = _make_id("Group", i)
            hv = False
            name = _make_name("Group", i)
            if i == 0:
                name = f"DOMAIN ADMINS{DOMAIN_SUFFIX}"
                hv = True
            elif i == 1:
                name = f"DOMAIN CONTROLLERS{DOMAIN_SUFFIX}"
                hv = True
            self._add_node(nid, name, "Group", high_value=hv)
            self.groups.append(nid)

        for i in range(n_computers):
            nid = _make_id("Computer", i)
            hv = False
            name = _make_name("Computer", i)
            if i == 0:
                name = "DC01.corp.test"
                hv = True
            self._add_node(nid, name, "Computer", high_value=hv)
            self.computers.append(nid)

        for i in range(n_ous):
            nid = _make_id("OU", i)
            self._add_node(nid, _make_name("OU", i), "OU")
            self.ous.append(nid)

        for i in range(n_gpos):
            nid = _make_id("GPO", i)
            self._add_node(nid, _make_name("GPO", i), "GPO")
            self.gpos.append(nid)

    # ------------------------------------------------------------------
    # Phase 2: Mark tier-0 and owned
    # ------------------------------------------------------------------

    def _designate_tier0_and_owned(self) -> None:
        self.tier0_ids = [self.domains[0], self.groups[0], self.computers[0]]
        extra_t0 = max(0, self.cfg["tier0_targets"] - len(self.tier0_ids))
        pool = [g for g in self.groups[2:] if g not in self.tier0_ids]
        for gid in self.rng.sample(pool, min(extra_t0, len(pool))):
            self.node_index[gid]["high_value"] = True
            self.tier0_ids.append(gid)

        owned_n = self.cfg["owned_start_nodes"]
        owned_pool = [u for u in self.users if u not in self.tier0_ids]
        for uid in self.rng.sample(owned_pool, min(owned_n, len(owned_pool))):
            self.node_index[uid]["owned"] = True
            self.owned_ids.append(uid)

    # ------------------------------------------------------------------
    # Phase 3: Group membership structure
    # ------------------------------------------------------------------

    def _build_group_memberships(self) -> None:
        depth = self.cfg["group_nesting_depth"]

        # Every user joins 1-3 groups randomly
        joinable = self.groups[:]
        for uid in self.users:
            n_memberships = self.rng.randint(1, min(3, len(joinable)))
            targets = self.rng.sample(joinable, n_memberships)
            for gid in targets:
                self._add_edge(uid, gid, "MemberOf")

        # Group nesting: create chains up to `depth` levels
        if depth > 1 and len(self.groups) > 2:
            nestable = self.groups[2:]  # skip DA, DC groups
            self.rng.shuffle(nestable)
            layer_size = max(1, len(nestable) // depth)
            layers: list[list[str]] = []
            for i in range(depth):
                start = i * layer_size
                end = start + layer_size if i < depth - 1 else len(nestable)
                layer = nestable[start:end]
                if layer:
                    layers.append(layer)

            for li in range(len(layers) - 1):
                for gid in layers[li]:
                    target = self.rng.choice(layers[li + 1])
                    self._add_edge(gid, target, "MemberOf")

            # Some groups in deepest layer connect to DA or DC group
            if layers:
                deep = layers[-1]
                for gid in deep[:max(1, len(deep) // 3)]:
                    tier0_group = self.rng.choice(self.groups[:2])
                    self._add_edge(gid, tier0_group, "MemberOf")

    # ------------------------------------------------------------------
    # Phase 4: Sessions
    # ------------------------------------------------------------------

    def _build_sessions(self) -> None:
        density = self.cfg["session_density"]
        for cid in self.computers:
            if self.rng.random() < density and self.users:
                user = self.rng.choice(self.users)
                self._add_edge(cid, user, "HasSession")

    # ------------------------------------------------------------------
    # Phase 5: ACL edges
    # ------------------------------------------------------------------

    def _build_acl_edges(self) -> None:
        density = self.cfg["acl_edge_density"]
        misconfig_rate = self.cfg["misconfiguration_rate"]
        all_ids = [n["id"] for n in self.nodes]
        n = len(all_ids)

        # Budget: number of ACL edges to add
        expected_edges = int(n * n * density)
        budget = min(expected_edges, n * 20)

        added = 0
        max_attempts = budget * 5
        attempts = 0

        while added < budget and attempts < max_attempts:
            attempts += 1
            src = self.rng.choice(all_ids)
            tgt = self.rng.choice(all_ids)
            if src == tgt:
                continue

            etype = self.rng.choices(ACL_EDGE_TYPES, weights=ACL_WEIGHTS, k=1)[0]

            # DCSync only targets Domain nodes
            if etype == "DCSync" and self.node_index[tgt]["kind"] != "Domain":
                continue
            # AddMember only targets Groups
            if etype == "AddMember" and self.node_index[tgt]["kind"] != "Group":
                continue

            # Misconfiguration gate: well-managed edges are filtered out
            if self.rng.random() > misconfig_rate:
                if etype not in ("AdminTo", "CanRDP"):
                    continue

            if not self._has_edge(src, tgt, etype):
                self._add_edge(src, tgt, etype)
                added += 1

        # Ensure at least some AdminTo edges to computers
        for cid in self.computers[:max(1, len(self.computers) // 5)]:
            src = self.rng.choice(self.users) if self.users else self.groups[0]
            self._add_edge(src, cid, "AdminTo")

    # ------------------------------------------------------------------
    # Phase 6: Planted attack chains
    # ------------------------------------------------------------------

    def _pick_owned(self) -> str:
        if self.owned_ids:
            return self.rng.choice(self.owned_ids)
        return self.users[0]

    def _pick_tier0(self) -> str:
        return self.rng.choice(self.tier0_ids)

    def _plant_chain(self, chain_nodes: list[str], chain_edges: list[str],
                     intended_class: str, label: str) -> None:
        """Ensure every edge in the chain exists, record in manifest."""
        for i in range(len(chain_edges)):
            self._add_edge(chain_nodes[i], chain_nodes[i + 1], chain_edges[i])

        self.planted_chains.append({
            "label": label,
            "intended_class": intended_class,
            "node_ids": chain_nodes,
            "edge_types": chain_edges,
        })

    def _plant_short_critical(self) -> None:
        """Plant 2 short critical chains."""
        # Chain 1: owned -> GenericAll -> victim_user -> DCSync -> domain
        start = self._pick_owned()
        victim = self.rng.choice(
            [u for u in self.users if u != start and u not in self.tier0_ids]
        )
        domain = self.domains[0]
        self._plant_chain(
            [start, victim, domain],
            ["GenericAll", "DCSync"],
            "critical",
            "short_critical_genericall_dcsync",
        )

        # Chain 2: owned -> WriteDacl -> group -> AddMember -> DA
        start2 = self._pick_owned()
        mid_group = self.rng.choice(self.groups[2:])
        da_group = self.groups[0]
        self._plant_chain(
            [start2, mid_group, da_group],
            ["WriteDacl", "AddMember"],
            "critical",
            "short_critical_writedacl_addmember",
        )

    def _plant_long_memberof_chain(self) -> None:
        """Plant a long chain of mostly MemberOf edges reaching Tier-0."""
        start = self._pick_owned()
        depth = min(self.cfg["group_nesting_depth"], len(self.groups) - 3)
        depth = max(depth, 3)

        pool = [g for g in self.groups[2:] if g != start]
        self.rng.shuffle(pool)
        chain_groups = pool[:depth]

        tier0 = self.groups[0]  # DA
        chain_nodes = [start] + chain_groups + [tier0]
        chain_edges = ["MemberOf"] * (len(chain_groups) + 1)

        self._plant_chain(chain_nodes, chain_edges, "critical",
                          "long_memberof_chain_to_tier0")

    def _plant_noisy_exploitable(self) -> None:
        """Plant a noisy but genuinely exploitable chain."""
        start = self._pick_owned()
        comp1 = self.rng.choice(self.computers)
        user_mid = self.rng.choice([u for u in self.users if u != start])
        comp2 = self.rng.choice([c for c in self.computers if c != comp1])
        domain = self.domains[0]

        self._plant_chain(
            [start, comp1, user_mid, comp2, domain],
            ["CanRDP", "HasSession", "AdminTo", "DCSync"],
            "critical",
            "noisy_but_exploitable",
        )

    def _plant_decoy_chains(self) -> None:
        """Plant 2 long decoy chains that never reach a privileged target."""
        for idx in range(2):
            start = self._pick_owned()
            length = self.rng.randint(4, 6)
            safe_pool = [n["id"] for n in self.nodes
                         if n["id"] not in self.tier0_ids and n["id"] != start]
            self.rng.shuffle(safe_pool)
            hop_nodes = safe_pool[:length]

            chain_nodes = [start] + hop_nodes
            benign_cycle = ["MemberOf", "CanRDP", "HasSession", "MemberOf"]
            chain_edges = [benign_cycle[i % len(benign_cycle)]
                           for i in range(len(hop_nodes))]

            self._plant_chain(chain_nodes, chain_edges, "decoy",
                              f"decoy_chain_{idx}")

    def _plant_chokepoint(self) -> None:
        """Ensure at least one shared choke-point node across multiple chains."""
        candidates = [n["id"] for n in self.nodes
                      if n["id"] not in self.tier0_ids
                      and n["id"] not in self.owned_ids
                      and n["kind"] in ("User", "Group")]
        if not candidates:
            return
        choke = self.rng.choice(candidates)

        for idx in range(2):
            start = self._pick_owned()
            tier0 = self._pick_tier0()
            if start == choke or tier0 == choke:
                continue
            etype1 = self.rng.choice(["GenericAll", "GenericWrite", "Owns"])
            etype2 = self.rng.choice(["WriteDacl", "AddMember", "DCSync"])
            if etype2 == "DCSync":
                tier0 = self.domains[0]
            if etype2 == "AddMember" and self.node_index[tier0]["kind"] != "Group":
                tier0 = self.groups[0]

            self._plant_chain(
                [start, choke, tier0],
                [etype1, etype2],
                "critical" if idx == 0 else "medium",
                f"chokepoint_chain_{idx}",
            )

    def _plant_all_chains(self) -> None:
        self._plant_short_critical()
        self._plant_long_memberof_chain()
        self._plant_noisy_exploitable()
        self._plant_decoy_chains()
        self._plant_chokepoint()

    # ------------------------------------------------------------------
    # Deterministic sort for byte-identical output
    # ------------------------------------------------------------------

    def _sort_output(self) -> None:
        self.nodes.sort(key=lambda n: n["id"])
        self.edges.sort(key=lambda e: (e["source"], e["target"], e["type"]))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Return (graph_dict, planted_chains_list)."""
        self._create_nodes()
        self._designate_tier0_and_owned()
        self._build_group_memberships()
        self._build_sessions()
        self._build_acl_edges()
        self._plant_all_chains()
        self._sort_output()

        graph = {
            "nodes": self.nodes,
            "edges": self.edges,
        }
        return graph, self.planted_chains


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def write_graph(profile_name: str, seed: int, out_dir: Path,
                profiles: dict[str, dict[str, Any]]) -> Path:
    """Generate one graph and write it + manifest. Return graph path."""
    cfg = profiles[profile_name]
    gen = GraphGenerator(cfg, seed)
    graph, chains = gen.generate()

    out_dir.mkdir(parents=True, exist_ok=True)
    graph_path = out_dir / f"{profile_name}_seed{seed}.json"
    manifest_path = out_dir / f"{profile_name}_seed{seed}.manifest.json"

    with graph_path.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(graph, fh, indent=2, sort_keys=False, ensure_ascii=True)
        fh.write("\n")

    manifest = {
        "profile": profile_name,
        "seed": seed,
        "config": cfg,
        "node_count": len(graph["nodes"]),
        "edge_count": len(graph["edges"]),
        "planted_chains": chains,
    }
    with manifest_path.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=False, ensure_ascii=True)
        fh.write("\n")

    return graph_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic AD graphs for GraphHound testing."
    )
    parser.add_argument("--profile", type=str, default=None,
                        help="Profile name from profiles.yaml")
    parser.add_argument("--all", action="store_true",
                        help="Generate for all profiles")
    parser.add_argument("--seed", type=int, default=1,
                        help="RNG seed (default: 1)")
    parser.add_argument("--out", type=str, default="corpus/graphs/",
                        help="Output directory")
    parser.add_argument("--profiles-file", type=str,
                        default=str(Path(__file__).resolve().parent / "profiles.yaml"),
                        help="Path to profiles YAML file")
    args = parser.parse_args()

    profiles = _load_profiles(Path(args.profiles_file))

    if not args.all and not args.profile:
        parser.error("Specify --profile <name> or --all")

    if args.profile and args.profile not in profiles:
        print(f"ERROR: Unknown profile '{args.profile}'. "
              f"Available: {', '.join(profiles.keys())}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out)
    names = list(profiles.keys()) if args.all else [args.profile]

    for name in names:
        path = write_graph(name, args.seed, out_dir, profiles)
        size_kb = path.stat().st_size / 1024
        print(f"  [OK] {path.name}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
