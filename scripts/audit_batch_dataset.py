"""Independent read-only audit for the H3 batch dataset and an optional run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

import networkx as nx


SENSITIVE_KEY = re.compile(r"^(?:contact(?::.*)?|phone|email|military|aeroway|power|telecom|communication|government)$", re.I)


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_dataset(root: Path) -> dict:
    root = root.resolve()
    manifest = _json(root / "manifest.json")
    if manifest["topology"] != {"full_road_edges": 667, "full_road_nodes": 629, "largest_component_edges": 444, "largest_component_nodes": 411}:
        raise AssertionError("manifest topology contract mismatch")
    for relative, evidence in manifest["generated_files"].items():
        path = root / relative
        if not path.is_file() or _sha(path) != evidence["sha256"]:
            raise AssertionError(f"generated-file hash mismatch: {relative}")
    checksum_lines = (root / "checksums.sha256").read_text(encoding="ascii").splitlines()
    checked = {}
    for line in checksum_lines:
        digest, relative = line.split("  ", 1)
        path = root / relative
        if _sha(path) != digest:
            raise AssertionError(f"checksums.sha256 mismatch: {relative}")
        checked[relative] = digest
    if "manifest.json" not in checked:
        raise AssertionError("manifest missing from checksums.sha256")

    background_counts = {"roads": 93, "buildings": 2716, "water": 4, "landuse": 50, "railways": 10}
    for layer, count in background_counts.items():
        document = _json(root / "background" / f"{layer}.geojson")
        if len(document["features"]) != count:
            raise AssertionError(f"public background count mismatch: {layer}")
        for feature in document["features"]:
            matched = [key for key in (feature.get("properties") or {}) if SENSITIVE_KEY.match(key)]
            if matched:
                raise AssertionError(f"sensitive tag key in {layer}: {matched}")

    document = _json(root / "network.geojson")
    nodes, edges = {}, {}
    graph = nx.Graph()
    roles = set()
    for feature in document["features"]:
        props = feature["properties"]
        if props["feature_type"] == "node":
            nodes[props["node_id"]] = feature["geometry"]["coordinates"]
            graph.add_node(props["node_id"])
            if props["data_class"] != "derived_from_public_road_geometry":
                raise AssertionError("node data boundary mismatch")
        else:
            asset_id = props["asset_id"]
            if "capacity_cores" in props or "used_cores" in props:
                raise AssertionError("legacy fiber-core capacity leaked into batch resources")
            required = {"subduct_total", "subduct_used_baseline", "capacity_status", "segment_status", "geometry_source", "business_attributes_source"}
            if not required.issubset(props):
                raise AssertionError(f"separated subduct fields missing: {asset_id}")
            if props["business_attributes_source"] != "synthetic_competition" or props["geometry_source"] != "derived_from_public_road_geometry":
                raise AssertionError(f"edge data boundary mismatch: {asset_id}")
            if props["subduct_used_baseline"] > props["subduct_total"]:
                raise AssertionError(f"negative baseline free subduct: {asset_id}")
            edges[asset_id] = props
            roles.add(props["scenario_role"])
            graph.add_edge(props["from_node"], props["to_node"], asset_id=asset_id)
    if (len(nodes), len(edges), graph.number_of_edges()) != (411, 444, 444) or not nx.is_connected(graph):
        raise AssertionError("network is not the connected 411/444 contract")
    for asset_id, props in edges.items():
        coordinates = next(feature["geometry"]["coordinates"] for feature in document["features"] if feature["properties"].get("asset_id") == asset_id)
        if coordinates[0] != nodes[props["from_node"]] or coordinates[-1] != nodes[props["to_node"]]:
            raise AssertionError(f"edge endpoint geometry mismatch: {asset_id}")
    required_roles = {"cross_task_bottleneck", "initial_full_reroute", "synthetic_forbidden_reroute", "risk_information_review", "task_explicit_cut_failure"}
    if not required_roles.issubset(roles):
        raise AssertionError("required synthetic scenario roles missing")

    facilities = _json(root / "facilities.geojson")["features"]
    counts = {kind: sum(1 for item in facilities if item["properties"]["site_type"] == kind) for kind in ("aggregation_room", "access_site")}
    if counts != {"aggregation_room": 3, "access_site": 30} or any(item["properties"]["data_class"] != "synthetic" for item in facilities):
        raise AssertionError("synthetic facility contract mismatch")
    known_facilities = {item["properties"]["site_id"] for item in facilities}
    for filename, expected in (("batch_tasks.csv", 30), ("stress_tasks_100.csv", 100), ("migration_tasks_10.csv", 10)):
        with (root / filename).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            prohibited = {"expected_route_id", "expected_edge_ids", "final_route", "route_geometry"}
            if prohibited & set(reader.fieldnames or []):
                raise AssertionError(f"route answer field leaked into {filename}")
            rows = list(reader)
        if len(rows) != expected or len({row["task_id"] for row in rows}) != expected:
            raise AssertionError(f"task row/ID count mismatch: {filename}")
        if any(row["site_id"] not in known_facilities or row["preferred_room_id"] not in known_facilities for row in rows):
            raise AssertionError(f"unknown facility in {filename}")
    return {"status": "PASS", "public_background_counts": background_counts, "network_nodes": 411, "network_edges": 444, "aggregation_rooms": 3, "access_sites": 30, "main_tasks": 30, "stress_tasks": 100, "migration_tasks": 10, "legacy_capacity_fields_present": False}


def audit_run(output: Path) -> dict:
    output = output.resolve()
    summary = _json(output / "run_summary.json")
    tasks = list(csv.DictReader((output / "tasks.csv").open(encoding="utf-8-sig", newline="")))
    if len(tasks) != summary["task_count"] or any(row["terminal_status"] not in {"completed_direct", "completed_rerouted", "needs_review", "failed"} for row in tasks):
        raise AssertionError("run has missing or invalid terminal statuses")
    counts = {status: sum(row["terminal_status"] == status for row in tasks) for status in {"completed_direct", "completed_rerouted", "needs_review", "failed"}}
    if counts != summary["terminal_counts"]:
        raise AssertionError("terminal count mismatch")
    if counts["completed_direct"] < 2 or counts["completed_rerouted"] < 2 or counts["needs_review"] < 1 or counts["failed"] < 1:
        raise AssertionError("main run does not cover all required result types")
    if not any(row["caused_by_task_ids"] for row in tasks if row["terminal_status"] == "completed_rerouted"):
        raise AssertionError("cross-task conflict chain missing")
    before, after = _json(output / "resource_before.json"), _json(output / "resource_after.json")
    reservations = [json.loads(line) for line in (output / "reservations.jsonl").read_text(encoding="utf-8").splitlines()]
    for asset_id, final in after.items():
        if final["free_subduct_count"] < 0:
            raise AssertionError(f"negative resource: {asset_id}")
        delta = final["subduct_reserved_batch"] - before[asset_id]["subduct_reserved_batch"]
        events = sum(item["asset_id"] == asset_id for item in reservations)
        if delta != events:
            raise AssertionError(f"reservation conservation mismatch: {asset_id}")
    failed_ids = {row["task_id"] for row in tasks if row["terminal_status"] in {"failed", "needs_review"}}
    if any(item["task_id"] in failed_ids for item in reservations):
        raise AssertionError("failed/review task changed resources")
    return {"status": "PASS", "task_count": len(tasks), "terminal_counts": counts, "reservation_events": len(reservations), "negative_resources": 0, "failed_task_resource_side_effects": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description="独立审计批量主展示数据与运行结果")
    parser.add_argument("--dataset", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "competition_batch")
    parser.add_argument("--run-output", type=Path)
    args = parser.parse_args()
    report = {"dataset": audit_dataset(args.dataset)}
    if args.run_output:
        report["run"] = audit_run(args.run_output)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
