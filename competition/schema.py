"""Validated, fingerprinted structured design parameters."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any


ASSET_ID = re.compile(r"^C[12]-\d{3}$")


class ParameterValidationError(ValueError):
    """Raised when a structured request must fail closed."""


@dataclass(frozen=True)
class DesignParameters:
    dataset_id: str
    scenario_id: str
    start_site_id: str
    end_site_id: str
    fiber_cores: int
    prefer_existing_duct: bool
    forbidden_asset_ids: tuple[str, ...] = ()

    @classmethod
    def from_mapping(
        cls,
        value: dict[str, Any],
        *,
        known_dataset_id: str,
        known_scenarios: set[str],
        known_site_ids: set[str],
        known_asset_ids: set[str],
    ) -> "DesignParameters":
        required = {
            "dataset_id",
            "scenario_id",
            "start_site_id",
            "end_site_id",
            "fiber_cores",
            "prefer_existing_duct",
            "forbidden_asset_ids",
        }
        missing = sorted(required - value.keys())
        if missing:
            raise ParameterValidationError("缺少结构化参数：" + "、".join(missing))
        dataset_id = value["dataset_id"]
        if dataset_id != known_dataset_id:
            raise ParameterValidationError(f"未知或未审计的数据集：{dataset_id!r}")
        scenario_id = value["scenario_id"]
        if scenario_id not in known_scenarios:
            raise ParameterValidationError(f"未知场景：{scenario_id!r}")
        start = value["start_site_id"]
        end = value["end_site_id"]
        if start not in known_site_ids:
            raise ParameterValidationError(f"起点不存在或未授权：{start!r}")
        if end not in known_site_ids:
            raise ParameterValidationError(f"终点不存在或未授权：{end!r}")
        if start == end:
            raise ParameterValidationError("起点和终点不能相同")
        fiber_cores = value["fiber_cores"]
        if (
            isinstance(fiber_cores, bool)
            or not isinstance(fiber_cores, int)
            or not 1 <= fiber_cores <= 576
        ):
            raise ParameterValidationError("光缆芯数必须是 1–576 的整数")
        preference = value["prefer_existing_duct"]
        if not isinstance(preference, bool):
            raise ParameterValidationError("已有管道偏好必须是布尔值")
        forbidden_raw = value["forbidden_asset_ids"]
        if not isinstance(forbidden_raw, (list, tuple)):
            raise ParameterValidationError("禁用资产必须是列表")
        forbidden: list[str] = []
        for asset_id in forbidden_raw:
            if not isinstance(asset_id, str) or not ASSET_ID.fullmatch(asset_id):
                raise ParameterValidationError(f"非法禁用资产 ID：{asset_id!r}")
            if asset_id not in known_asset_ids:
                raise ParameterValidationError(f"禁用资产不存在：{asset_id}")
            if asset_id not in forbidden:
                forbidden.append(asset_id)
        return cls(
            dataset_id=dataset_id,
            scenario_id=scenario_id,
            start_site_id=start,
            end_site_id=end,
            fiber_cores=fiber_cores,
            prefer_existing_duct=preference,
            forbidden_asset_ids=tuple(sorted(forbidden)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "scenario_id": self.scenario_id,
            "start_site_id": self.start_site_id,
            "end_site_id": self.end_site_id,
            "fiber_cores": self.fiber_cores,
            "prefer_existing_duct": self.prefer_existing_duct,
            "forbidden_asset_ids": list(self.forbidden_asset_ids),
        }

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def preview_text(self) -> str:
        forbidden = "、".join(self.forbidden_asset_ids) or "无"
        return (
            f"数据集：{self.dataset_id}\n"
            f"场景：{self.scenario_id}\n"
            f"起终点：{self.start_site_id} → {self.end_site_id}\n"
            f"光缆：{self.fiber_cores} 芯\n"
            f"优先已有管道：{'是' if self.prefer_existing_duct else '否'}\n"
            f"显式禁用资产：{forbidden}\n"
            f"确认指纹：{self.fingerprint[:12]}"
        )

    def assert_confirmation(self, confirmed_fingerprint: str | None) -> None:
        if confirmed_fingerprint != self.fingerprint:
            raise ParameterValidationError("参数尚未确认，或确认后字段已发生变化")
