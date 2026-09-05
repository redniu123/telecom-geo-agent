"""Plain-Python conversational controller over the frozen P0 Workflow."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from agent.outputs import write_outputs
from agent.state import AgentState
from agent.workflow import run_workflow
from telecom_core.data_loader import load_demo_network
from telecom_core.models import NetworkData

from .layer_plan import LayerPlan, build_layer_plan
from .presentation import build_workflow_events, issue_asset_ids


class ChatView(Protocol):
    def append_message(self, role: str, text: str, kind: str = "info") -> None: ...

    def clear_conversation(self) -> None: ...

    def set_status(self, text: str, state: str = "idle") -> None: ...

    def set_actions_enabled(self, enabled: bool) -> None: ...


class MapPort(Protocol):
    def load_plan(self, plan: LayerPlan) -> None: ...

    def show_first_route(self) -> None: ...

    def show_final_route(self) -> None: ...

    def focus_issue(self, asset_id: str) -> None: ...

    def clear_layers(self) -> None: ...


WorkflowRunner = Callable[[str], AgentState]
OutputWriter = Callable[[AgentState, str | Path], list[Path]]
NetworkLoader = Callable[[], NetworkData]


class ChatController:
    """Classify fixed local intents and present real P0 state in order."""

    def __init__(
        self,
        view: ChatView,
        map_port: MapPort,
        repository_root: str | Path,
        *,
        workflow_runner: WorkflowRunner = run_workflow,
        output_writer: OutputWriter = write_outputs,
        network_loader: NetworkLoader = load_demo_network,
    ) -> None:
        self.view = view
        self.map_port = map_port
        self.repository_root = Path(repository_root).resolve()
        self.workflow_runner = workflow_runner
        self.output_writer = output_writer
        self.network_loader = network_loader
        self.last_state: AgentState | None = None
        self.last_planning_request: str | None = None
        self.layer_plan: LayerPlan | None = None
        self.view.set_actions_enabled(False)

    @staticmethod
    def classify_intent(text: str) -> str:
        compact = "".join(text.strip().split())
        upper = compact.upper()
        if "清空" in compact and ("对话" in compact or "聊天" in compact):
            return "clear"
        if compact in {"帮助", "指令", "可用指令"} or "怎么用" in compact:
            return "help"
        if "重新运行" in compact or "再次运行" in compact:
            return "rerun"
        if "当前状态" in compact or "规划状态" in compact:
            return "show_status"
        if "解释" in compact and ("失败" in compact or "D017" in upper):
            return "explain_failure"
        if ("定位" in compact or "缩放" in compact) and (
            "问题" in compact or "D017" in upper
        ):
            return "focus_issue"
        if "第一次路线" in compact or "初次路线" in compact:
            return "show_first"
        if "最终路线" in compact or "第二次路线" in compact:
            return "show_final"
        if "BOM" in upper or "材料清单" in compact:
            return "show_bom"
        if "规划" in compact and "到" in compact and "芯" in compact:
            return "run_plan"
        return "unknown"

    def handle_user_input(self, text: str) -> None:
        request = text.strip()
        if not request:
            return
        intent = self.classify_intent(request)
        if intent == "clear":
            self.view.clear_conversation()
            self.view.append_message(
                "assistant",
                "对话已清空；已加载的地图结果和本次规划上下文仍保留。",
            )
            self.view.set_status("就绪", "idle")
            return

        self.view.append_message("user", request)
        try:
            if intent == "run_plan":
                self._run_plan(request)
                return
            elif intent == "rerun":
                if self.last_planning_request is None:
                    raise RuntimeError("还没有可重新运行的规划请求")
                self._run_plan(self.last_planning_request)
                return
            elif intent == "help":
                self.view.append_message("assistant", self._help_text(), "info")
            elif intent == "show_status":
                self.view.append_message("assistant", self._status_text(), "info")
            elif intent == "explain_failure":
                self._explain_failure()
            elif intent == "focus_issue":
                state = self._require_state()
                issues = issue_asset_ids(state)
                if not issues:
                    self.view.append_message(
                        "assistant", "本次规划没有需要定位的问题段。", "success"
                    )
                    self.view.set_status("就绪", "idle")
                    return
                self.map_port.focus_issue(issues[0])
                self.view.append_message(
                    "assistant",
                    f"已定位并标红 {issues[0]} 合成 P0 测试段。",
                    "map",
                )
            elif intent == "show_first":
                state = self._require_state()
                if state["first_route"] is None:
                    raise RuntimeError("当前运行没有第一次路线")
                self.map_port.show_first_route()
                self.view.append_message(
                    "assistant",
                    f"地图已切换到第一次路线 {state['first_route']['route_id']}："
                    + " → ".join(state["first_route"]["edge_ids"]),
                    "map",
                )
            elif intent == "show_final":
                state = self._require_state()
                if state["final_route"] is None:
                    raise RuntimeError("当前运行没有最终路线")
                self.map_port.show_final_route()
                self.view.append_message(
                    "assistant",
                    f"地图已切换到最终路线 {state['final_route']['route_id']}："
                    + " → ".join(state["final_route"]["edge_ids"])
                    + ("（PASS）" if state["status"] == "completed" else "（未通过）"),
                    "map",
                )
            elif intent == "show_bom":
                state = self._require_state()
                self.view.append_message("assistant", self._bom_text(state), "bom")
            else:
                self.view.append_message(
                    "assistant",
                    self._help_text(),
                    "warning",
                )
            self.view.set_status("就绪", "idle")
        except Exception as exc:
            self.view.append_message(
                "assistant", f"执行失败：{type(exc).__name__}: {exc}", "error"
            )
            self.view.set_status("执行失败", "error")

    def _run_plan(self, request: str) -> None:
        self.view.set_status("正在运行确定性 P0 Workflow…", "running")
        self.view.set_actions_enabled(False)
        # QGIS/OGR may hold the previous GeoJSON files open on Windows. Release
        # only plugin-owned layers before write_outputs rotates stale artifacts.
        if self.layer_plan is not None:
            self.map_port.clear_layers()
            self.layer_plan = None
        self.last_planning_request = request
        state = self.workflow_runner(request)
        self.last_state = state
        self.output_writer(state, self.repository_root / "outputs")
        network = self.network_loader()
        for event in build_workflow_events(state, network):
            self.view.append_message("assistant", event.text, event.kind)

        first_route = state["first_route"]
        final_route = state["final_route"]
        issues = issue_asset_ids(state)
        if first_route is not None or final_route is not None:
            plan = build_layer_plan(
                self.repository_root,
                include_first_route=first_route is not None,
                include_final_route=final_route is not None,
                issue_assets=issues,
                first_route_id=first_route["route_id"] if first_route else "R001",
                final_route_id=final_route["route_id"] if final_route else "R002",
                final_route_passed=state["status"] == "completed",
            )
            plan.validate_sources()
            self.map_port.load_plan(plan)
            self.layer_plan = plan
            if final_route is not None:
                self.map_port.show_final_route()
            elif first_route is not None:
                self.map_port.show_first_route()
        else:
            self.map_port.clear_layers()
            self.layer_plan = None

        if state["status"] == "completed":
            if final_route is None or state["bom_result"] is None:
                raise RuntimeError("completed 状态缺少最终路线或 BOM")
            self.view.set_actions_enabled(True)
            self.view.set_status("完成 · 最终 PASS", "success")
        else:
            self.view.set_actions_enabled(first_route is not None)
            self.view.set_status("Workflow 失败 · 已保留证据", "error")

    def _require_state(self) -> AgentState:
        state = self.last_state
        if state is None:
            raise RuntimeError("请先输入“从A到B规划24芯光缆”运行本次规划")
        return state

    def _explain_failure(self) -> None:
        state = self._require_state()
        network = self.network_loader()
        events = build_workflow_events(state, network)
        failures = [event for event in events if event.kind in {"warning", "error"}]
        if not failures:
            self.view.append_message(
                "assistant", "本次第一次校核即通过，没有失败原因可解释。", "success"
            )
            return
        self.view.append_message("assistant", "失败解释：", "warning")
        for event in failures:
            self.view.append_message("assistant", event.text, event.kind)

    @staticmethod
    def _bom_text(state: AgentState) -> str:
        bom = state["bom_result"]
        if bom is None:
            raise RuntimeError("当前结果没有 BOM")
        return (
            "BOM（由最终路线复算）："
            f"总长 {bom['total_length_m']:.2f} m；"
            f"已有管道 {bom['existing_duct_length_m']:.2f} m；"
            f"新建 {bom['new_build_length_m']:.2f} m；"
            f"建议光缆 {bom['recommended_cable_length_m']:.2f} m；"
            "used_edge_ids=" + " → ".join(bom["used_edge_ids"])
        )

    def _status_text(self) -> str:
        state = self.last_state
        if state is None:
            return "当前还没有运行规划。"
        first = state["first_route"]
        final = state["final_route"]
        return (
            f"当前状态：{state['status']}；"
            f"第一次路线={first['route_id'] if first else '无'}；"
            f"最终路线={final['route_id'] if final else '无'}；"
            f"repair_count={state['repair_count']}；"
            f"问题资产={','.join(issue_asset_ids(state)) or '无'}。"
        )

    @staticmethod
    def _help_text() -> str:
        return (
            "可用确定性指令：运行规划（例如“从A到B规划24芯光缆”）、重新运行、"
            "当前状态、解释失败、定位问题段、显示第一次路线、显示最终路线、"
            "查看 BOM、清空对话、帮助。"
        )
