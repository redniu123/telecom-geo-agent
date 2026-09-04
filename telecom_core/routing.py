"""Deterministic NetworkX Dijkstra routing for the P0 demo."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import networkx as nx

from .models import NetworkData, RouteResult, RouteSegment


class RoutePlanningError(RuntimeError):
    """Raised when a task cannot produce a truthful route."""


def _task_value(task: Mapping[str, Any], field: str) -> Any:
    if field not in task:
        raise RoutePlanningError(f"TelecomTask is missing required field {field!r}")
    return task[field]


def _eligible_graph(network: NetworkData, forbidden: set[str]) -> nx.MultiGraph:
    graph = nx.MultiGraph()
    for node_id in sorted(network.nodes):
        node = network.nodes[node_id]
        if node["status"] == "available":
            graph.add_node(node_id)
    for edge_id in sorted(network.edge_records):
        edge = network.edge_records[edge_id]
        if edge["status"] == "unavailable" or edge_id in forbidden:
            continue
        if edge["from_node"] not in graph or edge["to_node"] not in graph:
            continue
        graph.add_edge(
            edge["from_node"],
            edge["to_node"],
            key=edge_id,
            edge_id=edge_id,
            weight=edge["length_m"] * edge["cost_multiplier"],
        )
    return graph


def _select_edge(network: NetworkData, graph: nx.MultiGraph, start: str, end: str) -> dict[str, Any]:
    candidates = graph.get_edge_data(start, end)
    if not candidates:
        raise RoutePlanningError(f"internal route error: no edge between {start!r} and {end!r}")
    edge_id = min(
        candidates,
        key=lambda key: (float(candidates[key]["weight"]), str(candidates[key]["edge_id"])),
    )
    return network.edge_records[edge_id]


def _segment_for_direction(edge: dict[str, Any], start: str, end: str) -> RouteSegment:
    if edge["from_node"] == start and edge["to_node"] == end:
        coordinates = [list(point) for point in edge["geometry"]["coordinates"]]
    elif edge["from_node"] == end and edge["to_node"] == start:
        coordinates = [list(point) for point in reversed(edge["geometry"]["coordinates"])]
    else:
        raise RoutePlanningError(f"edge {edge['edge_id']!r} does not connect {start!r} to {end!r}")
    return {
        "edge_id": edge["edge_id"],
        "from_node": start,
        "to_node": end,
        "asset_type": edge["asset_type"],
        "length_m": round(float(edge["length_m"]), 2),
        "relative_cost": round(float(edge["length_m"] * edge["cost_multiplier"]), 2),
        "geometry": {"type": "LineString", "coordinates": coordinates},
    }


def _merge_segment_coordinates(segments: Sequence[RouteSegment]) -> list[list[float]]:
    merged: list[list[float]] = []
    for segment in segments:
        coordinates = segment["geometry"]["coordinates"]
        if not coordinates:
            raise RoutePlanningError(f"segment {segment['edge_id']!r} has no coordinates")
        if merged and merged[-1] != coordinates[0]:
            raise RoutePlanningError(
                f"route geometry is discontinuous before edge {segment['edge_id']!r}"
            )
        merged.extend(coordinates if not merged else coordinates[1:])
    return merged


def plan_route(
    task: Mapping[str, Any],
    network: NetworkData,
    forbidden_asset_ids: Sequence[str] | None,
    route_id: str,
) -> RouteResult:
    """Plan the lowest relative-cost route; capacity is intentionally ignored."""

    if not isinstance(route_id, str) or not route_id:
        raise RoutePlanningError("route_id must be a non-empty caller-supplied string")
    start_site_id = _task_value(task, "start_site_id")
    end_site_id = _task_value(task, "end_site_id")
    if start_site_id not in network.sites:
        raise RoutePlanningError(f"start site {start_site_id!r} does not exist in loaded network")
    if end_site_id not in network.sites:
        raise RoutePlanningError(f"end site {end_site_id!r} does not exist in loaded network")
    start_node = network.sites[start_site_id]["node_id"]
    end_node = network.sites[end_site_id]["node_id"]
    forbidden = sorted(set(forbidden_asset_ids or []))
    graph = _eligible_graph(network, set(forbidden))

    try:
        # NetworkX computes weighted shortest paths with Dijkstra. Choosing the
        # lexicographically smallest equal-cost node path makes ties stable.
        candidate_paths = nx.all_shortest_paths(
            graph, start_node, end_node, weight="weight", method="dijkstra"
        )
        node_path = min(tuple(path) for path in candidate_paths)
    except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
        raise RoutePlanningError(
            f"no route from site {start_site_id!r} ({start_node}) to "
            f"site {end_site_id!r} ({end_node}); forbidden_asset_ids={forbidden}"
        ) from exc

    segments = [
        _segment_for_direction(_select_edge(network, graph, start, end), start, end)
        for start, end in zip(node_path, node_path[1:])
    ]
    coordinates = _merge_segment_coordinates(segments)
    return {
        "success": True,
        "route_id": route_id,
        "start_site_id": start_site_id,
        "end_site_id": end_site_id,
        "segments": segments,
        "edge_ids": [segment["edge_id"] for segment in segments],
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "total_length_m": round(sum(segment["length_m"] for segment in segments), 2),
        "relative_cost": round(sum(segment["relative_cost"] for segment in segments), 2),
        "forbidden_asset_ids_applied": forbidden,
    }
