"""In-memory baseline resource ledger with atomic final-PASS reservations."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from typing import Any


class LedgerError(ValueError):
    """Raised before any partial resource mutation is allowed."""


class ResourceLedger:
    def __init__(self, baseline_records: Mapping[str, dict[str, Any]]) -> None:
        self._baseline = copy.deepcopy(dict(baseline_records))
        self._working = copy.deepcopy(dict(baseline_records))
        self._reservations: list[dict[str, Any]] = []
        self._reserved_by: dict[str, list[str]] = {asset_id: [] for asset_id in baseline_records}
        self._committed_tasks: set[str] = set()
        self._validate_snapshot(self._baseline)

    @staticmethod
    def _validate_snapshot(records: Mapping[str, dict[str, Any]]) -> None:
        if not records:
            raise LedgerError("资源台账不能为空")
        for asset_id, record in records.items():
            if record.get("asset_id") != asset_id:
                raise LedgerError(f"资源键与 asset_id 不一致：{asset_id}")
            total = record.get("subduct_total")
            used = record.get("subduct_used_baseline")
            reserved = record.get("subduct_reserved_batch", 0)
            if any(isinstance(value, bool) or not isinstance(value, int) for value in (total, used, reserved)):
                raise LedgerError(f"{asset_id}: 子管字段必须是整数")
            if total < 0 or used < 0 or reserved < 0 or used + reserved > total:
                raise LedgerError(f"{asset_id}: 子管资源不守恒")
            if record.get("segment_status") not in {"available", "forbidden", "review_required"}:
                raise LedgerError(f"{asset_id}: 非法 segment_status")

    @staticmethod
    def _free(record: Mapping[str, Any]) -> int:
        return int(record["subduct_total"]) - int(record["subduct_used_baseline"]) - int(record["subduct_reserved_batch"])

    def baseline_snapshot(self) -> dict[str, dict[str, Any]]:
        return copy.deepcopy(self._baseline)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        result = copy.deepcopy(self._working)
        for asset_id, record in result.items():
            record["free_subduct_count"] = self._free(record)
            record["reserved_by_task_ids"] = list(self._reserved_by[asset_id])
        return {key: result[key] for key in sorted(result)}

    @property
    def reservations(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._reservations)

    def validate_route(
        self,
        edge_ids: Iterable[str],
        *,
        explicit_forbidden: Iterable[str] = (),
    ) -> dict[str, Any]:
        forbidden = set(explicit_forbidden)
        violations: list[dict[str, Any]] = []
        for asset_id in dict.fromkeys(edge_ids):
            if asset_id not in self._working:
                raise LedgerError(f"路线引用未知候选通道：{asset_id}")
            record = self._working[asset_id]
            if asset_id in forbidden:
                violations.append(self._violation("R_TASK_FORBIDDEN", "explicit_forbidden_asset", asset_id, "任务显式禁用候选通道", True))
            if record["segment_status"] == "forbidden":
                violations.append(self._violation("R_SEGMENT_STATUS", "segment_forbidden", asset_id, "合成资源台账标记为禁用", True))
            elif record["segment_status"] == "review_required":
                violations.append(self._violation("R_REVIEW_REQUIRED", "insufficient_risk_information", asset_id, "空间风险信息不足，必须人工复核", False))
            if self._free(record) < 1:
                violation = self._violation("R_SUBDUCT_CAPACITY", "subduct_capacity", asset_id, "剩余合成子管不足 1 个", True)
                violation["caused_by_task_ids"] = list(self._reserved_by[asset_id])
                violation["free_subduct_count"] = self._free(record)
                violations.append(violation)
        return {"passed": not violations, "violations": violations}

    @staticmethod
    def _violation(rule_id: str, kind: str, asset_id: str, message: str, repairable: bool) -> dict[str, Any]:
        return {
            "rule_id": rule_id,
            "type": kind,
            "asset_id": asset_id,
            "severity": "error",
            "message": message,
            "repair_hint": "forbid_asset" if repairable else None,
        }

    def commit(self, task_id: str, edge_ids: Iterable[str]) -> list[dict[str, Any]]:
        if task_id in self._committed_tasks:
            raise LedgerError(f"任务不得重复提交资源：{task_id}")
        assets = list(dict.fromkeys(edge_ids))
        if not assets:
            raise LedgerError("最终 PASS 路线不能为空")
        changes: list[dict[str, Any]] = []
        for asset_id in assets:
            if asset_id not in self._working:
                raise LedgerError(f"提交引用未知候选通道：{asset_id}")
            record = self._working[asset_id]
            if record["segment_status"] != "available" or self._free(record) < 1:
                raise LedgerError(f"提交前资源已不可用：{asset_id}")
            before = self._free(record)
            changes.append({
                "task_id": task_id,
                "asset_id": asset_id,
                "free_subduct_before": before,
                "free_subduct_after": before - 1,
                "reserved_delta": 1,
            })
        # All checks above complete before the first mutation: this is the
        # single-process atomic commit boundary required by the master plan.
        for change in changes:
            asset_id = change["asset_id"]
            self._working[asset_id]["subduct_reserved_batch"] += 1
            self._reserved_by[asset_id].append(task_id)
            self._reservations.append(dict(change, sequence=len(self._reservations) + 1))
        self._committed_tasks.add(task_id)
        return changes

    def assert_conservation(self) -> None:
        self._validate_snapshot(self._working)
        expected = sum(record["subduct_reserved_batch"] for record in self._working.values())
        if expected != len(self._reservations):
            raise LedgerError("预占事件数与资源增量不守恒")
