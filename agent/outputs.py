"""Stable UTF-8 output serialization for the five P0 artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from telecom_core.models import RouteResult

from .state import AgentState


OUTPUT_FILENAMES = (
    "first_route.geojson",
    "final_route.geojson",
    "validation_report.json",
    "bom.json",
    "agent_log.md",
)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _route_feature_collection(route: RouteResult, stage: str) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": route["route_id"],
                "properties": {
                    "route_id": route["route_id"],
                    "stage": stage,
                    "edge_ids": route["edge_ids"],
                    "total_length_m": route["total_length_m"],
                    "relative_cost": route["relative_cost"],
                    "forbidden_asset_ids_applied": route[
                        "forbidden_asset_ids_applied"
                    ],
                },
                "geometry": route["geometry"],
            }
        ],
    }


def _validation_report(state: AgentState) -> dict[str, Any]:
    return {
        "status": state["status"],
        "validation_history": state["validation_history"],
        "forbidden_asset_ids": state["forbidden_asset_ids"],
        "repair_count": state["repair_count"],
        "error": state["error"],
    }


def _agent_log(state: AgentState) -> str:
    lines = ["# TelecomGeoAgent P0 执行日志", ""]
    lines.extend(
        f"{index}. {entry}" for index, entry in enumerate(state["execution_log"], start=1)
    )
    lines.extend(["", f"最终状态：{state['status']}"])
    if state["error"]:
        lines.append(f"失败原因：{state['error']}")
    return "\n".join(lines) + "\n"


def write_outputs(state: AgentState, output_dir: str | Path = "outputs") -> list[Path]:
    """Overwrite only the five known output names and return files actually written."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    output_names = {
        "validation_report.json",
        "agent_log.md",
    }
    if state["first_route"] is not None:
        output_names.add("first_route.geojson")
    if state["final_route"] is not None:
        output_names.add("final_route.geojson")
    if state["bom_result"] is not None:
        output_names.add("bom.json")

    for filename in set(OUTPUT_FILENAMES) - output_names:
        target = destination / filename
        if target.is_file():
            target.unlink()

    written: list[Path] = []
    if state["first_route"] is not None:
        target = destination / "first_route.geojson"
        _write_json(target, _route_feature_collection(state["first_route"], "first"))
        written.append(target)
    if state["final_route"] is not None:
        target = destination / "final_route.geojson"
        _write_json(target, _route_feature_collection(state["final_route"], "final"))
        written.append(target)

    validation_target = destination / "validation_report.json"
    _write_json(validation_target, _validation_report(state))
    written.append(validation_target)

    if state["bom_result"] is not None:
        bom_target = destination / "bom.json"
        _write_json(bom_target, state["bom_result"])
        written.append(bom_target)

    log_target = destination / "agent_log.md"
    log_target.write_text(_agent_log(state), encoding="utf-8")
    written.append(log_target)
    return written
