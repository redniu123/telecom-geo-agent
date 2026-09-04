"""Strict GeoJSON loaders for the fixed P0 telecom demo network."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import networkx as nx

from .models import EdgeRecord, NetworkData, NodeRecord, SiteRecord


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "demo"


class DataValidationError(ValueError):
    """Raised when a demo GeoJSON file fails a required health check."""


def _fail(path: Path, feature_id: str, field: str, detail: str) -> None:
    raise DataValidationError(
        f"{path}: Feature {feature_id!r}, field {field!r}: {detail}"
    )


def _read_feature_collection(path: str | Path) -> tuple[Path, list[dict[str, Any]]]:
    source = Path(path)
    try:
        with source.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise DataValidationError(f"{source}: unable to read valid UTF-8 JSON: {exc}") from exc

    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raise DataValidationError(f"{source}: root field 'type' must be 'FeatureCollection'")
    features = document.get("features")
    if not isinstance(features, list):
        raise DataValidationError(f"{source}: root field 'features' must be a list")
    return source, features


def _require_mapping(
    value: Any, path: Path, feature_id: str, field: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(path, feature_id, field, "must be an object")
    return value


def _require_string(
    properties: dict[str, Any], field: str, path: Path, feature_id: str
) -> str:
    value = properties.get(field)
    if not isinstance(value, str) or not value.strip():
        _fail(path, feature_id, field, "must be a non-empty string")
    return value


def _require_number(
    properties: dict[str, Any], field: str, path: Path, feature_id: str
) -> float:
    value = properties.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(path, feature_id, field, "must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        _fail(path, feature_id, field, "must be a finite number")
    return number


def _require_nonnegative_integer(
    properties: dict[str, Any], field: str, path: Path, feature_id: str
) -> int:
    value = properties.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(path, feature_id, field, "must be a non-negative integer")
    return value


def _coordinate(value: Any, path: Path, feature_id: str, field: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 2:
        _fail(path, feature_id, field, "must be [longitude, latitude]")
    longitude, latitude = value
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        _fail(path, feature_id, field, "coordinates must be finite numbers")
    longitude = float(longitude)
    latitude = float(latitude)
    if not math.isfinite(longitude) or not math.isfinite(latitude):
        _fail(path, feature_id, field, "coordinates must be finite numbers")
    if not -180.0 <= longitude <= 180.0:
        _fail(path, feature_id, field, "longitude must be within [-180, 180]")
    if not -90.0 <= latitude <= 90.0:
        _fail(path, feature_id, field, "latitude must be within [-90, 90]")
    return [longitude, latitude]


def _point_geometry(value: Any, path: Path, feature_id: str) -> dict[str, Any]:
    geometry = _require_mapping(value, path, feature_id, "geometry")
    if geometry.get("type") != "Point":
        _fail(path, feature_id, "geometry.type", "must be 'Point'")
    return {"type": "Point", "coordinates": _coordinate(
        geometry.get("coordinates"), path, feature_id, "geometry.coordinates"
    )}


def _line_geometry(value: Any, path: Path, feature_id: str) -> dict[str, Any]:
    geometry = _require_mapping(value, path, feature_id, "geometry")
    if geometry.get("type") != "LineString":
        _fail(path, feature_id, "geometry.type", "must be 'LineString'")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        _fail(path, feature_id, "geometry.coordinates", "must contain at least two points")
    return {
        "type": "LineString",
        "coordinates": [
            _coordinate(item, path, feature_id, f"geometry.coordinates[{index}]")
            for index, item in enumerate(coordinates)
        ],
    }


def load_sites(path: str | Path) -> dict[str, SiteRecord]:
    """Load and validate site Point features, keyed by site_id."""

    source, features = _read_feature_collection(path)
    sites: dict[str, SiteRecord] = {}
    seen_feature_ids: set[str] = set()
    for index, feature in enumerate(features):
        fallback_id = f"index:{index}"
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            _fail(source, fallback_id, "type", "must be 'Feature'")
        feature_id = str(feature.get("id", fallback_id))
        if feature_id in seen_feature_ids:
            _fail(source, feature_id, "id", "must be unique")
        seen_feature_ids.add(feature_id)
        properties = _require_mapping(feature.get("properties"), source, feature_id, "properties")
        site_id = _require_string(properties, "site_id", source, feature_id)
        if site_id in sites:
            _fail(source, feature_id, "site_id", f"duplicate site ID {site_id!r}")
        name = _require_string(properties, "name", source, feature_id)
        site_type = _require_string(properties, "site_type", source, feature_id)
        if site_type not in {"telecom_room", "base_station"}:
            _fail(source, feature_id, "site_type", "must be telecom_room or base_station")
        node_id = _require_string(properties, "node_id", source, feature_id)
        status = _require_string(properties, "status", source, feature_id)
        if status != "available":
            _fail(source, feature_id, "status", "must be 'available'")
        geometry = _point_geometry(feature.get("geometry"), source, feature_id)
        sites[site_id] = {
            "site_id": site_id,
            "name": name,
            "site_type": site_type,
            "node_id": node_id,
            "status": status,
            "geometry": geometry,
        }
    return sites


def load_network(path: str | Path) -> NetworkData:
    """Load validated node and edge features without silently skipping any."""

    source, features = _read_feature_collection(path)
    nodes: dict[str, NodeRecord] = {}
    edges: dict[str, EdgeRecord] = {}
    seen_feature_ids: set[str] = set()

    for index, feature in enumerate(features):
        fallback_id = f"index:{index}"
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            _fail(source, fallback_id, "type", "must be 'Feature'")
        feature_id = str(feature.get("id", fallback_id))
        if feature_id in seen_feature_ids:
            _fail(source, feature_id, "id", "must be unique")
        seen_feature_ids.add(feature_id)
        properties = _require_mapping(feature.get("properties"), source, feature_id, "properties")
        feature_type = _require_string(properties, "feature_type", source, feature_id)

        if feature_type == "node":
            node_id = _require_string(properties, "node_id", source, feature_id)
            if node_id in nodes:
                _fail(source, feature_id, "node_id", f"duplicate node ID {node_id!r}")
            status = _require_string(properties, "status", source, feature_id)
            if status not in {"available", "unavailable"}:
                _fail(source, feature_id, "status", "must be available or unavailable")
            nodes[node_id] = {
                "node_id": node_id,
                "status": status,
                "geometry": _point_geometry(feature.get("geometry"), source, feature_id),
            }
            continue

        if feature_type != "edge":
            _fail(source, feature_id, "feature_type", "must be 'node' or 'edge'")
        edge_id = _require_string(properties, "edge_id", source, feature_id)
        if edge_id in edges:
            _fail(source, feature_id, "edge_id", f"duplicate edge ID {edge_id!r}")
        from_node = _require_string(properties, "from_node", source, feature_id)
        to_node = _require_string(properties, "to_node", source, feature_id)
        asset_type = _require_string(properties, "asset_type", source, feature_id)
        if asset_type not in {"existing_duct", "new_build"}:
            _fail(source, feature_id, "asset_type", "must be existing_duct or new_build")
        length_m = _require_number(properties, "length_m", source, feature_id)
        if length_m <= 0:
            _fail(source, feature_id, "length_m", "must be greater than zero")
        cost_multiplier = _require_number(properties, "cost_multiplier", source, feature_id)
        if cost_multiplier <= 0:
            _fail(source, feature_id, "cost_multiplier", "must be greater than zero")
        capacity_cores = _require_nonnegative_integer(
            properties, "capacity_cores", source, feature_id
        )
        used_cores = _require_nonnegative_integer(properties, "used_cores", source, feature_id)
        if used_cores > capacity_cores:
            _fail(source, feature_id, "used_cores", "must not exceed capacity_cores")
        status = _require_string(properties, "status", source, feature_id)
        if status not in {"available", "unavailable"}:
            _fail(source, feature_id, "status", "must be available or unavailable")
        edges[edge_id] = {
            "edge_id": edge_id,
            "from_node": from_node,
            "to_node": to_node,
            "asset_type": asset_type,
            "length_m": length_m,
            "cost_multiplier": cost_multiplier,
            "capacity_cores": capacity_cores,
            "used_cores": used_cores,
            "status": status,
            "geometry": _line_geometry(feature.get("geometry"), source, feature_id),
        }

    if not nodes:
        raise DataValidationError(f"{source}: no node Features found")
    if not edges:
        raise DataValidationError(f"{source}: no edge Features found")

    for edge_id, edge in edges.items():
        for field in ("from_node", "to_node"):
            node_id = edge[field]
            if node_id not in nodes:
                _fail(source, f"edge:{edge_id}", field, f"references missing node {node_id!r}")
        coordinates = edge["geometry"]["coordinates"]
        from_coordinate = nodes[edge["from_node"]]["geometry"]["coordinates"]
        to_coordinate = nodes[edge["to_node"]]["geometry"]["coordinates"]
        if coordinates[0] != from_coordinate:
            _fail(source, f"edge:{edge_id}", "geometry.coordinates[0]", "must match from_node")
        if coordinates[-1] != to_coordinate:
            _fail(source, f"edge:{edge_id}", "geometry.coordinates[-1]", "must match to_node")

    graph = nx.MultiGraph()
    for node_id in sorted(nodes):
        graph.add_node(node_id, **nodes[node_id])
    for edge_id in sorted(edges):
        edge = edges[edge_id]
        graph.add_edge(
            edge["from_node"],
            edge["to_node"],
            key=edge_id,
            weight=edge["length_m"] * edge["cost_multiplier"],
            **edge,
        )
    return NetworkData(graph=graph, nodes=nodes, edge_records=edges)


def load_demo_network(
    network_path: str | Path | None = None,
    sites_path: str | Path | None = None,
) -> NetworkData:
    """Load the repository demo network and validate all site-node bindings."""

    network_source = Path(network_path) if network_path is not None else DEFAULT_DATA_DIR / "network.geojson"
    sites_source = Path(sites_path) if sites_path is not None else DEFAULT_DATA_DIR / "sites.geojson"
    network = load_network(network_source)
    sites = load_sites(sites_source)
    for site_id, site in sites.items():
        node_id = site["node_id"]
        if node_id not in network.nodes:
            _fail(sites_source, f"site:{site_id}", "node_id", f"references missing node {node_id!r}")
        if site["geometry"]["coordinates"] != network.nodes[node_id]["geometry"]["coordinates"]:
            _fail(sites_source, f"site:{site_id}", "geometry.coordinates", "must match bound node")
    network.sites = sites
    return network
