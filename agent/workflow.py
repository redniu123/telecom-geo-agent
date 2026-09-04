"""Plain-Python bounded orchestration over the frozen telecom_core APIs."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from telecom_core.bom import calculate_bom
from telecom_core.data_loader import load_demo_network
from telecom_core.models import BOMResult, NetworkData, RouteResult, ValidationResult
from telecom_core.routing import plan_route
from telecom_core.validation import validate_route

from .parser import has_explicit_existing_duct_preference, parse_request
from .state import AgentState, new_agent_state


MAX_REPAIRS = 1

NetworkLoader = Callable[[str | Path | None, str | Path | None], NetworkData]
Planner = Callable[[Mapping[str, Any], NetworkData, Sequence[str] | None, str], RouteResult]
Validator = Callable[[RouteResult, Mapping[str, Any], Mapping[str, Any]], ValidationResult]
BOMCalculator = Callable[[RouteResult], BOMResult]


class WorkflowExecutionError(RuntimeError):
    """Raised internally when the bounded workflow cannot finish truthfully."""


def _validation_summary(validation: ValidationResult) -> str:
    if validation["passed"]:
        return "PASS"
    details = "、".join(
        f"{violation['rule_id']}/{violation['asset_id'] or '-'}（{violation['message']}）"
        for violation in validation["violations"]
    )
    return f"FAIL；{details}"


def _is_main_demo_task(task: Mapping[str, Any]) -> bool:
    return (
        task.get("task_type") == "fiber_route"
        and task.get("start_site_id") == "A"
        and task.get("end_site_id") == "B"
        and task.get("fiber_cores") == 24
        and task.get("prefer_existing_duct") is True
    )


def _has_expected_main_demo_failure(validation: ValidationResult) -> bool:
    return any(
        violation.get("rule_id") == "R_CAPACITY"
        and violation.get("asset_id") == "D017"
        and violation.get("severity") == "error"
        and violation.get("repair_hint") == "forbid_asset"
        for violation in validation["violations"]
    )


def run_workflow(
    user_request: str,
    *,
    network_path: str | Path | None = None,
    sites_path: str | Path | None = None,
    network_loader: NetworkLoader = load_demo_network,
    planner: Planner = plan_route,
    validator: Validator = validate_route,
    bom_calculator: BOMCalculator = calculate_bom,
) -> AgentState:
    """Run at most one repair and retain evidence for either success or failure."""

    state = new_agent_state(user_request)
    try:
        state["execution_log"].append("读取并校验 Demo 网络与站点数据")
        network = network_loader(network_path, sites_path)

        task = parse_request(user_request, network.sites)
        state["task"] = task
        preference_source = (
            "用户显式指定"
            if has_explicit_existing_duct_preference(user_request)
            else "未写明，使用 P0 默认值 True"
        )
        state["execution_log"].append(
            "任务解析："
            f"{task['start_site_id']} 到 {task['end_site_id']}，"
            f"{task['fiber_cores']} 芯；已有管道偏好：{preference_source}"
        )

        first_route = planner(task, network, [], "R001")
        state["first_route"] = first_route
        state["execution_log"].append(
            f"第一次路线 R001：edge_ids={first_route['edge_ids']}"
        )

        first_validation = validator(first_route, task, network.edge_records)
        state["validation_history"].append(first_validation)
        state["execution_log"].append(
            f"第一次校核：{_validation_summary(first_validation)}"
        )

        if _is_main_demo_task(task):
            if "D017" not in first_route["edge_ids"]:
                raise WorkflowExecutionError("主 Demo 第一次路线未经过 D017")
            if not _has_expected_main_demo_failure(first_validation):
                raise WorkflowExecutionError(
                    "主 Demo 第一次校核未返回 R_CAPACITY/D017，拒绝伪造修复演示"
                )

        if first_validation["passed"]:
            state["final_route"] = first_route
            state["bom_result"] = bom_calculator(first_route)
            state["execution_log"].append("第一次校核通过，无需自动修复")
        else:
            repairable_assets: list[str] = []
            unrepairable_errors: list[str] = []
            for violation in first_validation["violations"]:
                is_repairable = (
                    violation.get("severity") == "error"
                    and violation.get("repair_hint") == "forbid_asset"
                    and isinstance(violation.get("asset_id"), str)
                    and bool(violation["asset_id"])
                )
                if is_repairable:
                    asset_id = violation["asset_id"]
                    if asset_id not in repairable_assets:
                        repairable_assets.append(asset_id)
                elif violation.get("severity") == "error":
                    unrepairable_errors.append(str(violation.get("rule_id", "UNKNOWN")))

            if unrepairable_errors:
                raise WorkflowExecutionError(
                    "第一次校核包含不可自动修复错误：" + "、".join(unrepairable_errors)
                )
            if not repairable_assets:
                raise WorkflowExecutionError("第一次校核失败，但没有可执行的 forbid_asset 修复提示")
            if state["repair_count"] >= MAX_REPAIRS:
                raise WorkflowExecutionError("已达到最大重新规划次数 1")

            state["forbidden_asset_ids"].extend(repairable_assets)
            state["repair_count"] += 1
            state["execution_log"].append(
                "自动修复：forbid "
                + "、".join(repairable_assets)
                + f"；repair_count={state['repair_count']}"
            )

            final_route = planner(
                task,
                network,
                state["forbidden_asset_ids"],
                "R002",
            )
            state["final_route"] = final_route
            state["execution_log"].append(
                f"第二次路线 R002：edge_ids={final_route['edge_ids']}"
            )
            reused_forbidden = sorted(
                set(final_route["edge_ids"]) & set(state["forbidden_asset_ids"])
            )
            if reused_forbidden:
                raise WorkflowExecutionError(
                    "第二次路线仍使用已禁用资产：" + "、".join(reused_forbidden)
                )

            final_validation = validator(final_route, task, network.edge_records)
            state["validation_history"].append(final_validation)
            state["execution_log"].append(
                f"第二次校核：{_validation_summary(final_validation)}"
            )
            if not final_validation["passed"]:
                raise WorkflowExecutionError("自动修复后第二次校核仍失败")
            state["bom_result"] = bom_calculator(final_route)

        bom = state["bom_result"]
        if bom is None:
            raise WorkflowExecutionError("校核通过后未生成 BOM")
        state["execution_log"].append(
            "BOM 生成："
            f"总长 {bom['total_length_m']:.2f} m，"
            f"已有管道 {bom['existing_duct_length_m']:.2f} m，"
            f"新建 {bom['new_build_length_m']:.2f} m，"
            f"建议光缆 {bom['recommended_cable_length_m']:.2f} m"
        )
        state["status"] = "completed"
        state["execution_log"].append("Workflow 完成：最终校核 PASS")
    except Exception as exc:  # State is the public failure channel for the CLI.
        state["status"] = "failed"
        state["error"] = f"{type(exc).__name__}: {exc}"
        state["execution_log"].append(f"执行失败：{state['error']}")
    return state
