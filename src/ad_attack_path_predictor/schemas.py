from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NodeKind(str, Enum):
    USER = "User"
    GROUP = "Group"
    COMPUTER = "Computer"
    DOMAIN = "Domain"
    OU = "OU"
    GPO = "GPO"
    UNKNOWN = "Unknown"


class AttackNode(BaseModel):
    id: str
    name: str
    kind: NodeKind = NodeKind.UNKNOWN
    owned: bool = False
    high_value: bool = False
    properties: dict[str, Any] = Field(default_factory=dict)


class AttackEdge(BaseModel):
    source: str
    target: str
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class AttackGraph(BaseModel):
    nodes: list[AttackNode]
    edges: list[AttackEdge]


class EdgeRiskProfile(BaseModel):
    edge_type: str
    attack_id: str
    tactic: str
    prevalence: float = Field(ge=0, le=1)
    noisiness: float = Field(ge=0, le=1)
    impact: float = Field(ge=0, le=1)
    remediation: str


class PathFeatures(BaseModel):
    path_id: str
    node_ids: list[str]
    edge_types: list[str]
    length: int
    unique_edge_types: int
    mean_prevalence: float
    mean_noisiness: float
    max_impact: float
    choke_point_score: float
    high_value_steps: int
    quiet_edge_ratio: float
    technique_ids: list[str]


class RankedPath(BaseModel):
    rank: int
    path_id: str
    score: float
    confidence: str
    nodes: list[AttackNode]
    edges: list[AttackEdge]
    features: PathFeatures
    explanations: list[str]
    remediation: list[str]


class RankingSummary(BaseModel):
    graph_nodes: int
    graph_edges: int
    candidate_paths: int
    returned_paths: int
    start_nodes: list[str]
    target_nodes: list[str]
    top_score: float | None = None
    has_session: bool = False
    has_acl: bool = False
    has_gpo: bool = False
    environment_type: str = "Unknown"
    edge_simulation_used: bool = False



class RankingResponse(BaseModel):
    summary: RankingSummary
    paths: list[RankedPath]

