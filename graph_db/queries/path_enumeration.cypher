// Phase 2 — All-paths enumeration bounded by hop depth.
//
// Parameters:
// $start_id   — low-privilege starting principal id
// $target_id  — privileged target id (e.g. DOMAIN ADMINS group)
// $max_hops   — maximum path length (recommended: 6)
//
// Returns all simple paths (no repeated nodes) from start to target,
// bounded by hop depth.  If the query is too slow, tighten $max_hops
// before reducing the LIMIT — pruning depth keeps results meaningful.

MATCH (start:AttackNode {id: $start_id}), (target:AttackNode {id: $target_id})
MATCH path = (start)-[*1..$max_hops]->(target)
WHERE ALL(node IN nodes(path) WHERE single(other IN nodes(path) WHERE other = node))
RETURN path
LIMIT 500;
