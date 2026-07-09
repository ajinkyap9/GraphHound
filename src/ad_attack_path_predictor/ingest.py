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
    
    if source.suffix.lower() == ".zip":
        import zipfile
        nodes_dict = {}
        edges = []
        
        edge_types_map = {
            "memberof": "MemberOf",
            "adminto": "AdminTo",
            "hassession": "HasSession",
            "genericall": "GenericAll",
            "genericwrite": "GenericWrite",
            "writedacl": "WriteDacl",
            "writeowner": "WriteOwner",
            "owns": "Owns",
            "canrdp": "CanRDP",
            "dcsync": "DCSync",
            "allextendedrights": "AllExtendedRights",
            "getchanges": "GetChanges",
            "getchangesall": "GetChangesAll",
            "gplink": "GPLink",
            "canpsremote": "CanPSRemote",
            "executedcom": "ExecuteDCOM",
        }
        
        def get_kind(filename):
            fn = filename.lower()
            if "users.json" in fn: return "User"
            if "groups.json" in fn: return "Group"
            if "computers.json" in fn: return "Computer"
            if "domains.json" in fn: return "Domain"
            if "ous.json" in fn: return "OU"
            if "gpos.json" in fn: return "GPO"
            if "containers.json" in fn: return "Container"
            return "Unknown"

        with zipfile.ZipFile(source, 'r') as zip_ref:
            for filename in zip_ref.namelist():
                kind = get_kind(filename)
                if kind == "Unknown":
                    continue
                with zip_ref.open(filename) as f:
                    raw_data = json.loads(f.read().decode("utf-8-sig"))
                    key = "data" if "data" in raw_data else list(raw_data.keys())[0]
                    for item in raw_data[key]:
                        node_id = str(_pick(item, "ObjectIdentifier", "id", "objectid", "name", "Name"))
                        props = item.get("Properties", {})
                        name = str(props.get("name", _pick(item, "name", "Name", "label", "Label", default=node_id)))
                        
                        owned = bool(props.get("owned", False))
                        high_value = bool(props.get("highvalue", False))
                        # Domain Controllers, Domain Admins, and Domain are high value by default
                        if "domain admins" in name.lower() or "domain controllers" in name.lower() or kind == "Domain":
                            high_value = True
                            
                        # Keep properties clean of duplicates
                        prop_clean = {k: v for k, v in item.items() if k not in {"ObjectIdentifier", "Properties", "IsDeleted", "IsACLProtected"}}
                        prop_clean.update(props)
                        
                        nodes_dict[node_id] = AttackNode(
                            id=node_id,
                            name=name,
                            kind=_node_kind(kind),
                            owned=owned,
                            high_value=high_value,
                            properties=prop_clean
                        )
                        
                        for ace in item.get("Aces", []):
                            src = str(ace.get("PrincipalSID"))
                            tgt = node_id
                            rtype = str(ace.get("RightName"))
                            normalized_type = edge_types_map.get(rtype.lower(), rtype)
                            edges.append(AttackEdge(
                                source=src,
                                target=tgt,
                                type=normalized_type,
                                properties={
                                    "PrincipalSID": src,
                                    "PrincipalType": ace.get("PrincipalType"),
                                    "RightName": rtype,
                                    "IsInherited": ace.get("IsInherited", False)
                                }
                            ))
                            
                        for m in item.get("Members", []):
                            src = str(m.get("ObjectIdentifier"))
                            tgt = node_id
                            edges.append(AttackEdge(
                                source=src,
                                target=tgt,
                                type="MemberOf",
                                properties={
                                    "ObjectIdentifier": src,
                                    "ObjectType": m.get("ObjectType")
                                }
                            ))
                            
                        pgsid = item.get("PrimaryGroupSID")
                        if pgsid:
                            edges.append(AttackEdge(
                                source=node_id,
                                target=str(pgsid),
                                type="MemberOf",
                                properties={}
                            ))
                            
                        for link in item.get("Links", []):
                            gpo_guid = str(link.get("GUID"))
                            edges.append(AttackEdge(
                                source=gpo_guid,
                                target=node_id,
                                type="GPLink",
                                properties={
                                    "GUID": gpo_guid,
                                    "IsEnforced": link.get("IsEnforced", False)
                                }
                            ))
                            
                        sessions_val = item.get("Sessions", {})
                        if isinstance(sessions_val, dict) and sessions_val.get("Results"):
                            for sess in sessions_val["Results"]:
                                user_sid = sess.get("UserSID")
                                if user_sid:
                                    edges.append(AttackEdge(
                                        source=node_id,
                                        target=str(user_sid),
                                        type="HasSession",
                                        properties={}
                                    ))

        # Ensure all edge sources/targets exist in nodes
        for edge in edges:
            if edge.source not in nodes_dict:
                nodes_dict[edge.source] = AttackNode(id=edge.source, name=edge.source)
            if edge.target not in nodes_dict:
                nodes_dict[edge.target] = AttackNode(id=edge.target, name=edge.target)
                
        return AttackGraph(nodes=list(nodes_dict.values()), edges=edges)

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

