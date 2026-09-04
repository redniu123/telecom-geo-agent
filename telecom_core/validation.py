"""Independent deterministic route validation for the three P0 rules."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import EdgeRecord, RouteResult, TelecomTask, ValidationResult, ValidationViolation


def _violation(
    rule_id: str,
    violation_type: str,
    asset_id: str | None,
    message: str,
    repair_hint: str | None,
) -> ValidationViolation:
    return {
        "rule_id": rule_id,
        "type": violation_type,
        "asset_id": asset_id,
        "severity": "error",
        "message": message,
        "repair_hint": repair_hint,
    }


def validate_route(
    route: RouteResult,
    task: TelecomTask | Mapping[str, Any],
    edge_records: Mapping[str, EdgeRecord],
) -> ValidationResult:
    """Validate endpoints, asset status, and existing-duct capacity."""

    violations: list[ValidationViolation] = []
    segments = route.get("segments", [])
    endpoint_ok = (
        route.get("success") is True
        and route.get("start_site_id") == task.get("start_site_id")
        and route.get("end_site_id") == task.get("end_site_id")
        and bool(segments)
        and all(
            segments[index - 1]["to_node"] == segments[index]["from_node"]
            for index in range(1, len(segments))
        )
    )
    if not endpoint_ok:
        violations.append(
            _violation(
                "R_ENDPOINT",
                "route_endpoint",
                None,
                "路线未从任务起点连续到达任务终点",
                None,
            )
        )

    route_edge_ids = route.get("edge_ids", [])
    segment_edge_ids = [segment.get("edge_id") for segment in segments]
    if route_edge_ids != segment_edge_ids:
        raise ValueError("route edge_ids must exactly match segment edge_id order")

    requested_cores = task.get("fiber_cores")
    if isinstance(requested_cores, bool) or not isinstance(requested_cores, int) or requested_cores <= 0:
        raise ValueError("TelecomTask fiber_cores must be a positive integer")

    for segment in segments:
        edge_id = segment["edge_id"]
        if edge_id not in edge_records:
            raise ValueError(f"route references unknown edge {edge_id!r}")
        edge = edge_records[edge_id]
        if edge["status"] == "unavailable":
            violations.append(
                _violation(
                    "R_ASSET_STATUS",
                    "asset_status",
                    edge_id,
                    f"{edge_id} 状态不可用",
                    "forbid_asset",
                )
            )
        if edge["asset_type"] == "existing_duct":
            remaining = edge["capacity_cores"] - edge["used_cores"]
            if remaining < requested_cores:
                violations.append(
                    _violation(
                        "R_CAPACITY",
                        "duct_capacity",
                        edge_id,
                        f"{edge_id} 剩余容量不足以承载 {requested_cores} 芯光缆",
                        "forbid_asset",
                    )
                )
    return {"passed": not violations, "violations": violations}
