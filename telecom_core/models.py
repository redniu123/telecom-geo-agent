"""Frozen P0 public data shapes and the internal loaded-network container."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict

import networkx as nx


class TelecomTask(TypedDict):
    task_type: str
    start_site_id: str
    end_site_id: str
    fiber_cores: int
    prefer_existing_duct: bool


class GeoJSONLineString(TypedDict):
    type: str
    coordinates: list[list[float]]


class RouteSegment(TypedDict):
    edge_id: str
    from_node: str
    to_node: str
    asset_type: str
    length_m: float
    relative_cost: float
    geometry: GeoJSONLineString


class RouteResult(TypedDict):
    success: bool
    route_id: str
    start_site_id: str
    end_site_id: str
    segments: list[RouteSegment]
    edge_ids: list[str]
    geometry: GeoJSONLineString
    total_length_m: float
    relative_cost: float
    forbidden_asset_ids_applied: list[str]


class ValidationViolation(TypedDict):
    rule_id: str
    type: str
    asset_id: str | None
    severity: str
    message: str
    repair_hint: str | None


class ValidationResult(TypedDict):
    passed: bool
    violations: list[ValidationViolation]


class BOMResult(TypedDict):
    total_length_m: float
    existing_duct_length_m: float
    new_build_length_m: float
    recommended_cable_length_m: float
    slack_ratio: float
    used_edge_ids: list[str]


SiteRecord = dict[str, Any]
NodeRecord = dict[str, Any]
EdgeRecord = dict[str, Any]


@dataclass
class NetworkData:
    """Validated deterministic network plus optional site bindings."""

    graph: nx.MultiGraph
    nodes: dict[str, NodeRecord]
    edge_records: dict[str, EdgeRecord]
    sites: dict[str, SiteRecord] = field(default_factory=dict)
