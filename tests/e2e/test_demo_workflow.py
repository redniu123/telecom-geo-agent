from __future__ import annotations

import socket

import pytest

from agent.parser import RequestParseError, parse_request
from agent.workflow import run_workflow
from telecom_core.validation import validate_route


EXPECTED_TASK = {
    "task_type": "fiber_route",
    "start_site_id": "A",
    "end_site_id": "B",
    "fiber_cores": 24,
    "prefer_existing_duct": True,
}


@pytest.mark.parametrize(
    "user_text",
    [
        "从 A 机房到 B 基站规划一条 24 芯光缆，优先使用已有管道。",
        "从A到B规划24芯光缆",
        "A 到 B，24芯，优先走已有管道",
    ],
)
def test_required_chinese_forms_parse_to_same_task(user_text):
    assert parse_request(user_text, {"A", "B"}) == EXPECTED_TASK


@pytest.mark.parametrize(
    ("user_text", "message"),
    [
        ("从 A 到 B 规划光缆", "缺少光缆芯数"),
        ("从 A 到 C 规划 24 芯光缆", "未知站点：C"),
        ("从 A 到 B 规划 0 芯光缆", "必须为正整数"),
        ("从 A 到 B 规划 -1 芯光缆", "必须为正整数"),
    ],
)
def test_invalid_requests_fail_explicitly(user_text, message):
    with pytest.raises(RequestParseError, match=message):
        parse_request(user_text, {"A", "B"})


def test_real_core_workflow_repairs_d017_and_builds_bom():
    state = run_workflow("从 A 机房到 B 基站规划一条 24 芯光缆，优先使用已有管道。")

    assert state["status"] == "completed"
    assert state["error"] is None
    assert state["task"] == EXPECTED_TASK
    assert state["first_route"] is not None
    assert state["first_route"]["edge_ids"] == ["D001", "D017", "D003"]
    assert state["validation_history"][0] == {
        "passed": False,
        "violations": [
            {
                "rule_id": "R_CAPACITY",
                "type": "duct_capacity",
                "asset_id": "D017",
                "severity": "error",
                "message": "D017 剩余容量不足以承载 24 芯光缆",
                "repair_hint": "forbid_asset",
            }
        ],
    }
    assert state["forbidden_asset_ids"] == ["D017"]
    assert state["repair_count"] == 1
    assert state["final_route"] is not None
    assert state["final_route"]["edge_ids"] == ["N001", "N002"]
    assert "D017" not in state["final_route"]["edge_ids"]
    assert state["validation_history"][1] == {"passed": True, "violations": []}
    assert state["bom_result"] == {
        "total_length_m": 400.0,
        "existing_duct_length_m": 180.0,
        "new_build_length_m": 220.0,
        "recommended_cable_length_m": 440.0,
        "slack_ratio": 0.1,
        "used_edge_ids": ["N001", "N002"],
    }
    assert state["bom_result"]["used_edge_ids"] == state["final_route"]["edge_ids"]
    assert state["bom_result"]["used_edge_ids"] != state["first_route"]["edge_ids"]


def test_main_success_path_does_not_open_network_socket(monkeypatch):
    def reject_network(*args, **kwargs):
        raise AssertionError("P0 workflow attempted a network call")

    monkeypatch.setattr(socket, "create_connection", reject_network)
    monkeypatch.setattr(socket.socket, "connect", reject_network)

    state = run_workflow("从A到B规划24芯光缆")
    assert state["status"] == "completed"


def test_second_validation_failure_stops_after_one_repair():
    def fail_final_route(route, task, edge_records):
        result = validate_route(route, task, edge_records)
        if route["route_id"] == "R002":
            return {
                "passed": False,
                "violations": [
                    {
                        "rule_id": "R_CAPACITY",
                        "type": "duct_capacity",
                        "asset_id": "N001",
                        "severity": "error",
                        "message": "替代路线容量仍不足",
                        "repair_hint": "forbid_asset",
                    }
                ],
            }
        return result

    state = run_workflow("从A到B规划24芯光缆", validator=fail_final_route)

    assert state["status"] == "failed"
    assert state["repair_count"] == 1
    assert state["forbidden_asset_ids"] == ["D017"]
    assert len(state["validation_history"]) == 2
    assert state["validation_history"][1]["passed"] is False
    assert state["bom_result"] is None
    assert "第二次校核仍失败" in state["error"]
