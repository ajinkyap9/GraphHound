from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx

from .schemas import AttackEdge, AttackGraph, AttackNode, NodeKind


def _pick(item: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
    return default


def _node_kind(value: Any) -> NodeKind:
    normalized = str(value or "Unknown").strip()
    for kind in NodeKind:
        if normalized.lower() == kind.value.lower():
            return kind
    return NodeKind.UNKNOWN


def normalize_node(raw: dict[str, Any]) -> AttackNode:
    node_id = str(_pick(raw, "id", "objectid", "ObjectIdentifier", "name", "Name"))
    name = str(_pick(raw, "name", "Name", "label", "Label", default=node_id))
    return AttackNode(
        id=node_id,
        name=name,
        kind=_node_kind(_pick(raw, "kind", "type", "label", "Label")),
        owned=bool(_pick(raw, "owned", "Owned", default=False)),
        high_value=bool(_pick(raw, "high_value", "highvalue", "HighValue", default=False)),
        properties={k: v for k, v in raw.items() if k not in {"id", "name", "kind", "type", "label"}},
    )


def normalize_edge(raw: dict[str, Any]) -> AttackEdge:
    return AttackEdge(
        source=str(_pick(raw, "source", "start", "StartNode", "source_id", "Source")),
        target=str(_pick(raw, "target", "end", "EndNode", "target_id", "Target")),
        type=str(_pick(raw, "type", "relationship", "RelationshipType", "label", default="RelatedTo")),
        properties={k: v for k, v in raw.items() if k not in {"source", "target", "type"}},
    )


def load_bloodhound_json(path: str | Path) -> AttackGraph:
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    if isinstance(raw, list):
        raise ValueError("Expected an object with 'nodes' and 'edges' arrays, not a top-level list.")

    nodes = [normalize_node(node) for node in raw.get("nodes", [])]
    edges = [normalize_edge(edge) for edge in raw.get("edges", [])]

    known = {node.id for node in nodes}
    for edge in edges:
        if edge.source not in known:
            nodes.append(AttackNode(id=edge.source, name=edge.source))
            known.add(edge.source)
        if edge.target not in known:
            nodes.append(AttackNode(id=edge.target, name=edge.target))
            known.add(edge.target)

    return AttackGraph(nodes=nodes, edges=edges)


def to_networkx(graph: AttackGraph) -> nx.MultiDiGraph:
    nx_graph = nx.MultiDiGraph()
    for node in graph.nodes:
        nx_graph.add_node(node.id, **node.model_dump())
    for index, edge in enumerate(graph.edges):
        nx_graph.add_edge(edge.source, edge.target, key=f"{edge.type}:{index}", **edge.model_dump())
    return nx_graph


def dump_graph(graph: AttackGraph, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        json.dump(graph.model_dump(), handle, indent=2)

