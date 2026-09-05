"""Turn real P0 state into ordered, QGIS-independent conversation events."""

from __future__ import annotations

from dataclasses import dataclass

from agent.state import AgentState
from telecom_core.models import NetworkData, ValidationResult


@dataclass(frozen=True)
class WorkflowEvent:
    text: str
    kind: str = "info"


def _validation_label(validation: ValidationResult) -> str:
    if validation["passed"]:
        return "PASS"
    rule_ids = "/".join(
        dict.fromkeys(str(item.get("rule_id", "UNKNOWN")) for item in validation["violations"])
    )
    return f"FAIL / {rule_ids}"


def _violation_event(
    violation: dict,
    state: AgentState,
    network: NetworkData,
) -> WorkflowEvent:
    asset_id = violation.get("asset_id")
    rule_id = violation.get("rule_id", "UNKNOWN")
    if rule_id == "R_CAPACITY" and isinstance(asset_id, str):
        edge = network.edge_records.get(asset_id)
        task = state.get("task")
        if edge is not None and task is not None:
            capacity = int(edge["capacity_cores"])
            used = int(edge["used_cores"])
            remaining = capacity - used
            requested = int(task["fiber_cores"])
            return WorkflowEvent(
                f"{asset_id} 是仓库内合成 P0 测试段，不是现实管道。"
                f"总容量 {capacity} 芯，已用 {used} 芯，剩余 {remaining} 芯，"
                f"小于本次 {requested} 芯需求。",
                "warning",
            )
    return WorkflowEvent(
        f"{rule_id} / {asset_id or '-'}：{violation.get('message', '未提供说明')}。"
        "该结论仅针对仓库内合成 P0 数据。",
        "warning",
    )


def issue_asset_ids(state: AgentState) -> tuple[str, ...]:
    """Return unique failed asset IDs in validation order."""

    values: list[str] = []
    for validation in state["validation_history"]:
        for violation in validation["violations"]:
            asset_id = violation.get("asset_id")
            if isinstance(asset_id, str) and asset_id and asset_id not in values:
                values.append(asset_id)
    return tuple(values)


def build_workflow_events(state: AgentState, network: NetworkData) -> list[WorkflowEvent]:
    """Present completed or failed state without inventing missing steps."""

    events: list[WorkflowEvent] = []
    first_route = state["first_route"]
    final_route = state["final_route"]
    history = state["validation_history"]

    if state["task"] is not None:
        task = state["task"]
        events.append(
            WorkflowEvent(
                f"任务已解析：{task['start_site_id']} → {task['end_site_id']}，"
                f"{task['fiber_cores']} 芯，已有管道偏好={task['prefer_existing_duct']}。"
            )
        )

    if first_route is not None:
        events.append(
            WorkflowEvent(
                f"第一次路线 {first_route['route_id']}："
                + " → ".join(first_route["edge_ids"]),
                "route",
            )
        )
    if history:
        first_validation = history[0]
        events.append(
            WorkflowEvent(
                "第一次校核：" + _validation_label(first_validation),
                "success" if first_validation["passed"] else "warning",
            )
        )
        if not first_validation["passed"]:
            events.extend(
                _violation_event(violation, state, network)
                for violation in first_validation["violations"]
            )

    if state["repair_count"]:
        events.append(
            WorkflowEvent(
                "自动修复：禁用问题段 "
                + "、".join(state["forbidden_asset_ids"])
                + f"；repair_count={state['repair_count']}。",
                "repair",
            )
        )

    if final_route is not None:
        if state["repair_count"]:
            events.append(
                WorkflowEvent(
                    f"重新规划 {final_route['route_id']}："
                    + " → ".join(final_route["edge_ids"]),
                    "route",
                )
            )
        elif first_route is not None and (
            final_route is first_route
            or final_route["route_id"] == first_route.get("route_id")
        ):
            events.append(
                WorkflowEvent(
                    f"第一次路线已通过，无需重规划；最终路线沿用 {final_route['route_id']}。",
                    "success",
                )
            )

    if len(history) > 1:
        final_validation = history[-1]
        events.append(
            WorkflowEvent(
                "最终校核：" + _validation_label(final_validation),
                "success" if final_validation["passed"] else "error",
            )
        )
        if not final_validation["passed"]:
            events.extend(
                _violation_event(violation, state, network)
                for violation in final_validation["violations"]
            )
    elif history and history[0]["passed"]:
        events.append(WorkflowEvent("最终校核：PASS", "success"))

    bom = state["bom_result"]
    if bom is not None:
        events.append(
            WorkflowEvent(
                "BOM（由最终路线复算）："
                f"总长 {bom['total_length_m']:.2f} m；"
                f"已有管道 {bom['existing_duct_length_m']:.2f} m；"
                f"新建 {bom['new_build_length_m']:.2f} m；"
                f"建议光缆 {bom['recommended_cable_length_m']:.2f} m；"
                "used_edge_ids=" + " → ".join(bom["used_edge_ids"]),
                "bom",
            )
        )

    if state["status"] == "failed":
        events.append(
            WorkflowEvent(
                "Workflow 明确失败；已保留完成到当前步骤的真实证据。"
                f"原因：{state['error'] or '未知错误'}",
                "error",
            )
        )
    return events
