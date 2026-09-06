"""UTF-8 CSV import with row/field-localized validation evidence."""

from __future__ import annotations

import csv
from pathlib import Path

from .schema import BatchRequest, BatchTask, BatchValidationError


REQUIRED_COLUMNS = (
    "task_id",
    "batch_id",
    "site_id",
    "preferred_room_id",
    "priority",
    "cable_fiber_cores",
    "prefer_existing_duct",
    "forbidden_asset_ids",
)


def import_tasks_csv(
    path: str | Path,
    *,
    dataset_id: str,
    known_site_ids: set[str],
    known_room_ids: set[str],
    known_asset_ids: set[str],
) -> BatchRequest:
    source = Path(path).resolve()
    try:
        handle = source.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise BatchValidationError(f"无法读取批量任务 CSV：{source}: {exc}") from exc
    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise BatchValidationError("CSV 缺少表头")
        missing = [name for name in REQUIRED_COLUMNS if name not in reader.fieldnames]
        if missing:
            raise BatchValidationError("CSV 缺少字段：" + "、".join(missing))
        tasks: list[BatchTask] = []
        failures: list[str] = []
        for row_number, row in enumerate(reader, start=2):
            if not any((value or "").strip() for value in row.values() if value is not None):
                continue
            try:
                tasks.append(
                    BatchTask.from_mapping(
                        row,
                        known_site_ids=known_site_ids,
                        known_room_ids=known_room_ids,
                        known_asset_ids=known_asset_ids,
                    )
                )
            except BatchValidationError as exc:
                failures.append(f"第 {row_number} 行：{exc}")
        if failures:
            suffix = "" if len(failures) <= 10 else f"；另有 {len(failures) - 10} 项"
            raise BatchValidationError("CSV 校验失败：" + "；".join(failures[:10]) + suffix)
    return BatchRequest.create(dataset_id, tasks)
