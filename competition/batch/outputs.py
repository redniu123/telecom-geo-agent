"""Atomic, auditable serializers for one completed batch design run."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .data_loader import BatchDataset


OUTPUT_FILENAMES = {
    "run_summary.json",
    "tasks.csv",
    "task_results.geojson",
    "candidate_routes.geojson",
    "final_routes.geojson",
    "issues.geojson",
    "resource_utilization.geojson",
    "resource_before.json",
    "resource_after.json",
    "reservations.jsonl",
    "bom_by_task.json",
    "bom_summary.json",
    "events.jsonl",
    "workflow_log.md",
    "checksums.sha256",
}


def _json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n" for value in values), encoding="utf-8")


def _feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}},
        "features": features,
    }


def _route_feature(task_result: dict[str, Any], route: dict[str, Any], stage: str) -> dict[str, Any]:
    task = task_result["task"]
    return {
        "type": "Feature",
        "id": route["route_id"],
        "properties": {
            "task_id": task["task_id"],
            "batch_id": task["batch_id"],
            "site_id": task["site_id"],
            "preferred_room_id": task["preferred_room_id"],
            "priority": task["priority"],
            "status": task_result["status"],
            "stage": stage,
            "route_id": route["route_id"],
            "edge_ids": ",".join(route["edge_ids"]),
            "total_length_m": route["total_length_m"],
            "relative_cost": route["relative_cost"],
            "repair_count": task_result["repair_count"],
            "caused_by_task_ids": ",".join(task_result["caused_by_task_ids"]),
            "data_class": "derived_competition_output",
            "disclaimer": "合成通信属性、竞赛样例、非正式施工图",
        },
        "geometry": route["geometry"],
    }


def _task_feature(result: dict[str, Any], dataset: BatchDataset) -> dict[str, Any]:
    task = result["task"]
    facility = dataset.facilities[task["site_id"]]
    bom = result.get("bom") or {}
    return {
        "type": "Feature",
        "id": f"task:{task['task_id']}",
        "properties": {
            "task_id": task["task_id"],
            "batch_id": task["batch_id"],
            "priority": task["priority"],
            "site_id": task["site_id"],
            "preferred_room_id": task["preferred_room_id"],
            "status": result["status"],
            "repair_count": result["repair_count"],
            "route_length_m": bom.get("total_length_m"),
            "cable_fiber_cores": task["cable_fiber_cores"],
            "caused_by_task_ids": ",".join(result["caused_by_task_ids"]),
            "error": result["error"],
            "data_class": "derived_competition_output",
        },
        "geometry": facility["geometry"],
    }


def _issue_features(state: dict[str, Any], dataset: BatchDataset) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str, str]] = set()
    for result in state["tasks"]:
        task_id = result["task"]["task_id"]
        for validation_index, validation in enumerate(result["validation_history"], start=1):
            for item in validation["violations"]:
                asset_id = item.get("asset_id")
                if asset_id not in dataset.network.edge_records:
                    continue
                key = (task_id, validation_index, str(item.get("rule_id")), asset_id)
                if key in seen:
                    continue
                seen.add(key)
                features.append({
                    "type": "Feature",
                    "id": ":".join(map(str, key)),
                    "properties": {
                        "task_id": task_id,
                        "status": result["status"],
                        "validation_index": validation_index,
                        "rule_id": item.get("rule_id"),
                        "issue_type": item.get("type"),
                        "asset_id": asset_id,
                        "message": item.get("message"),
                        "caused_by_task_ids": ",".join(item.get("caused_by_task_ids", [])),
                        "data_class": "derived_competition_output",
                    },
                    "geometry": dataset.network.edge_records[asset_id]["geometry"],
                })
    return features


def _resource_features(state: dict[str, Any], dataset: BatchDataset) -> list[dict[str, Any]]:
    before, after = state["resource_before"], state["resource_after"]
    features = []
    for asset_id in sorted(after):
        final = after[asset_id]
        original = before[asset_id]
        features.append({
            "type": "Feature",
            "id": f"resource:{asset_id}",
            "properties": {
                "asset_id": asset_id,
                "subduct_total": final["subduct_total"],
                "subduct_used_baseline": final["subduct_used_baseline"],
                "subduct_reserved_batch": final["subduct_reserved_batch"],
                "free_subduct_before": original["subduct_total"] - original["subduct_used_baseline"],
                "free_subduct_after": final["free_subduct_count"],
                "segment_status": final["segment_status"],
                "capacity_status": final["capacity_status"],
                "reserved_by_task_ids": ",".join(final["reserved_by_task_ids"]),
                "geometry_source": final["geometry_source"],
                "business_attributes_source": final["business_attributes_source"],
            },
            "geometry": dataset.network.edge_records[asset_id]["geometry"],
        })
    return features


def _write_normalized_tasks(path: Path, state: dict[str, Any]) -> None:
    columns = [
        "task_id", "batch_id", "site_id", "preferred_room_id", "alternate_room_id",
        "priority", "cable_fiber_cores", "prefer_existing_duct", "forbidden_asset_ids",
        "required_date", "notes", "terminal_status", "repair_count", "caused_by_task_ids",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for result in state["tasks"]:
            row = dict(result["task"])
            row["forbidden_asset_ids"] = ",".join(row["forbidden_asset_ids"])
            row.update(terminal_status=result["status"], repair_count=result["repair_count"], caused_by_task_ids=",".join(result["caused_by_task_ids"]))
            writer.writerow({key: row.get(key) for key in columns})


def refresh_checksums(destination: str | Path) -> Path:
    output = Path(destination).resolve()
    checksum = output / "checksums.sha256"
    files = sorted(path for path in output.iterdir() if path.is_file() and path.name != checksum.name)
    checksum.write_text("".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in files), encoding="ascii")
    return checksum


def write_batch_outputs(state: dict[str, Any], dataset: BatchDataset, destination: str | Path) -> list[Path]:
    if state.get("status") != "completed" or state.get("task_count") != len(state.get("tasks", [])):
        raise ValueError("只有具有完整明确终态的批次可以序列化")
    output = Path(destination).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temp_name:
        temp = Path(temp_name)
        summary = {key: state[key] for key in ("schema_version", "dataset_id", "batch_id", "parameter_fingerprint", "sorting_rule", "max_replans_per_task", "task_count", "terminal_counts", "status", "disclaimer")}
        _json(temp / "run_summary.json", summary)
        _write_normalized_tasks(temp / "tasks.csv", state)
        _json(temp / "task_results.geojson", _feature_collection([_task_feature(item, dataset) for item in state["tasks"]]))
        _json(temp / "candidate_routes.geojson", _feature_collection([_route_feature(item, item["candidate_route"], "candidate") for item in state["tasks"] if item.get("candidate_route")]))
        _json(temp / "final_routes.geojson", _feature_collection([_route_feature(item, item["final_route"], "validated_final") for item in state["tasks"] if item["status"].startswith("completed_") and item.get("final_route")]))
        _json(temp / "issues.geojson", _feature_collection(_issue_features(state, dataset)))
        _json(temp / "resource_utilization.geojson", _feature_collection(_resource_features(state, dataset)))
        _json(temp / "resource_before.json", state["resource_before"])
        _json(temp / "resource_after.json", state["resource_after"])
        _jsonl(temp / "reservations.jsonl", state["reservations"])
        bom_by_task = {item["task"]["task_id"]: item["bom"] for item in state["tasks"] if item.get("bom")}
        _json(temp / "bom_by_task.json", bom_by_task)
        _json(temp / "bom_summary.json", {
            "completed_task_count": len(bom_by_task),
            "total_route_length_m": round(sum(item["total_length_m"] for item in bom_by_task.values()), 2),
            "recommended_cable_length_m": round(sum(item["recommended_cable_length_m"] for item in bom_by_task.values()), 2),
            "by_fiber_cores": dict(sorted({str(cores): sum(1 for item in bom_by_task.values() if item["cable_fiber_cores"] == cores) for cores in {item["cable_fiber_cores"] for item in bom_by_task.values()}}.items())),
            "cost_semantics": "relative routing weight only; not currency or real construction cost",
        })
        _jsonl(temp / "events.jsonl", state["events"])
        lines = [
            "# 片区通信设施批量接入设计运行日志",
            "",
            f"- batch_id: `{state['batch_id']}`",
            f"- dataset_id: `{state['dataset_id']}`",
            f"- parameter_fingerprint: `{state['parameter_fingerprint']}`",
            f"- sorting_rule: `{state['sorting_rule']}`",
            f"- terminal_counts: `{json.dumps(state['terminal_counts'], ensure_ascii=False, sort_keys=True)}`",
            "- boundary: 真实公开 GIS 背景；候选通道身份、设施、子管资源与成本为合成竞赛属性。",
            "- output: 竞赛样例/非正式施工图，不用于施工、签章、概预算或现实资产判断。",
            "",
            "## 任务终态",
            "",
        ]
        lines.extend(f"- {item['task']['task_id']}: {item['status']} / repair_count={item['repair_count']} / caused_by={','.join(item['caused_by_task_ids']) or '-'}" for item in state["tasks"])
        (temp / "workflow_log.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        refresh_checksums(temp)
        output.mkdir(parents=True, exist_ok=True)
        produced = {path.name for path in temp.iterdir() if path.is_file()}
        for stale in sorted(OUTPUT_FILENAMES - produced):
            target = output / stale
            if target.is_file():
                target.unlink()
        for source in sorted(temp.iterdir()):
            if source.is_file():
                os.replace(source, output / source.name)
    return sorted(path for path in output.iterdir() if path.is_file() and path.name in OUTPUT_FILENAMES)
