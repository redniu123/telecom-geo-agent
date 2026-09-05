from __future__ import annotations

from pathlib import Path

import pytest

from qgis_plugin.telecom_geo_agent.controller import ChatController


class FakeView:
    def __init__(self):
        self.messages = []
        self.statuses = []
        self.action_states = []
        self.clear_count = 0

    def append_message(self, role, text, kind="info"):
        self.messages.append((role, text, kind))

    def clear_conversation(self):
        self.clear_count += 1
        self.messages.clear()

    def set_status(self, text, state="idle"):
        self.statuses.append((text, state))

    def set_actions_enabled(self, enabled):
        self.action_states.append(enabled)


class FakeMap:
    def __init__(self):
        self.loaded_plan = None
        self.calls = []

    def load_plan(self, plan):
        self.loaded_plan = plan
        self.calls.append("load")

    def show_first_route(self):
        self.calls.append("first")

    def show_final_route(self):
        self.calls.append("final")

    def focus_issue(self, asset_id):
        self.calls.append(f"focus:{asset_id}")

    def clear_layers(self):
        self.calls.append("clear")


def _controller(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    view = FakeView()
    map_port = FakeMap()

    def write_to_temp(state, output_dir):
        from agent.outputs import write_outputs

        return write_outputs(state, output_dir)

    # The layer plan intentionally points at the supplied root. Link the
    # temporary outputs while canonical source/data remain in the repository.
    controller = ChatController(view, map_port, root, output_writer=write_to_temp)
    original_build = controller.repository_root
    assert original_build == root
    return controller, view, map_port


def _use_temporary_runtime(controller, tmp_path: Path):
    repo_root = controller.repository_root
    plan_root = tmp_path / "runtime"
    (plan_root / "data" / "demo").mkdir(parents=True)
    (plan_root / "outputs").mkdir(parents=True)
    for name in ("network.geojson", "sites.geojson"):
        (plan_root / "data" / "demo" / name).write_bytes(
            (repo_root / "data" / "demo" / name).read_bytes()
        )
    controller.repository_root = plan_root
    return plan_root


def test_real_workflow_is_presented_in_required_order(tmp_path):
    controller, view, map_port = _controller(tmp_path)
    # Avoid touching committed outputs while retaining canonical source data.
    _use_temporary_runtime(controller, tmp_path)

    controller.handle_user_input("从A到B规划24芯光缆")

    assert controller.last_state["status"] == "completed"
    assistant_text = [text for role, text, _kind in view.messages if role == "assistant"]
    joined = "\n".join(assistant_text)
    required = [
        "第一次路线 R001：D001 → D017 → D003",
        "第一次校核：FAIL / R_CAPACITY",
        "不是现实管道",
        "总容量 48 芯，已用 32 芯，剩余 16 芯",
        "自动修复：禁用问题段 D017",
        "重新规划 R002：N001 → N002",
        "最终校核：PASS",
        "建议光缆 440.00 m",
    ]
    for item in required:
        assert item in joined
    assert [joined.index(item) for item in required] == sorted(
        joined.index(item) for item in required
    )
    assert map_port.calls == ["load", "final"]
    assert map_port.loaded_plan.by_key("issue_d017").subset_expression == (
        '"edge_id" = \'D017\''
    )
    assert view.statuses[-1] == ("完成 · 最终 PASS", "success")


@pytest.mark.parametrize(
    ("command", "expected_call"),
    [
        ("定位问题段", "focus:D017"),
        ("显示第一次路线", "first"),
        ("显示最终路线", "final"),
    ],
)
def test_map_commands_require_and_use_current_real_result(tmp_path, command, expected_call):
    controller, _view, map_port = _controller(tmp_path)
    controller.last_state = controller.workflow_runner("从A到B规划24芯光缆")

    controller.handle_user_input(command)

    assert map_port.calls[-1] == expected_call


def test_explain_bom_clear_and_unknown_intents(tmp_path):
    controller, view, _map_port = _controller(tmp_path)
    controller.last_state = controller.workflow_runner("从A到B规划24芯光缆")

    controller.handle_user_input("解释失败")
    controller.handle_user_input("查看 BOM")
    text = "\n".join(message[1] for message in view.messages)
    assert "D017 是仓库内合成 P0 测试段，不是现实管道" in text
    assert "used_edge_ids=N001 → N002" in text

    controller.handle_user_input("随便聊聊")
    assert "可用确定性指令" in view.messages[-1][1]
    controller.handle_user_input("清空对话")
    assert view.clear_count == 1
    assert view.messages[-1][1].startswith("对话已清空")
    assert controller.last_state["status"] == "completed"


def test_commands_before_planning_fail_explicitly(tmp_path):
    controller, view, map_port = _controller(tmp_path)

    controller.handle_user_input("显示最终路线")

    assert map_port.calls == []
    assert "请先输入" in view.messages[-1][1]
    assert view.statuses[-1] == ("执行失败", "error")


def test_no_repair_success_is_presented_truthfully(tmp_path):
    controller, view, map_port = _controller(tmp_path)
    _use_temporary_runtime(controller, tmp_path)

    controller.handle_user_input("从A到B规划12芯光缆")

    state = controller.last_state
    assert state["status"] == "completed"
    assert state["repair_count"] == 0
    assert len(state["validation_history"]) == 1
    assert state["first_route"] is state["final_route"]
    joined = "\n".join(text for _role, text, _kind in view.messages)
    assert "第一次校核：PASS" in joined
    assert "无需重规划；最终路线沿用 R001" in joined
    assert "最终校核：PASS" in joined
    assert "建议光缆 385.00 m" in joined
    assert "自动修复" not in joined
    assert map_port.loaded_plan.by_key("final_route").name == "最终路线 R001（PASS）"
    assert all(layer.key != "issue_d017" for layer in map_port.loaded_plan.layers)
    assert map_port.calls == ["load", "final"]


def test_failed_workflow_keeps_partial_routes_and_marks_final_unpassed(tmp_path):
    controller, view, map_port = _controller(tmp_path)
    _use_temporary_runtime(controller, tmp_path)

    controller.handle_user_input("从A到B规划64芯光缆")

    state = controller.last_state
    assert state["status"] == "failed"
    assert state["first_route"]["edge_ids"] == ["D001", "D017", "D003"]
    assert state["final_route"]["edge_ids"] == ["N001", "N002"]
    assert state["bom_result"] is None
    assert map_port.loaded_plan.by_key("final_route").style == "failed_route"
    assert map_port.loaded_plan.by_key("final_route").name.endswith("（未通过）")
    assert map_port.loaded_plan.by_key("issues").subset_expression == (
        '"edge_id" = \'D017\' OR "edge_id" = \'D003\' OR "edge_id" = \'N001\''
    )
    joined = "\n".join(text for _role, text, _kind in view.messages)
    assert "Workflow 明确失败；已保留完成到当前步骤的真实证据" in joined
    assert "最终校核：FAIL / R_CAPACITY" in joined
    assert view.statuses[-1] == ("Workflow 失败 · 已保留证据", "error")


def test_parse_failure_clears_stale_plugin_layers_and_keeps_error(tmp_path):
    controller, view, map_port = _controller(tmp_path)
    _use_temporary_runtime(controller, tmp_path)

    controller.handle_user_input("从A到C规划24芯光缆")

    assert controller.last_state["status"] == "failed"
    assert controller.last_state["first_route"] is None
    assert map_port.calls == ["clear"]
    assert controller.layer_plan is None
    assert "未知站点：C" in view.messages[-1][1]


def test_help_status_and_rerun_use_session_context(tmp_path):
    controller, view, map_port = _controller(tmp_path)
    _use_temporary_runtime(controller, tmp_path)

    controller.handle_user_input("帮助")
    assert "重新运行" in view.messages[-1][1]
    controller.handle_user_input("当前状态")
    assert view.messages[-1][1] == "当前还没有运行规划。"

    controller.handle_user_input("从A到B规划12芯光缆")
    controller.handle_user_input("当前状态")
    assert "completed" in view.messages[-1][1]
    assert "repair_count=0" in view.messages[-1][1]
    controller.handle_user_input("重新运行")
    assert controller.last_planning_request == "从A到B规划12芯光缆"
    assert map_port.calls.count("load") == 2
