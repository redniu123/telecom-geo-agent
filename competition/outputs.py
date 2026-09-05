"""Auditable competition output serialization."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from telecom_core.models import NetworkData


KNOWN_OUTPUTS = {
    "candidate_route.geojson",
    "final_route.geojson",
    "issues.geojson",
    "validation_report.json",
    "bom.json",
    "events.jsonl",
    "run_summary.json",
    "workflow_log.md",
}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _route_collection(route: dict[str, Any], stage: str, scenario_id: str) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::4326"},
        },
        "features": [
            {
                "type": "Feature",
                "id": route["route_id"],
                "properties": {
                    "route_id": route["route_id"],
                    "stage": stage,
                    "scenario_id": scenario_id,
                    "edge_ids": route["edge_ids"],
                    "total_length_m": route["total_length_m"],
                    "relative_cost": route["relative_cost"],
                    "data_class": "derived_competition_output",
                    "disclaimer": "竞赛样例/非正式施工图",
                },
                "geometry": route["geometry"],
            }
        ],
    }


def _issues_collection(state: dict[str, Any], network: NetworkData) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for validation_index, validation in enumerate(state["validation_history"], start=1):
        for violation in validation["violations"]:
            asset_id = violation.get("asset_id")
            if not isinstance(asset_id, str) or asset_id not in network.edge_records:
                continue
            unique = (str(violation.get("rule_id")), asset_id)
            if unique in seen:
                continue
            seen.add(unique)
            edge = network.edge_records[asset_id]
            issues.append(
                {
                    "type": "Feature",
                    "id": f"issue:{unique[0]}:{asset_id}",
                    "properties": {
                        "scenario_id": state["scenario_id"],
                        "validation_index": validation_index,
                        "rule_id": violation.get("rule_id"),
                        "issue_type": violation.get("type"),
                        "asset_id": asset_id,
                        "severity": violation.get("severity"),
                        "message": violation.get("message"),
                        "data_class": "derived_competition_output",
                    },
                    "geometry": edge["geometry"],
                }
            )
    return {"type": "FeatureCollection", "features": issues}


def write_workflow_outputs(
    state: dict[str, Any], network: NetworkData, destination: str | Path
) -> list[Path]:
    output_dir = Path(destination).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in KNOWN_OUTPUTS:
        target = output_dir / filename
        if target.is_file():
            target.unlink()

    written: list[Path] = []
    candidate = state.get("candidate_route")
    if candidate:
        path = output_dir / "candidate_route.geojson"
        _write_json(path, _route_collection(candidate, "constraint_free_candidate", state["scenario_id"]))
        written.append(path)
    final = state.get("final_route")
    if final and state["status"] == "completed":
        path = output_dir / "final_route.geojson"
        _write_json(path, _route_collection(final, "validated_final", state["scenario_id"]))
        written.append(path)

    issues_path = output_dir / "issues.geojson"
    _write_json(issues_path, _issues_collection(state, network))
    written.append(issues_path)

    report_path = output_dir / "validation_report.json"
    _write_json(
        report_path,
        {
            "status": state["status"],
            "scenario_id": state["scenario_id"],
            "parameter_fingerprint": state["parameter_fingerprint"],
            "validation_history": state["validation_history"],
            "forbidden_asset_ids_applied": state["forbidden_asset_ids_applied"],
            "repair_count": state["repair_count"],
            "error": state["error"],
        },
    )
    written.append(report_path)

    if state.get("bom_result") is not None:
        bom_path = output_dir / "bom.json"
        _write_json(bom_path, state["bom_result"])
        written.append(bom_path)

    events_path = output_dir / "events.jsonl"
    events_path.write_text(
        "".join(
            json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
            for event in state["events"]
        ),
        encoding="utf-8",
    )
    written.append(events_path)

    log_path = output_dir / "workflow_log.md"
    log_lines = [
        f"# {state['scenario_id']} 工作流证据",
        "",
        "数据边界：公开 OSM 背景 + 派生候选几何 + 合成通信属性。",
        "成果声明：竞赛样例 / 非正式施工图。",
        "",
    ]
    log_lines.extend(
        f"{event['sequence']}. [{event['elapsed_ms']:.3f} ms] {event['message']}"
        for event in state["events"]
    )
    log_lines.extend(["", f"最终状态：{state['status']}"])
    if state["error"]:
        log_lines.append(f"失败原因：{state['error']}")
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    written.append(log_path)

    hashes = {path.name: _sha256(path) for path in sorted(written)}
    summary_path = output_dir / "run_summary.json"
    _write_json(
        summary_path,
        {
            "schema_version": 1,
            "dataset_id": state["dataset_id"],
            "scenario_id": state["scenario_id"],
            "status": state["status"],
            "parameters": state["parameters"],
            "parameter_fingerprint": state["parameter_fingerprint"],
            "system_elapsed_ms": state["system_elapsed_ms"],
            "candidate_edge_ids": candidate["edge_ids"] if candidate else [],
            "final_edge_ids": final["edge_ids"] if final and state["status"] == "completed" else [],
            "repair_count": state["repair_count"],
            "output_sha256": hashes,
            "data_boundary": "public_real_background + derived_geometry + synthetic_telecom_attributes",
            "disclaimer": "竞赛样例/非正式施工图",
        },
    )
    written.append(summary_path)
    return written
