# Synthetic Corpus Generator for GraphHound

> **All data is fictional and generated offline.** Node names like
> `user0001@corp.test` are purely synthetic. Labels reflect generator
> design choices, not real exploit outcomes. No network scanning occurs.

## Quick Start

```bash
# Generate all profiles with seed 1
python corpus/generate.py --all --seed 1 --out corpus/graphs/

# Generate a single profile
python corpus/generate.py --profile small_clean --seed 42 --out corpus/graphs/

# Validate all generated graphs
python corpus/validate.py corpus/graphs/

# Generate seeds 1-3 for all profiles
for seed in 1 2 3; do python corpus/generate.py --all --seed $seed --out corpus/graphs/; done
python corpus/validate.py corpus/graphs/
```

## Profiles

Each profile is designed to stress a **structurally different** aspect of the
ranker. See `profiles.yaml` for the exact knobs.

| Profile | ~Nodes | What It Stresses |
|---|---|---|
| `small_clean` | 100 | Baseline: well-managed AD with very few misconfigurations. Tests that the ranker surfaces the few real paths. |
| `small_sloppy` | 150 | Poorly managed small org. High misconfiguration rate means many ACL edges — tests noise tolerance. |
| `medium_balanced` | 500 | Typical enterprise mix. Middle-ground for all parameters. |
| `medium_deep_nesting` | 500 | Very deep group-nesting chains (depth ≤ 12). Tests that long MemberOf paths reaching Tier-0 are not underranked. |
| `large_dense_acl` | 3000 | Dense ACL edges. Tests scalability and ability to prioritise amid many candidate paths. |
| `large_sparse_acl` | 3000 | Dominated by MemberOf; very few ACL edges. Tests that structural membership paths are still evaluated. |
| `xl` | 10000 | Stress-test for memory and enumerator performance at scale. |
| `hardened` | 3000 | Hardened org — very low misconfiguration rate. Tests sensitivity: can the ranker find the rare planted paths? |

## Planted Attack Chains

Every generated graph includes these **planted** chains (recorded in the
`<name>_seed<N>.manifest.json` file):

| Chain | Class | Purpose |
|---|---|---|
| `short_critical_genericall_dcsync` | critical | Short GenericAll → DCSync reaching domain |
| `short_critical_writedacl_addmember` | critical | Short WriteDacl → AddMember reaching Domain Admins |
| `long_memberof_chain_to_tier0` | critical | Long MemberOf-only chain to DA — must NOT be underranked |
| `noisy_but_exploitable` | critical | Noisy lateral-movement chain (CanRDP, HasSession) that IS genuinely exploitable |
| `decoy_chain_0`, `decoy_chain_1` | decoy | Long chains that never reach a privileged target |
| `chokepoint_chain_0`, `chokepoint_chain_1` | critical/medium | Chains sharing a common choke-point node |

## Manifest Format

Each `<name>_seed<N>.manifest.json` contains:

```json
{
  "profile": "small_clean",
  "seed": 1,
  "config": { "...profile knobs..." },
  "node_count": 105,
  "edge_count": 312,
  "planted_chains": [
    {
      "label": "short_critical_genericall_dcsync",
      "intended_class": "critical",
      "node_ids": ["user0001", "user0042", "domain0000"],
      "edge_types": ["GenericAll", "DCSync"]
    }
  ]
}
```

## Validator

`corpus/validate.py` checks:

1. **Ingest**: Every graph loads through the existing `load_bloodhound_json()`
2. **Counts**: Node counts are within 20% of the profile's `node_count`
3. **Chain integrity**: Every planted chain exists edge-by-edge
4. **Reachability**: Every critical chain's target is reachable from its start
5. **Fingerprint uniqueness**: No two graphs have identical structural fingerprints

The fingerprint table shows: node/edge counts, node-type mix, degree
distribution, group nesting depth stats, candidate paths found by
the existing enumerator (`Paths`, capped at 250 with cutoff=6), and the true
number of nodes reachable from owned nodes via unconstrained BFS closure (`ReachNodes`).
Any planted chain requiring more than the default 6 hops includes a `needs_cutoff: <n>`
field in its manifest.

## Determinism

The generator uses **only** `random.Random(seed)` — no system entropy, no
timestamps, no hash randomisation. Same profile + same seed always produces
**byte-identical** output files.

## Assumptions & Limitations

1. **Synthetic data only** — Graph topology is randomly generated, not derived
   from real Active Directory exports. Structural properties (degree
   distribution, cluster coefficient) may differ from production environments.

2. **Labels reflect design, not ground truth** — The `intended_class` on
   planted chains is the generator's intent. It does not represent validated
   exploit outcomes in any real environment.

3. **Simplified ACL semantics** — The generator places ACL edges randomly
   without modelling real AD permission inheritance, GPO linkage semantics,
   or token-based access evaluation.

4. **No Kerberos or NTLM modelling** — `AllowedToDelegate` edges are placed
   structurally; constrained/unconstrained delegation semantics are not
   simulated.

5. **Single domain** — All graphs model a single flat domain (`corp.test`).
   Multi-domain forests, trusts, and cross-domain paths are out of scope.

6. **Edge type constraints are lightweight** — DCSync targets only Domain
   nodes; AddMember targets only Groups. Other edges are placed with minimal
   semantic filtering.

7. **Background noise is uniform random** — Real environments have
   non-uniform permission patterns (e.g., help-desk tiers, delegation
   patterns). The generator's noise is i.i.d., which may be easier or harder
   for the ranker than real-world noise.

8. **Enumerator cutoff** — The validator uses the existing enumerator's
   default `cutoff=6`, so very long planted chains may not appear in the
   candidate path count.

