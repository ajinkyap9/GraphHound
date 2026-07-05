"""Centrality computation wrappers for NetworkX graphs.

Computes betweenness and degree centrality for nodes in the attack graph.
This is the NetworkX equivalent of Neo4j GDS centrality calls — no running
Neo4j instance is needed.
"""

from __future__ import annotations

import networkx as nx


def compute_betweenness_centrality(nx_graph: nx.MultiDiGraph) -> dict[str, float]:
    """Return betweenness centrality for every node in *nx_graph*.

    Betweenness centrality quantifies how often a node lies on shortest paths
    between other nodes — a high score means the node is a key transit point
    that many attack paths pass through.
    """
    simple = nx.DiGraph(nx_graph)
    return nx.betweenness_centrality(simple, normalized=True)


def compute_degree_centrality(nx_graph: nx.MultiDiGraph) -> dict[str, float]:
    """Return degree centrality for every node in *nx_graph*.

    Degree centrality is the fraction of nodes each node is connected to.
    Nodes with many connections are more exposed.
    """
    simple = nx.DiGraph(nx_graph)
    return nx.degree_centrality(simple)
