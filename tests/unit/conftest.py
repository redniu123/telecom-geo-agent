from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.generate_demo_data import build_documents


@pytest.fixture
def telecom_task() -> dict[str, object]:
    return {
        "task_type": "fiber_route",
        "start_site_id": "A",
        "end_site_id": "B",
        "fiber_cores": 24,
        "prefer_existing_duct": True,
    }


@pytest.fixture
def demo_documents() -> tuple[dict, dict]:
    sites, network = build_documents()
    return copy.deepcopy(sites), copy.deepcopy(network)


def write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path
