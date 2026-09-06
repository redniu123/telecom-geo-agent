"""Strict contracts for one deterministic, single-process batch run."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable


ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]{1,63}$")
DATASET_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{1,127}$")
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class BatchValidationError(ValueError):
    """Raised when batch input must fail closed before planning."""


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BatchValidationError(f"{field}: 必须是非空字符串")
    result = value.strip()
    if not ID_PATTERN.fullmatch(result):
        raise BatchValidationError(f"{field}: 非法 ID {result!r}")
    return result


def _boolean(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "是"}:
            return True
        if normalized in {"false", "0", "no", "n", "否"}:
            return False
    raise BatchValidationError(f"{field}: 必须是 true/false 布尔值")


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _forbidden_assets(value: Any, known_asset_ids: set[str]) -> tuple[str, ...]:
    if value in (None, "", (), []):
        return ()
    if isinstance(value, str):
        values = [item.strip() for item in value.replace("，", ",").replace(";", ",").split(",")]
    elif isinstance(value, (list, tuple)):
        values = [str(item).strip() for item in value]
    else:
        raise BatchValidationError("forbidden_asset_ids: 必须是逗号分隔字符串或列表")
    unique: list[str] = []
    for asset_id in values:
        if not asset_id:
            continue
        if asset_id not in known_asset_ids:
            raise BatchValidationError(f"forbidden_asset_ids: 未知候选通道 {asset_id!r}")
        if asset_id not in unique:
            unique.append(asset_id)
    return tuple(sorted(unique))


@dataclass(frozen=True)
class BatchTask:
    task_id: str
    batch_id: str
    site_id: str
    preferred_room_id: str
    alternate_room_id: str | None
    priority: str
    cable_fiber_cores: int
    prefer_existing_duct: bool
    forbidden_asset_ids: tuple[str, ...] = ()
    required_date: str | None = None
    notes: str | None = None

    @classmethod
    def from_mapping(
        cls,
        value: dict[str, Any],
        *,
        known_site_ids: set[str],
        known_room_ids: set[str],
        known_asset_ids: set[str],
    ) -> "BatchTask":
        task_id = _required_text(value.get("task_id"), "task_id")
        batch_id = _required_text(value.get("batch_id"), "batch_id")
        site_id = _required_text(value.get("site_id"), "site_id")
        if site_id not in known_site_ids:
            raise BatchValidationError(f"site_id: 未知接入设施 {site_id!r}")
        room_id = _required_text(value.get("preferred_room_id"), "preferred_room_id")
        if room_id not in known_room_ids:
            raise BatchValidationError(f"preferred_room_id: 未知汇聚机房 {room_id!r}")
        alternate = _optional_text(value.get("alternate_room_id"))
        if alternate is not None and alternate not in known_room_ids:
            raise BatchValidationError(f"alternate_room_id: 未知汇聚机房 {alternate!r}")
        priority = str(value.get("priority", "")).strip().lower()
        if priority not in PRIORITY_ORDER:
            raise BatchValidationError("priority: 必须是 high/medium/low")
        raw_cores = value.get("cable_fiber_cores")
        try:
            cores = int(raw_cores)
        except (TypeError, ValueError) as exc:
            raise BatchValidationError("cable_fiber_cores: 必须是 1–576 的整数") from exc
        if isinstance(raw_cores, bool) or not 1 <= cores <= 576 or str(raw_cores).strip() != str(cores):
            raise BatchValidationError("cable_fiber_cores: 必须是 1–576 的整数")
        required_date = _optional_text(value.get("required_date"))
        if required_date:
            try:
                date.fromisoformat(required_date)
            except ValueError as exc:
                raise BatchValidationError("required_date: 必须是 YYYY-MM-DD") from exc
        return cls(
            task_id=task_id,
            batch_id=batch_id,
            site_id=site_id,
            preferred_room_id=room_id,
            alternate_room_id=alternate,
            priority=priority,
            cable_fiber_cores=cores,
            prefer_existing_duct=_boolean(value.get("prefer_existing_duct"), "prefer_existing_duct"),
            forbidden_asset_ids=_forbidden_assets(value.get("forbidden_asset_ids"), known_asset_ids),
            required_date=required_date,
            notes=_optional_text(value.get("notes")),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "batch_id": self.batch_id,
            "site_id": self.site_id,
            "preferred_room_id": self.preferred_room_id,
            "alternate_room_id": self.alternate_room_id,
            "priority": self.priority,
            "cable_fiber_cores": self.cable_fiber_cores,
            "prefer_existing_duct": self.prefer_existing_duct,
            "forbidden_asset_ids": list(self.forbidden_asset_ids),
            "required_date": self.required_date,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class BatchRequest:
    dataset_id: str
    batch_id: str
    tasks: tuple[BatchTask, ...]
    max_replans_per_task: int = 1
    sorting_rule: str = "priority(high>medium>low),task_id(ascending)"

    @classmethod
    def create(cls, dataset_id: str, tasks: Iterable[BatchTask]) -> "BatchRequest":
        if not isinstance(dataset_id, str) or not DATASET_ID_PATTERN.fullmatch(dataset_id.strip()):
            raise BatchValidationError(f"dataset_id: 非法 ID {dataset_id!r}")
        dataset = dataset_id.strip()
        items = tuple(tasks)
        if not items:
            raise BatchValidationError("批次至少包含 1 个任务")
        batch_ids = {item.batch_id for item in items}
        if len(batch_ids) != 1:
            raise BatchValidationError(f"一个输入文件只能包含一个 batch_id，实际为 {sorted(batch_ids)}")
        task_ids = [item.task_id for item in items]
        duplicates = sorted({task_id for task_id in task_ids if task_ids.count(task_id) > 1})
        if duplicates:
            raise BatchValidationError("task_id 重复：" + "、".join(duplicates))
        return cls(dataset_id=dataset, batch_id=next(iter(batch_ids)), tasks=items)

    @property
    def ordered_tasks(self) -> tuple[BatchTask, ...]:
        return tuple(sorted(self.tasks, key=lambda item: (PRIORITY_ORDER[item.priority], item.task_id)))

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "batch_id": self.batch_id,
            "max_replans_per_task": self.max_replans_per_task,
            "sorting_rule": self.sorting_rule,
            "tasks": [item.as_dict() for item in self.ordered_tasks],
        }

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def assert_confirmation(self, fingerprint: str | None) -> None:
        if fingerprint != self.fingerprint:
            raise BatchValidationError("批次参数尚未确认，或确认后输入已经变化")

    def preview_text(self) -> str:
        counts = {key: 0 for key in PRIORITY_ORDER}
        for task in self.tasks:
            counts[task.priority] += 1
        return (
            f"数据集：{self.dataset_id}\n批次：{self.batch_id}\n任务数：{len(self.tasks)}\n"
            f"优先级：高 {counts['high']} / 中 {counts['medium']} / 低 {counts['low']}\n"
            f"固定顺序：{self.sorting_rule}\n每任务最多自动改路：1 次\n"
            f"确认指纹：{self.fingerprint[:16]}"
        )
