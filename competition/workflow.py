"""Deterministic competition workflow using the canonical P0 core."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from telecom_core.bom import calculate_bom
from telecom_core.models import NetworkData, ValidationResult
from telecom_core.routing import plan_route
from telecom_core.validation import validate_route

from .catalog import load_competition_network
from .schema import DesignParameters


WorkflowState = dict[str, Any]
Clock = Callable[[], int]


def _new_state(parameters: DesignParameters) -> WorkflowState:
    return {
        "schema_version": 1,
        "dataset_id": parameters.dataset_id,
        "scenario_id": parameters.scenario_id,
        "parameters": parameters.as_dict(),
        "parameter_fingerprint": parameters.fingerprint,
        "candidate_route": None,
        "final_route": None,
        "validation_history": [],
        "forbidden_asset_ids_applied": [],
        "repair_count": 0,
        "bom_result": None,
        "events": [],
        "status": "pending",
        "error": None,
    }


def _task(parameters: DesignParameters) -> dict[str, Any]:
    return {
        "task_type": "fiber_route",
        "start_site_id": parameters.start_site_id,
        "end_site_id": parameters.end_site_id,
        "fiber_cores": parameters.fiber_cores,
        "prefer_existing_duct": parameters.prefer_existing_duct,
    }


def _network_for_preference(
    network: NetworkData, parameters: DesignParameters
) -> NetworkData:
    """Apply the competition preference without changing the frozen P0 core.

    The audited dataset's cost multipliers encode a preference for existing
    ducts.  When the user clears that preference, routing must be based on
    geometric length alone, so every eligible edge receives multiplier 1.0.
    Other validated attributes remain byte-for-byte equivalent values.
    """

    if parameters.prefer_existing_duct:
        return network
    edge_records = {
        edge_id: {**edge, "cost_multiplier": 1.0}
        for edge_id, edge in network.edge_records.items()
    }
    return NetworkData(
        graph=network.graph,
        nodes=network.nodes,
        edge_records=edge_records,
        sites=network.sites,
    )


def _record(
    state: WorkflowState,
    clock: Clock,
    started_ns: int,
    event_type: str,
    message: str,
    **details: Any,
) -> None:
    state["events"].append(
        {
            "sequence": len(state["events"]) + 1,
            "elapsed_ms": round((clock() - started_ns) / 1_000_000, 3),
            "event_type": event_type,
            "message": message,
            "details": details,
        }
    )


def _with_user_forbidden(
    validation: ValidationResult,
    route: dict[str, Any],
    forbidden_asset_ids: tuple[str, ...],
) -> ValidationResult:
    violations = list(validation["violations"])
    route_edges = set(route["edge_ids"])
    for asset_id in forbidden_asset_ids:
        if asset_id in route_edges:
            violations.append(
                {
                    "rule_id": "R_USER_FORBIDDEN",
                    "type": "explicit_forbidden_asset",
                    "asset_id": asset_id,
                    "severity": "error",
                    "message": f"约束前候选路线命中显式禁用资产 {asset_id}",
                    "repair_hint": "forbid_asset",
                }
            )
    return {"passed": not violations, "violations": violations}


def _issue_assets(validation: ValidationResult) -> list[str]:
    values: list[str] = []
    for violation in validation["violations"]:
        asset_id = violation.get("asset_id")
        if isinstance(asset_id, str) and asset_id and asset_id not in values:
            values.append(asset_id)
    return values


def run_design_workflow(
    parameters: DesignParameters,
    repository_root: str | Path,
    *,
    confirmed_fingerprint: str | None,
    network_loader: Callable[[str | Path], NetworkData] = load_competition_network,
    clock: Clock = time.perf_counter_ns,
) -> WorkflowState:
    """Run a confirmed request with one bounded explainable repair."""

    parameters.assert_confirmation(confirmed_fingerprint)
    state = _new_state(parameters)
    started_ns = clock()
    task = _task(parameters)
    try:
        _record(state, clock, started_ns, "parameters_confirmed", "结构化参数指纹已确认")
        source_network = network_loader(repository_root)
        network = _network_for_preference(source_network, parameters)
        _record(
            state,
            clock,
            started_ns,
            "dataset_loaded",
            "竞赛数据集已加载",
            nodes=len(network.nodes),
            candidate_channels=len(network.edge_records),
            sites=len(network.sites),
            routing_weight_mode=(
                "length_times_cost_multiplier"
                if parameters.prefer_existing_duct
                else "length_only"
            ),
        )

        candidate = plan_route(task, network, [], "COMP-CANDIDATE")
        state["candidate_route"] = candidate
        _record(
            state,
            clock,
            started_ns,
            "candidate_planned",
            "已生成约束前候选路线（不代表可施工）",
            edge_ids=candidate["edge_ids"],
            total_length_m=candidate["total_length_m"],
        )

        candidate_validation = _with_user_forbidden(
            validate_route(candidate, task, network.edge_records),
            candidate,
            parameters.forbidden_asset_ids,
        )
        state["validation_history"].append(candidate_validation)
        _record(
            state,
            clock,
            started_ns,
            "candidate_validated",
            "约束前候选路线校核完成",
            passed=candidate_validation["passed"],
            issue_asset_ids=_issue_assets(candidate_validation),
        )

        if candidate_validation["passed"]:
            state["final_route"] = candidate
            final_validation = candidate_validation
        else:
            unrepairable = [
                item
                for item in candidate_validation["violations"]
                if item.get("severity") == "error"
                and (
                    item.get("repair_hint") != "forbid_asset"
                    or not item.get("asset_id")
                )
            ]
            if unrepairable:
                raise RuntimeError(
                    "候选路线存在不可自动修复错误："
                    + "、".join(str(item.get("rule_id")) for item in unrepairable)
                )
            applied = sorted(
                set(parameters.forbidden_asset_ids)
                | set(_issue_assets(candidate_validation))
            )
            if not applied:
                raise RuntimeError("候选路线失败但没有可执行的禁用资产")
            state["forbidden_asset_ids_applied"] = applied
            state["repair_count"] = 1
            _record(
                state,
                clock,
                started_ns,
                "repair_applied",
                "一次有界修复：禁用问题/显式禁用资产并重规划",
                forbidden_asset_ids=applied,
            )
            final = plan_route(task, network, applied, "COMP-FINAL")
            state["final_route"] = final
            if set(final["edge_ids"]) & set(applied):
                raise RuntimeError("最终路线仍复用已禁用资产")
            _record(
                state,
                clock,
                started_ns,
                "final_planned",
                "已生成重规划路线",
                edge_ids=final["edge_ids"],
                total_length_m=final["total_length_m"],
            )
            final_validation = validate_route(final, task, network.edge_records)
            state["validation_history"].append(final_validation)

        if not final_validation["passed"]:
            raise RuntimeError("最终路线独立校核未通过")
        _record(
            state,
            clock,
            started_ns,
            "final_validated",
            "最终路线独立校核 PASS",
            passed=True,
        )
        state["bom_result"] = calculate_bom(state["final_route"])
        _record(
            state,
            clock,
            started_ns,
            "bom_calculated",
            "BOM 已由最终路线段复算",
            total_length_m=state["bom_result"]["total_length_m"],
            recommended_cable_length_m=state["bom_result"]["recommended_cable_length_m"],
        )
        state["status"] = "completed"
        _record(state, clock, started_ns, "workflow_completed", "竞赛工作流完成")
    except Exception as exc:
        state["status"] = "failed"
        state["error"] = f"{type(exc).__name__}: {exc}"
        _record(
            state,
            clock,
            started_ns,
            "workflow_failed",
            "工作流明确失败；未伪造最终 PASS 或 BOM",
            error=state["error"],
        )
    state["system_elapsed_ms"] = round((clock() - started_ns) / 1_000_000, 3)
    return state
