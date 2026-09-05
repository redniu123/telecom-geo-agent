"""Structured competition form controller, independent of widget internals."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from competition.catalog import (
    load_catalog,
    load_competition_network,
    parameters_from_mapping,
)
from competition.outputs import write_workflow_outputs
from competition.schema import ParameterValidationError
from competition.workflow import run_design_workflow

from .layer_plan import build_competition_layer_plan


class CompetitionView(Protocol):
    def configure_competition(self, catalog: dict[str, Any]) -> None: ...
    def set_competition_preview(self, text: str, fingerprint: str | None) -> None: ...
    def set_competition_status(self, text: str, state: str = "idle") -> None: ...
    def set_export_enabled(self, enabled: bool) -> None: ...
    def append_message(self, role: str, text: str, kind: str = "info") -> None: ...


class CompetitionMapPort(Protocol):
    def clear_layers(self) -> None: ...
    def load_plan(self, plan) -> None: ...
    def show_first_route(self) -> None: ...
    def show_final_route(self) -> None: ...
    def export_competition_pdf(self, state: dict, destination, *, paper_size: str = "A3"): ...


class CompetitionController:
    def __init__(self, view: CompetitionView, map_port: CompetitionMapPort, repository_root: str | Path) -> None:
        self.view = view
        self.map_port = map_port
        self.repository_root = Path(repository_root).resolve()
        self.last_state: dict[str, Any] | None = None
        self.last_output_dir: Path | None = None
        self.view.configure_competition(load_catalog(self.repository_root))
        self.view.set_export_enabled(False)

    def preview(self, raw_parameters: dict[str, Any]) -> None:
        try:
            parameters = parameters_from_mapping(self.repository_root, raw_parameters)
        except Exception as exc:
            self.view.set_competition_preview(f"参数无效：{type(exc).__name__}: {exc}", None)
            self.view.set_competition_status("参数无效", "error")
            return
        self.view.set_competition_preview(parameters.preview_text(), parameters.fingerprint)
        self.view.set_competition_status("参数已预览，等待确认执行", "idle")

    def execute(self, raw_parameters: dict[str, Any], confirmed_fingerprint: str | None) -> None:
        self.view.set_export_enabled(False)
        self.view.set_competition_status("正在执行确定性规划…", "running")
        try:
            parameters = parameters_from_mapping(self.repository_root, raw_parameters)
            parameters.assert_confirmation(confirmed_fingerprint)
        except Exception as exc:
            self.view.set_competition_status("拒绝执行：参数未确认", "error")
            self.view.append_message("assistant", f"竞赛参数拒绝执行：{type(exc).__name__}: {exc}", "error")
            return

        self.map_port.clear_layers()
        state = run_design_workflow(
            parameters,
            self.repository_root,
            confirmed_fingerprint=confirmed_fingerprint,
        )
        network = load_competition_network(self.repository_root)
        output_dir = self.repository_root / "outputs" / "competition" / parameters.scenario_id
        write_workflow_outputs(state, network, output_dir)
        self.last_state = state
        self.last_output_dir = output_dir

        plan = build_competition_layer_plan(
            self.repository_root,
            parameters.scenario_id,
            include_candidate_route=state["candidate_route"] is not None,
            include_final_route=state["status"] == "completed" and state["final_route"] is not None,
        )
        plan.validate_sources()
        self.map_port.load_plan(plan)
        if state["status"] == "completed":
            self.map_port.show_final_route()
            bom = state["bom_result"]
            self.view.append_message(
                "assistant",
                f"竞赛场景 {parameters.scenario_id} 完成：修复 {state['repair_count']} 次，"
                f"最终 PASS；路线 {bom['total_length_m']:.2f} m，建议光缆 "
                f"{bom['recommended_cable_length_m']:.2f} m。",
                "success",
            )
            self.view.set_competition_status("完成 · 最终 PASS", "success")
            self.view.set_export_enabled(True)
        else:
            self.map_port.show_first_route()
            self.view.append_message(
                "assistant",
                f"竞赛场景 {parameters.scenario_id} 明确失败，未生成 BOM 或最终 PASS：{state['error']}",
                "error",
            )
            self.view.set_competition_status("失败 · 已保留证据", "error")

    def export_pdf(self) -> None:
        if self.last_state is None or self.last_state.get("status") != "completed":
            self.view.append_message("assistant", "没有可导出的最终 PASS 竞赛结果。", "error")
            return
        destination = (
            self.repository_root
            / "output"
            / "pdf"
            / "通信线路参数化智能设计_标准图纸_A3.pdf"
        )
        try:
            path = self.map_port.export_competition_pdf(
                self.last_state, destination, paper_size="A3"
            )
        except Exception as exc:
            self.view.set_competition_status("图纸导出失败", "error")
            self.view.append_message(
                "assistant", f"图纸导出失败：{type(exc).__name__}: {exc}", "error"
            )
            return
        self.view.append_message(
            "assistant",
            f"A3 标准图纸已导出：{path}。仍为竞赛样例/非正式施工图。",
            "success",
        )
        self.view.set_competition_status("图纸导出完成", "success")


class PluginController:
    """Keep the existing chat route and the competition form as peers."""

    def __init__(self, chat_controller, competition_controller: CompetitionController) -> None:
        self.chat = chat_controller
        self.competition = competition_controller

    def handle_user_input(self, text: str) -> None:
        self.chat.handle_user_input(text)

    def preview_competition(self, raw_parameters: dict[str, Any]) -> None:
        self.competition.preview(raw_parameters)

    def execute_competition(
        self, raw_parameters: dict[str, Any], confirmed_fingerprint: str | None
    ) -> None:
        self.competition.execute(raw_parameters, confirmed_fingerprint)

    def export_competition(self) -> None:
        self.competition.export_pdf()

    @property
    def last_state(self):
        return self.chat.last_state
