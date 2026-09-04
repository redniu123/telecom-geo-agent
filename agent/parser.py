"""Deterministic parser for the fixed Chinese P0 request forms."""

from __future__ import annotations

import re
from collections.abc import Iterable

from telecom_core.models import TelecomTask


class RequestParseError(ValueError):
    """Raised when a request cannot be mapped to the frozen TelecomTask shape."""


_ENDPOINT_PATTERN = re.compile(
    r"(?:从\s*)?"
    r"(?P<start>[A-Za-z0-9_-]+)\s*(?:机房|基站|站点)?\s*"
    r"到\s*"
    r"(?P<end>[A-Za-z0-9_-]+)\s*(?:机房|基站|站点)?"
)
_CORE_PATTERN = re.compile(r"(?P<cores>[+-]?\d+)\s*芯")
_EXPLICIT_EXISTING_DUCT_PATTERN = re.compile(
    r"优先\s*(?:使用|利用|走)\s*已有管道"
)


def has_explicit_existing_duct_preference(user_text: str) -> bool:
    """Return whether the request explicitly states the P0 duct preference."""

    return bool(_EXPLICIT_EXISTING_DUCT_PATTERN.search(user_text))


def parse_request(user_text: str, available_site_ids: Iterable[str]) -> TelecomTask:
    """Parse one supported Chinese request without guessing missing facts."""

    if not isinstance(user_text, str) or not user_text.strip():
        raise RequestParseError("用户请求不能为空")

    endpoint_match = _ENDPOINT_PATTERN.search(user_text)
    if endpoint_match is None:
        raise RequestParseError("无法识别起点和终点；请使用“从 X 到 Y”或“X 到 Y”")

    core_match = _CORE_PATTERN.search(user_text)
    if core_match is None:
        raise RequestParseError("缺少光缆芯数；请提供正整数 N 芯")
    fiber_cores = int(core_match.group("cores"))
    if fiber_cores <= 0:
        raise RequestParseError("光缆芯数必须为正整数")

    start_site_id = endpoint_match.group("start")
    end_site_id = endpoint_match.group("end")
    known_sites = set(available_site_ids)
    unknown_sites = [
        site_id for site_id in (start_site_id, end_site_id) if site_id not in known_sites
    ]
    if unknown_sites:
        unknown_text = "、".join(dict.fromkeys(unknown_sites))
        raise RequestParseError(f"未知站点：{unknown_text}")

    return {
        "task_type": "fiber_route",
        "start_site_id": start_site_id,
        "end_site_id": end_site_id,
        "fiber_cores": fiber_cores,
        # The P0 default is True even when the preference phrase is omitted.
        "prefer_existing_duct": True,
    }
