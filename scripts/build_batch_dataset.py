"""Build the 411-node/444-edge batch dataset from the audited local OSM staging set.

Public geometries are copied/derived with attribution. Facilities, channel
identity, subduct resources, status, priority and task demand are synthetic.
No real carrier asset or expected route answer is created.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import networkx as nx

from build_competition_dataset import (
    EXPECTED_DATASET_ID,
    EXPECTED_SOURCE_MANIFEST_SHA256,
    SENSITIVE_KEY,
    _distance_m,
    _feature_collection,
    _read_json,
    _road_graph,
    _sha256,
    _write_json,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGING = Path(r"E:\Users\zhubinhua\Documents\ChatGPT\通信工程agent_data_staging\selected")
DEFAULT_OUTPUT = ROOT / "data" / "competition_batch"
DATASET_ID = "osm_shanghai_public_background_synthetic_batch_v1"


def _validate_staging(staging: Path) -> dict[str, Any]:
    manifest_path = staging / "source_manifest.json"
    if _sha256(manifest_path) != EXPECTED_SOURCE_MANIFEST_SHA256:
        raise ValueError("audited staging source_manifest.json SHA-256 mismatch")
    manifest = _read_json(manifest_path)
    if manifest.get("dataset_id") != EXPECTED_DATASET_ID:
        raise ValueError("unexpected audited staging dataset")
    expected_counts = {"roads": 93, "buildings": 2716, "water": 4, "landuse": 50, "railways": 10, "site_candidates": 2}
    for name, expected in expected_counts.items():
        entry = manifest["layers"][name]
        path = staging / Path(entry["file"]).name
        if not path.is_file() or _sha256(path) != entry["sha256"]:
            raise ValueError(f"audited staging hash mismatch: {name}")
        document = _read_json(path)
        if len(document.get("features", [])) != expected:
            raise ValueError(f"audited staging feature count mismatch: {name}")
        for feature in document["features"]:
            matched = [key for key in (feature.get("properties") or {}) if SENSITIVE_KEY.match(key)]
            if matched:
                raise ValueError(f"sensitive tag keys present in {name}: {matched}")
    return manifest


def _edge_key(left, right):
    return tuple(sorted((left, right)))


def _path_edges(path, edge_ids):
    return [edge_ids[_edge_key(left, right)] for left, right in zip(path, path[1:])]


def _choose_rooms(graph: nx.Graph) -> list[tuple[float, float]]:
    candidates = sorted(node for node in graph if graph.degree(node) >= 2)
    first = min(candidates, key=lambda node: (node[0], node[1]))
    lengths_first = nx.single_source_dijkstra_path_length(graph, first, weight="length_m")
    second = max(candidates, key=lambda node: (lengths_first[node], node))
    lengths_second = nx.single_source_dijkstra_path_length(graph, second, weight="length_m")
    third = max(candidates, key=lambda node: (min(lengths_first[node], lengths_second[node]), node))
    return [first, second, third]


def _spread_nodes(graph: nx.Graph, seeds: list, count: int, *, excluded: set) -> list:
    candidates = sorted(node for node in graph if node not in excluded)
    distances = {seed: nx.single_source_dijkstra_path_length(graph, seed, weight="length_m") for seed in seeds}
    selected: list = []
    while len(selected) < count:
        node = max(candidates, key=lambda item: (min(table[item] for table in distances.values()), item))
        selected.append(node)
        candidates.remove(node)
        distances[node] = nx.single_source_dijkstra_path_length(graph, node, weight="length_m")
    return selected


def _path(graph, node, room):
    return nx.shortest_path(graph, node, room, weight="routing_weight")


def _routable_edge(graph, node, room, edge_ids, excluded=frozenset()):
    path = _path(graph, node, room)
    for left, right in zip(path[1:-1], path[2:]):
        asset_id = edge_ids[_edge_key(left, right)]
        if asset_id in excluded:
            continue
        alternate = graph.copy()
        alternate.remove_edge(left, right)
        if nx.has_path(alternate, node, room):
            return asset_id
    for left, right in zip(path, path[1:]):
        asset_id = edge_ids[_edge_key(left, right)]
        if asset_id in excluded:
            continue
        alternate = graph.copy()
        alternate.remove_edge(left, right)
        if nx.has_path(alternate, node, room):
            return asset_id
    raise ValueError("could not find a deterministically reroutable edge")


def _cross_task_pair(graph, candidates, rooms, edge_ids):
    for room in rooms:
        paths = {node: _path(graph, node, room) for node in candidates}
        path_assets = {node: _path_edges(path, edge_ids) for node, path in paths.items()}
        for index, first in enumerate(candidates):
            for second in candidates[index + 1:]:
                shared = [asset for asset in path_assets[first] if asset in set(path_assets[second])]
                for asset_id in shared:
                    endpoints = next(key for key, value in edge_ids.items() if value == asset_id)
                    alternate = graph.copy()
                    alternate.remove_edge(*endpoints)
                    if nx.has_path(alternate, first, room) and nx.has_path(alternate, second, room):
                        return first, second, room, asset_id
    raise ValueError("no cross-task bottleneck pair with an alternate route")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = ["task_id", "batch_id", "site_id", "preferred_room_id", "alternate_room_id", "priority", "cable_fiber_cores", "prefer_existing_duct", "forbidden_asset_ids", "required_date", "notes"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def build(staging: Path, output: Path) -> Path:
    source_manifest = _validate_staging(staging)
    roads = _read_json(staging / "roads.geojson")
    full_graph = _road_graph(roads)
    components = sorted(nx.connected_components(full_graph), key=lambda values: (-len(values), tuple(sorted(values))))
    graph = full_graph.subgraph(components[0]).copy()
    if (full_graph.number_of_nodes(), full_graph.number_of_edges(), graph.number_of_nodes(), graph.number_of_edges()) != (629, 667, 411, 444):
        raise ValueError("audited road topology no longer matches 629/667 and largest 411/444")

    node_ids = {coordinate: f"BN-{index:04d}" for index, coordinate in enumerate(sorted(graph.nodes), start=1)}
    edge_keys = sorted(_edge_key(left, right) for left, right in graph.edges)
    edge_ids = {key: f"BC-{index:04d}" for index, key in enumerate(edge_keys, start=1)}
    for left, right in graph.edges:
        asset_id = edge_ids[_edge_key(left, right)]
        is_new_build = int(asset_id.split("-")[1]) % 11 == 0
        graph[left][right]["routing_weight"] = graph[left][right]["length_m"] * (1.25 if is_new_build else 0.90)
    rooms = _choose_rooms(graph)
    broad_candidates = _spread_nodes(graph, rooms, 80, excluded=set(rooms))
    first, second, shared_room, bottleneck = _cross_task_pair(graph, broad_candidates, rooms, edge_ids)

    leaves = [node for node in sorted(graph) if graph.degree(node) == 1 and node not in rooms and node not in {first, second}]
    if len(leaves) < 2:
        raise ValueError("largest component lacks two leaf nodes for review/failure truth cases")
    review_node, failed_node = leaves[0], leaves[-1]
    reserved_nodes = {first, second, review_node, failed_node}
    other_nodes = _spread_nodes(graph, rooms + list(reserved_nodes), 26, excluded=set(rooms) | reserved_nodes)
    access_nodes = [first, second] + other_nodes[:26] + [review_node, failed_node]
    if len(access_nodes) != 30 or len(set(access_nodes)) != 30:
        raise ValueError("failed to generate 30 unique synthetic access nodes")

    room_ids = {room: f"ROOM-{index:02d}" for index, room in enumerate(rooms, start=1)}
    site_ids = {node: f"SITE-{index:03d}" for index, node in enumerate(access_nodes, start=1)}
    task_rooms = {first: shared_room, second: shared_room}
    for index, node in enumerate(access_nodes[2:], start=2):
        task_rooms[node] = rooms[index % len(rooms)]

    excluded = {bottleneck}
    initial_full = _routable_edge(graph, access_nodes[2], task_rooms[access_nodes[2]], edge_ids, excluded)
    excluded.add(initial_full)
    global_forbidden = _routable_edge(graph, access_nodes[3], task_rooms[access_nodes[3]], edge_ids, excluded)
    excluded.add(global_forbidden)
    explicit_forbidden = _routable_edge(graph, access_nodes[4], task_rooms[access_nodes[4]], edge_ids, excluded)
    review_edge = edge_ids[_edge_key(review_node, next(iter(graph.neighbors(review_node))))]
    failed_edge = edge_ids[_edge_key(failed_node, next(iter(graph.neighbors(failed_node))))]
    if len({bottleneck, initial_full, global_forbidden, explicit_forbidden, review_edge, failed_edge}) != 6:
        raise ValueError("scenario-role resource edges must be distinct")

    node_features = [{
        "type": "Feature", "id": f"node:{node_ids[node]}",
        "properties": {"feature_type": "node", "node_id": node_ids[node], "status": "available", "data_class": "derived_from_public_road_geometry"},
        "geometry": {"type": "Point", "coordinates": list(node)},
    } for node in sorted(graph)]
    edge_features = []
    for key in edge_keys:
        left, right = key
        asset_id = edge_ids[key]
        total, used, segment_status, capacity_status, role = 32, 0, "available", "available", "ordinary"
        if asset_id == bottleneck:
            total, used, capacity_status, role = 1, 0, "near_full", "cross_task_bottleneck"
        elif asset_id == initial_full:
            total, used, capacity_status, role = 1, 1, "full", "initial_full_reroute"
        elif asset_id == global_forbidden:
            segment_status, role = "forbidden", "synthetic_forbidden_reroute"
        elif asset_id == review_edge:
            segment_status, role = "review_required", "risk_information_review"
        elif asset_id == failed_edge:
            role = "task_explicit_cut_failure"
        asset_type = "new_build" if int(asset_id.split("-")[1]) % 11 == 0 else "existing_duct"
        length = round(_distance_m(left, right), 2)
        props = {
            "feature_type": "edge", "asset_id": asset_id,
            "from_node": node_ids[left], "to_node": node_ids[right],
            "length_m": length, "asset_type": asset_type,
            "subduct_total": total, "subduct_used_baseline": used,
            "free_subduct_count": total - used, "capacity_status": capacity_status,
            "segment_status": segment_status,
            "cost_multiplier": 1.25 if asset_type == "new_build" else 0.90,
            "risk_flags": ["manual_review_required"] if segment_status == "review_required" else [],
            "scenario_role": role,
            "geometry_source": "derived_from_public_road_geometry",
            "business_attributes_source": "synthetic_competition",
            "attribution": "© OpenStreetMap contributors",
        }
        edge_features.append({"type": "Feature", "id": f"edge:{asset_id}", "properties": props, "geometry": {"type": "LineString", "coordinates": [list(left), list(right)]}})

    facilities = []
    for node, room_id in room_ids.items():
        facilities.append({"type": "Feature", "id": f"facility:{room_id}", "properties": {"site_id": room_id, "name": f"合成汇聚机房 {room_id[-2:]}", "site_type": "aggregation_room", "node_id": node_ids[node], "snap_distance_m": 0.0, "data_class": "synthetic", "source_rule": "deterministic_three_point_network_spread"}, "geometry": {"type": "Point", "coordinates": list(node)}})
    for node, site_id in site_ids.items():
        facilities.append({"type": "Feature", "id": f"facility:{site_id}", "properties": {"site_id": site_id, "name": f"合成接入设施 {site_id[-3:]}", "site_type": "access_site", "node_id": node_ids[node], "snap_distance_m": 0.0, "data_class": "synthetic", "source_rule": "fixed_seed_free_deterministic_graph_spread"}, "geometry": {"type": "Point", "coordinates": list(node)}})

    priorities = ["high"] * 10 + ["medium"] * 10 + ["low"] * 10
    fiber_cycle = [24, 48, 96, 24, 48, 144]
    rows = []
    for index, node in enumerate(access_nodes, start=1):
        forbidden = ""
        notes = "deterministic synthetic task"
        if index == 1:
            notes = "cross-task bottleneck first reservation"
        elif index == 2:
            notes = "must explain previous-task capacity conflict"
        elif index == 3:
            notes = "initial full subduct triggers bounded reroute"
        elif index == 4:
            notes = "synthetic forbidden segment triggers bounded reroute"
        elif index == 5:
            forbidden = explicit_forbidden
            notes = "task-level explicit forbidden segment"
        elif index == 29:
            notes = "risk information requires human review"
        elif index == 30:
            forbidden = failed_edge
            notes = "explicit cut leaves no feasible path"
        rows.append({
            "task_id": f"T{index:03d}", "batch_id": "BATCH-MAIN-30", "site_id": site_ids[node],
            "preferred_room_id": room_ids[task_rooms[node]], "alternate_room_id": "",
            "priority": priorities[index - 1], "cable_fiber_cores": fiber_cycle[(index - 1) % len(fiber_cycle)],
            "prefer_existing_duct": "true", "forbidden_asset_ids": forbidden,
            "required_date": "2026-09-15", "notes": notes,
        })

    output.mkdir(parents=True, exist_ok=True)
    for name in ("roads", "buildings", "water", "landuse", "railways"):
        target = output / "background" / f"{name}.geojson"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(staging / f"{name}.geojson", target)
    _write_json(output / "network.geojson", _feature_collection(node_features + edge_features))
    _write_json(output / "candidate_channels.geojson", _feature_collection(edge_features))
    _write_json(output / "facilities.geojson", _feature_collection(facilities))
    _write_csv(output / "batch_tasks.csv", rows)

    stress_rows = []
    for index in range(1, 101):
        source = dict(rows[(index - 1) % len(rows)])
        source.update(task_id=f"S{index:03d}", batch_id="BATCH-STRESS-100", forbidden_asset_ids="", notes="100-task deterministic stress input")
        stress_rows.append(source)
    _write_csv(output / "stress_tasks_100.csv", stress_rows)
    migration_rows = []
    for index, source_row in enumerate(reversed(rows[10:20]), start=1):
        source = dict(source_row)
        source.update(task_id=f"M{index:03d}", batch_id="BATCH-MIGRATION-10", forbidden_asset_ids="", notes="second contract-compatible migration set")
        migration_rows.append(source)
    _write_csv(output / "migration_tasks_10.csv", migration_rows)
    _write_json(output / "expected_coverage.json", {
        "schema_version": 1,
        "assertions": ["multiple_completed_direct", "multiple_completed_rerouted", "at_least_one_needs_review", "at_least_one_failed", "cross_task_caused_by_chain"],
        "scenario_resource_roles": {"cross_task_bottleneck": bottleneck, "initial_full": initial_full, "global_forbidden": global_forbidden, "review_required": review_edge, "explicit_failure_cut": failed_edge},
        "prohibited_answer_fields": ["expected_route_id", "expected_edge_ids", "final_route", "route_geometry"],
    })

    generated = {}
    for path in sorted(file for file in output.rglob("*") if file.is_file() and file.name not in {"manifest.json", "checksums.sha256"}):
        relative = path.relative_to(output).as_posix()
        entry = {"sha256": _sha256(path), "bytes": path.stat().st_size}
        if path.suffix == ".geojson":
            entry["feature_count"] = len(_read_json(path)["features"])
        generated[relative] = entry
    manifest = {
        "schema_version": 1,
        "dataset_id": DATASET_ID,
        "dataset_name": "上海公开 GIS 背景上的合成片区批量接入竞赛数据",
        "output_crs": "EPSG:4326",
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
        "source_dataset_id": source_manifest["dataset_id"],
        "source_license": source_manifest["data_license"],
        "required_attribution": "© OpenStreetMap contributors; ODbL 1.0",
        "topology": {"full_road_nodes": 629, "full_road_edges": 667, "largest_component_nodes": 411, "largest_component_edges": 444},
        "object_counts": {"aggregation_rooms": 3, "access_sites": 30, "main_tasks": 30, "stress_tasks": 100, "migration_tasks": 10},
        "generation_rule": "largest connected public-road component; deterministic graph-spread facilities; synthetic scenario roles selected by topology with alternate-path checks; no final route answers",
        "classification_boundary": {
            "background": "public_real_osm",
            "candidate_channel_geometry": "derived_from_public_road_geometry",
            "facilities": "synthetic",
            "subduct_status_cost_task_attributes": "synthetic_competition",
            "outputs": "derived_competition_output",
        },
        "generated_files": generated,
        "limitations": [
            "Public roads are not real telecom ducts or channels.",
            "Facilities, capacity, occupancy, status, cost and task demand are synthetic.",
            "No real operator room, duct, chamber, cable, capacity or cost data is present.",
            "Competition prototype only; not a formal construction drawing.",
        ],
    }
    _write_json(output / "manifest.json", manifest)
    files = sorted(path for path in output.rglob("*") if path.is_file() and path.name != "checksums.sha256")
    (output / "checksums.sha256").write_text("".join(f"{_sha256(path)}  {path.relative_to(output).as_posix()}\n" for path in files), encoding="ascii")
    return output / "manifest.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="构建并冻结批量接入主展示数据")
    parser.add_argument("--staging", type=Path, default=DEFAULT_STAGING)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = build(args.staging.resolve(), args.output.resolve())
    print(manifest)
    print(_sha256(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
