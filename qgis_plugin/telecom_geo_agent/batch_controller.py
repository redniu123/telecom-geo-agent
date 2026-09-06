"""Batch tab controller, independent of concrete Qt widget implementation."""

from __future__ import annotations

from pathlib import Path

from competition.batch.data_loader import load_batch_dataset
from competition.batch.outputs import write_batch_outputs
from competition.batch.planner import run_batch
from competition.batch.task_import import import_tasks_csv

from .batch_layer_plan import build_batch_layer_plan


class BatchController:
    def __init__(self, view, map_port, repository_root: str | Path) -> None:
        self.view = view
        self.map_port = map_port
        self.repository_root = Path(repository_root).resolve()
        self.dataset = load_batch_dataset(self.repository_root)
        self.request = None
        self.last_state = None
        self.output_dir = None
        self.view.configure_batch(self.dataset.dataset_id, str(self.dataset.root / "batch_tasks.csv"))
        self.view.set_batch_export_enabled(False)

    def import_csv(self, path: str) -> None:
        try:
            self.request = import_tasks_csv(path, dataset_id=self.dataset.dataset_id, known_site_ids=self.dataset.site_ids, known_room_ids=self.dataset.room_ids, known_asset_ids=set(self.dataset.resources))
        except Exception as exc:
            self.request = None
            self.view.set_batch_preview(f"导入失败：{type(exc).__name__}: {exc}", None)
            self.view.set_batch_status("CSV 校验失败", "error")
            return
        self.view.set_batch_preview(f"CSV 字段校验通过，共 {len(self.request.tasks)} 个任务。请预览并确认批次指纹。", None)
        self.view.set_batch_status("导入通过，等待预览", "idle")

    def preview(self) -> None:
        if self.request is None:
            self.import_csv(self.view.batch_csv_path())
        if self.request is not None:
            self.view.set_batch_preview(self.request.preview_text(), self.request.fingerprint)
            self.view.set_batch_status("批次已预览，等待确认执行", "idle")

    def execute(self, confirmed_fingerprint: str | None) -> None:
        if self.request is None:
            self.view.set_batch_status("拒绝执行：尚未导入", "error")
            return
        try:
            self.request.assert_confirmation(confirmed_fingerprint)
            self.view.set_batch_status("顺序规划中…", "running")
            state = run_batch(self.request, self.dataset, confirmed_fingerprint=confirmed_fingerprint)
            output = self.repository_root / "outputs" / "competition_batch" / self.request.batch_id
            write_batch_outputs(state, self.dataset, output)
            plan = build_batch_layer_plan(self.repository_root, self.request.batch_id)
            plan.validate_sources()
            self.map_port.load_plan(plan)
        except Exception as exc:
            self.view.set_batch_status("批次执行失败", "error")
            self.view.append_message("assistant", f"批次执行失败：{type(exc).__name__}: {exc}", "error")
            return
        self.last_state, self.output_dir = state, output
        self.view.set_batch_results(state["tasks"])
        counts = state["terminal_counts"]
        self.view.set_batch_status(f"完成：直接 {counts['completed_direct']} / 绕行 {counts['completed_rerouted']} / 待复核 {counts['needs_review']} / 失败 {counts['failed']}", "success")
        self.view.set_batch_export_enabled(True)

    def filter_status(self, status: str) -> None:
        self.map_port.filter_batch_tasks(status)
        self.view.filter_batch_results(status)

    def focus_task(self, task_id: str) -> None:
        self.map_port.focus_batch_task(task_id)

    def set_route_visibility(self, candidate_visible: bool, final_visible: bool) -> None:
        self.map_port.set_batch_route_visibility(candidate_visible, final_visible)

    def export_atlas(self) -> None:
        if self.last_state is None or self.output_dir is None:
            self.view.set_batch_status("没有可导出的批次结果", "error")
            return
        destination = self.output_dir / "design_book.pdf"
        try:
            self.map_port.export_batch_atlas(self.last_state, destination)
        except Exception as exc:
            self.view.set_batch_status("图册导出失败", "error")
            self.view.append_message("assistant", f"批量图册导出失败：{type(exc).__name__}: {exc}", "error")
            return
        self.view.set_batch_status("完整图册导出完成", "success")
        self.view.append_message("assistant", f"批量设计图册已导出：{destination}。竞赛样例/非正式施工图。", "success")
