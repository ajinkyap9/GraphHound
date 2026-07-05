from __future__ import annotations

from collections.abc import Iterable

import networkx as nx

from .schemas import AttackEdge, AttackGraph, AttackNode


def resolve_start_nodes(graph: AttackGraph, requested: str | None = None) -> list[str]:
    if requested:
        lowered = requested.lower()
        return [node.id for node in graph.nodes if node.id.lower() == lowered or node.name.lower() == lowered]
    owned = [node.id for node in graph.nodes if node.owned]
    if owned:
        return owned
    return [node.id for node in graph.nodes if node.kind.value == "User"][:1]


def resolve_target_nodes(graph: AttackGraph, requested: str | None = None) -> list[str]:
    if requested:
        lowered = requested.lower()
        return [node.id for node in graph.nodes if node.id.lower() == lowered or node.name.lower() == lowered]
    high_value = [node.id for node in graph.nodes if node.high_value]
    if high_value:
        return high_value
    return [node.id for node in graph.nodes if "admin" in node.name.lower()]


def _edge_between(graph: nx.MultiDiGraph, source: str, target: str) -> AttackEdge:
    edge_data = graph.get_edge_data(source, target) or {}
    best = sorted(edge_data.values(), key=lambda item: item.get("type", ""))[0]
    return AttackEdge(
        source=best["source"],
        target=best["target"],
        type=best["type"],
        properties=best.get("properties", {}),
    )


def _all_simple_paths_bfs(nxg: nx.MultiDiGraph, source: str, target: str, cutoff: int) -> Iterable[list[str]]:
    import collections
    queue = collections.deque([(source, (source,))])
    while queue:
        node, path = queue.popleft()
        if node == target:
            yield list(path)
            continue
        if len(path) - 1 >= cutoff:
            continue
        for neighbor in nxg.successors(node):
            if neighbor not in path:
                queue.append((neighbor, path + (neighbor,)))


def enumerate_candidate_paths(
    graph: AttackGraph,
    nx_graph: nx.MultiDiGraph,
    starts: Iterable[str],
    targets: Iterable[str],
    cutoff: int = 6,
    max_paths: int = 250,
) -> list[tuple[list[AttackNode], list[AttackEdge]]]:
    node_lookup = {node.id: node for node in graph.nodes}
    paths: list[tuple[list[AttackNode], list[AttackEdge]]] = []

    for start in starts:
        for target in targets:
            if start not in nx_graph or target not in nx_graph or start == target:
                continue
            for node_path in _all_simple_paths_bfs(nx_graph, source=start, target=target, cutoff=cutoff):
                nodes = [node_lookup[node_id] for node_id in node_path]
                edges = [_edge_between(nx_graph, source, dest) for source, dest in zip(node_path, node_path[1:])]
                paths.append((nodes, edges))
                if len(paths) >= max_paths:
                    return paths
    return paths


