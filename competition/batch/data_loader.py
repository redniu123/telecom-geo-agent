"""Strict loader for the audited public-background/synthetic-resource batch dataset."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx

from telecom_core.models import NetworkData

from .resource_ledger import LedgerError


class BatchDataError(ValueError):
    """Raised when the batch dataset cannot be trusted."""


@dataclass(frozen=True)
class BatchDataset:
    root: Path
    dataset_id: str
    manifest: dict[str, Any]
    network: NetworkData
    resources: dict[str, dict[str, Any]]
    facilities: dict[str, dict[str, Any]]

    @property
    def site_ids(self) -> set[str]:
        return {key for key, item in self.facilities.items() if item["site_type"] == "access_site"}

    @property
    def room_ids(self) -> set[str]:
        return {key for key, item in self.facilities.items() if item["site_type"] == "aggregation_room"}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BatchDataError(f"无法读取有效 UTF-8 JSON：{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BatchDataError(f"JSON 根必须是对象：{path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _coordinate(value: Any, context: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 2 or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        raise BatchDataError(f"{context}: 坐标必须为 [longitude, latitude]")
    point = [float(value[0]), float(value[1])]
    if not all(math.isfinite(item) for item in point):
        raise BatchDataError(f"{context}: 坐标必须有限")
    return point


def _features(path: Path) -> list[dict[str, Any]]:
    document = _read_json(path)
    if document.get("type") != "FeatureCollection" or not isinstance(document.get("features"), list):
        raise BatchDataError(f"不是 GeoJSON FeatureCollection：{path}")
    return document["features"]


def load_batch_dataset(repository_root: str | Path, *, verify_hashes: bool = True) -> BatchDataset:
    root = Path(repository_root).resolve() / "data" / "competition_batch"
    manifest = _read_json(root / "manifest.json")
    if manifest.get("schema_version") != 1:
        raise BatchDataError("不支持的批量数据 manifest 版本")
    if verify_hashes:
        for relative, evidence in manifest.get("generated_files", {}).items():
            path = root / relative
            if not path.is_file() or _sha256(path) != evidence.get("sha256"):
                raise BatchDataError(f"批量数据哈希不匹配：{relative}")

    node_records: dict[str, dict[str, Any]] = {}
    edge_records: dict[str, dict[str, Any]] = {}
    resources: dict[str, dict[str, Any]] = {}
    for feature in _features(root / "network.geojson"):
        props = feature.get("properties") or {}
        feature_type = props.get("feature_type")
        geometry = feature.get("geometry") or {}
        if feature_type == "node":
            node_id = props.get("node_id")
            if not isinstance(node_id, str) or node_id in node_records or geometry.get("type") != "Point":
                raise BatchDataError("network.geojson 包含非法或重复节点")
            node_records[node_id] = {
                "node_id": node_id,
                "status": "available",
                "geometry": {"type": "Point", "coordinates": _coordinate(geometry.get("coordinates"), node_id)},
            }
            continue
        if feature_type != "edge":
            raise BatchDataError("network.geojson feature_type 必须为 node/edge")
        asset_id = props.get("asset_id")
        if not isinstance(asset_id, str) or asset_id in edge_records:
            raise BatchDataError("network.geojson 包含非法或重复 asset_id")
        from_node, to_node = props.get("from_node"), props.get("to_node")
        if not isinstance(from_node, str) or not isinstance(to_node, str):
            raise BatchDataError(f"{asset_id}: 缺少拓扑端点")
        length = props.get("length_m")
        cost = props.get("cost_multiplier")
        if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)) or float(item) <= 0 for item in (length, cost)):
            raise BatchDataError(f"{asset_id}: 长度/相对成本必须为正有限数")
        if geometry.get("type") != "LineString" or not isinstance(geometry.get("coordinates"), list) or len(geometry["coordinates"]) < 2:
            raise BatchDataError(f"{asset_id}: 几何必须是 LineString")
        resource = {
            "asset_id": asset_id,
            "subduct_total": props.get("subduct_total"),
            "subduct_used_baseline": props.get("subduct_used_baseline"),
            "subduct_reserved_batch": 0,
            "segment_status": props.get("segment_status"),
            "capacity_status": props.get("capacity_status"),
            "geometry_source": props.get("geometry_source"),
            "business_attributes_source": props.get("business_attributes_source"),
        }
        resources[asset_id] = resource
        # Compatibility adapter only: the frozen routing core consumes geometry,
        # status, type and cost. Legacy fiber-capacity values are not serialized
        # and are never used as batch subduct capacity.
        edge_records[asset_id] = {
            "edge_id": asset_id,
            "from_node": from_node,
            "to_node": to_node,
            "asset_type": props.get("asset_type"),
            "length_m": float(length),
            "cost_multiplier": float(cost),
            "capacity_cores": 0,
            "used_cores": 0,
            "status": "available",
            "geometry": {
                "type": "LineString",
                "coordinates": [_coordinate(point, asset_id) for point in geometry["coordinates"]],
            },
        }

    if len(node_records) != 411 or len(edge_records) != 444:
        raise BatchDataError(f"主展示网络必须是 411 节点/444 边，实际 {len(node_records)}/{len(edge_records)}")
    graph = nx.MultiGraph()
    for node_id, node in sorted(node_records.items()):
        graph.add_node(node_id, **node)
    for asset_id, edge in sorted(edge_records.items()):
        if edge["from_node"] not in node_records or edge["to_node"] not in node_records:
            raise BatchDataError(f"{asset_id}: 引用不存在节点")
        graph.add_edge(edge["from_node"], edge["to_node"], key=asset_id, weight=edge["length_m"] * edge["cost_multiplier"], **edge)
    if not nx.is_connected(nx.Graph(graph)):
        raise BatchDataError("411/444 主展示网络必须连通")
    try:
        # Validate the separated subduct fields independently of the route core.
        from .resource_ledger import ResourceLedger

        ResourceLedger(resources).assert_conservation()
    except LedgerError as exc:
        raise BatchDataError(f"资源台账无效：{exc}") from exc

    facilities: dict[str, dict[str, Any]] = {}
    sites_for_core: dict[str, dict[str, Any]] = {}
    for feature in _features(root / "facilities.geojson"):
        props = feature.get("properties") or {}
        site_id = props.get("site_id")
        site_type = props.get("site_type")
        node_id = props.get("node_id")
        geometry = feature.get("geometry") or {}
        if not isinstance(site_id, str) or site_id in facilities or site_type not in {"aggregation_room", "access_site"} or node_id not in node_records:
            raise BatchDataError("facilities.geojson 包含非法设施")
        coordinates = _coordinate(geometry.get("coordinates"), site_id)
        if coordinates != node_records[node_id]["geometry"]["coordinates"]:
            raise BatchDataError(f"{site_id}: 设施未精确绑定节点")
        item = {
            "site_id": site_id,
            "name": props.get("name", site_id),
            "site_type": site_type,
            "node_id": node_id,
            "snap_distance_m": props.get("snap_distance_m", 0.0),
            "data_class": props.get("data_class"),
            "source_rule": props.get("source_rule"),
            "geometry": {"type": "Point", "coordinates": coordinates},
        }
        facilities[site_id] = item
        sites_for_core[site_id] = {
            "site_id": site_id,
            "name": item["name"],
            "site_type": "telecom_room" if site_type == "aggregation_room" else "base_station",
            "node_id": node_id,
            "status": "available",
            "geometry": item["geometry"],
        }
    if len({key for key, value in facilities.items() if value["site_type"] == "aggregation_room"}) != 3:
        raise BatchDataError("主展示数据必须包含 3 个合成汇聚机房")
    if len({key for key, value in facilities.items() if value["site_type"] == "access_site"}) != 30:
        raise BatchDataError("主展示数据必须包含 30 个合成接入设施")
    network = NetworkData(graph=graph, nodes=node_records, edge_records=edge_records, sites=sites_for_core)
    return BatchDataset(root=root, dataset_id=manifest["dataset_id"], manifest=manifest, network=network, resources=resources, facilities=facilities)
