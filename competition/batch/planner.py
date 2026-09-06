"""Fixed-order batch planner with one bounded reroute and no task preemption."""

from __future__ import annotations

from collections import Counter
from typing import Any

from telecom_core.bom import calculate_bom
from telecom_core.routing import plan_route

from .data_loader import BatchDataset
from .resource_ledger import ResourceLedger
from .schema import BatchRequest, BatchTask


TERMINAL_STATUSES = {"completed_direct", "completed_rerouted", "needs_review", "failed"}


def _route_task(task: BatchTask) -> dict[str, Any]:
    return {
        "task_type": "fiber_route",
        "start_site_id": task.site_id,
        "end_site_id": task.preferred_room_id,
        # Route calculation does not interpret this as subduct usage. It remains
        # the cable specification and is copied into BOM/output metadata.
        "fiber_cores": task.cable_fiber_cores,
        "prefer_existing_duct": task.prefer_existing_duct,
    }


def _network_for_preference(dataset: BatchDataset, task: BatchTask):
    if task.prefer_existing_duct:
        return dataset.network
    from telecom_core.models import NetworkData

    records = {key: {**value, "cost_multiplier": 1.0} for key, value in dataset.network.edge_records.items()}
    return NetworkData(graph=dataset.network.graph, nodes=dataset.network.nodes, edge_records=records, sites=dataset.network.sites)


def _event(events: list[dict[str, Any]], event_type: str, task_id: str | None, **details: Any) -> None:
    events.append({"sequence": len(events) + 1, "event_type": event_type, "task_id": task_id, "details": details})


def _result_shell(task: BatchTask) -> dict[str, Any]:
    return {
        "task": task.as_dict(),
        "status": None,
        "candidate_route": None,
        "final_route": None,
        "validation_history": [],
        "repair_count": 0,
        "temporary_forbidden_asset_ids": [],
        "caused_by_task_ids": [],
        "resource_changes": [],
        "bom": None,
        "error": None,
    }


def _causes(validation: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for violation in validation["violations"]:
        for task_id in violation.get("caused_by_task_ids", []):
            if task_id not in values:
                values.append(task_id)
    return sorted(values)


def _finish_pass(result: dict[str, Any], ledger: ResourceLedger, events: list[dict[str, Any]], rerouted: bool) -> None:
    task_id = result["task"]["task_id"]
    route = result["final_route"]
    result["resource_changes"] = ledger.commit(task_id, route["edge_ids"])
    result["bom"] = {
        **calculate_bom(route),
        "cable_fiber_cores": result["task"]["cable_fiber_cores"],
        "subducts_reserved_per_segment": 1,
    }
    result["status"] = "completed_rerouted" if rerouted else "completed_direct"
    _event(events, "resource_committed", task_id, changes=result["resource_changes"])
    _event(events, "task_completed", task_id, status=result["status"], route_id=route["route_id"])


def run_batch(request: BatchRequest, dataset: BatchDataset, *, confirmed_fingerprint: str | None) -> dict[str, Any]:
    request.assert_confirmation(confirmed_fingerprint)
    if request.dataset_id != dataset.dataset_id:
        raise ValueError(f"批次数据集不匹配：{request.dataset_id!r} != {dataset.dataset_id!r}")
    ledger = ResourceLedger(dataset.resources)
    events: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    _event(events, "batch_started", None, batch_id=request.batch_id, fingerprint=request.fingerprint, sorting_rule=request.sorting_rule)

    for task in request.ordered_tasks:
        result = _result_shell(task)
        results.append(result)
        network = _network_for_preference(dataset, task)
        route_task = _route_task(task)
        _event(events, "task_started", task.task_id, priority=task.priority)
        try:
            candidate = plan_route(route_task, network, [], f"{task.task_id}-CANDIDATE")
        except Exception as exc:
            result["status"] = "failed"
            result["error"] = f"{type(exc).__name__}: {exc}"
            _event(events, "task_failed", task.task_id, error=result["error"], resource_side_effect=False)
            continue
        result["candidate_route"] = candidate
        candidate_validation = ledger.validate_route(candidate["edge_ids"], explicit_forbidden=task.forbidden_asset_ids)
        result["validation_history"].append(candidate_validation)
        result["caused_by_task_ids"] = _causes(candidate_validation)
        _event(events, "candidate_validated", task.task_id, passed=candidate_validation["passed"], violations=candidate_validation["violations"])
        if candidate_validation["passed"]:
            result["final_route"] = candidate
            _finish_pass(result, ledger, events, False)
            continue

        repairable = all(item.get("repair_hint") == "forbid_asset" and item.get("asset_id") for item in candidate_validation["violations"])
        if not repairable:
            result["status"] = "needs_review"
            result["error"] = "候选路线含不可自动裁决的待复核风险"
            _event(events, "task_needs_review", task.task_id, resource_side_effect=False)
            continue

        temporary_forbidden = sorted(set(task.forbidden_asset_ids) | {str(item["asset_id"]) for item in candidate_validation["violations"]})
        result["repair_count"] = 1
        result["temporary_forbidden_asset_ids"] = temporary_forbidden
        _event(events, "bounded_reroute_started", task.task_id, forbidden_asset_ids=temporary_forbidden, attempt=1, maximum=1)
        try:
            final = plan_route(route_task, network, temporary_forbidden, f"{task.task_id}-FINAL")
        except Exception as exc:
            result["status"] = "failed"
            result["error"] = f"{type(exc).__name__}: {exc}"
            _event(events, "task_failed", task.task_id, error=result["error"], resource_side_effect=False, repair_count=1)
            continue
        result["final_route"] = final
        final_validation = ledger.validate_route(final["edge_ids"], explicit_forbidden=task.forbidden_asset_ids)
        result["validation_history"].append(final_validation)
        _event(events, "final_validated", task.task_id, passed=final_validation["passed"], violations=final_validation["violations"])
        if final_validation["passed"]:
            _finish_pass(result, ledger, events, True)
        else:
            result["status"] = "needs_review"
            result["error"] = "一次有界改路后仍未通过；未继续自动尝试"
            result["caused_by_task_ids"] = sorted(set(result["caused_by_task_ids"]) | set(_causes(final_validation)))
            _event(events, "task_needs_review", task.task_id, resource_side_effect=False, repair_count=1)

    ledger.assert_conservation()
    if any(result["status"] not in TERMINAL_STATUSES for result in results):
        raise RuntimeError("批次存在悬空状态")
    counts = Counter(result["status"] for result in results)
    _event(events, "batch_completed", None, terminal_counts=dict(sorted(counts.items())))
    return {
        "schema_version": 1,
        "dataset_id": dataset.dataset_id,
        "batch_id": request.batch_id,
        "parameter_fingerprint": request.fingerprint,
        "sorting_rule": request.sorting_rule,
        "max_replans_per_task": 1,
        "task_count": len(results),
        "terminal_counts": {key: counts.get(key, 0) for key in sorted(TERMINAL_STATUSES)},
        "status": "completed",
        "tasks": results,
        "resource_before": ledger.baseline_snapshot(),
        "resource_after": ledger.snapshot(),
        "reservations": ledger.reservations,
        "events": events,
        "disclaimer": "真实公开 GIS 背景；通信设施、候选通道身份、子管资源和成本均为合成竞赛属性；非正式施工图。",
    }
