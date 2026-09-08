"""Stateful batch controller with an explicit, fail-closed dataset gate."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from competition.batch.data_loader import BatchDataset, load_batch_dataset
from competition.batch.outputs import write_batch_outputs
from competition.batch.planner import run_batch
from competition.batch.task_import import import_tasks_csv

from .batch_layer_plan import build_batch_input_layer_plan, build_batch_layer_plan


class BatchController:
    """Coordinate the five-stage UI without selecting data at startup."""

    def __init__(self, view, map_port, repository_root: str | Path) -> None:
        self.view = view
        self.map_port = map_port
        self.repository_root = Path(repository_root).resolve()
        self.dataset: BatchDataset | None = None
        self.request = None
        self.last_state = None
        self.output_dir: Path | None = None
        self._imported_path: Path | None = None
        self._available_descriptor = self._manifest_descriptor()

        self.view.configure_batch(self._available_descriptor)
        self.view.set_batch_export_enabled(False)
        self.view.set_batch_run_gate(False, "尚未选择数据集")
        self.view.set_batch_map_context("QGIS 项目显示：未加载本插件数据", "idle")

    def _manifest_descriptor(self) -> dict:
        """Read only the source catalog; this does not activate the dataset."""

        manifest_path = self.repository_root / "data" / "competition_batch" / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "name": "内置批量样例（清单不可读）",
                "dataset_id": "unavailable",
                "source_summary": f"manifest 读取失败：{type(exc).__name__}: {exc}",
                "attribution": "待数据校验",
            }
        return {
            "name": manifest.get("dataset_name", "内置批量样例"),
            "dataset_id": manifest.get("dataset_id", "unknown"),
            "source_dataset_id": manifest.get("source_dataset_id", "unknown"),
            "source_summary": (
                "真实公开 OSM 背景 + 公开道路几何派生候选走廊 + 合成通信设施与资源"
            ),
            "attribution": manifest.get(
                "required_attribution", "© OpenStreetMap contributors / ODbL 1.0"
            ),
        }

    @staticmethod
    def _feature_count(manifest: dict, relative_path: str) -> int | str:
        value = manifest.get("generated_files", {}).get(relative_path, {}).get("feature_count")
        return value if isinstance(value, int) else "—"

    def _selected_descriptor(self, dataset: BatchDataset) -> dict:
        manifest = dataset.manifest
        return {
            **self._available_descriptor,
            "name": manifest.get("dataset_name", dataset.dataset_id),
            "dataset_id": dataset.dataset_id,
            "source_dataset_id": manifest.get("source_dataset_id", "unknown"),
            "attribution": manifest.get(
                "required_attribution", "© OpenStreetMap contributors / ODbL 1.0"
            ),
            "counts": {
                "nodes": len(dataset.network.nodes),
                "edges": len(dataset.network.edge_records),
                "rooms": len(dataset.room_ids),
                "sites": len(dataset.site_ids),
            },
            "public_counts": {
                "roads": self._feature_count(manifest, "background/roads.geojson"),
                "buildings": self._feature_count(manifest, "background/buildings.geojson"),
                "water": self._feature_count(manifest, "background/water.geojson"),
                "landuse": self._feature_count(manifest, "background/landuse.geojson"),
                "railways": self._feature_count(manifest, "background/railways.geojson"),
            },
        }

    def _show_input_layers(self) -> None:
        if self.dataset is None:
            raise RuntimeError("尚未选择批量数据集")
        plan = build_batch_input_layer_plan(
            self.repository_root,
            self.dataset.dataset_id,
        )
        plan.validate_sources()
        self.map_port.load_plan(plan)
        show_dataset = getattr(self.map_port, "show_batch_dataset", None)
        if show_dataset is not None:
            show_dataset()
        self.view.set_batch_map_context(
            f"QGIS 项目显示：{self.dataset.dataset_id} 的输入图层（{len(plan.layers)} 层，尚未运行）；"
            "当前操作使用同一数据集。",
            "selected",
        )

    def select_builtin_sample(self) -> None:
        """Activate the bundled sample only after an explicit UI click."""

        self.view.set_batch_busy(True, "dataset")
        self.view.set_batch_export_enabled(False)
        try:
            dataset = load_batch_dataset(self.repository_root)
            self.dataset = dataset
            self.request = None
            self.last_state = None
            self.output_dir = None
            self._imported_path = None
            self._show_input_layers()
        except Exception as exc:
            self.dataset = None
            self.request = None
            self.last_state = None
            self.output_dir = None
            self._imported_path = None
            clear_layers = getattr(self.map_port, "clear_layers", None)
            if clear_layers is not None:
                clear_layers()
            self.view.clear_batch_dataset(
                f"内置样例未启用：{type(exc).__name__}: {exc}"
            )
            self.view.set_batch_busy(False)
            self.view.set_batch_status("数据集校验失败", "error")
            self.view.append_message(
                "assistant",
                f"批量数据集校验失败：{type(exc).__name__}: {exc}",
                "error",
            )
            return

        descriptor = self._selected_descriptor(dataset)
        default_csv = str(dataset.root / "batch_tasks.csv")
        self.view.set_batch_dataset(descriptor, default_csv)
        # set_batch_dataset resets the map label, so restate the loaded context.
        input_layer_count = len(
            build_batch_input_layer_plan(
                self.repository_root,
                dataset.dataset_id,
            ).layers
        )
        self.view.set_batch_map_context(
            f"QGIS 项目显示：{dataset.dataset_id} 的输入图层（{input_layer_count} 层，尚未运行）；"
            "当前操作使用同一数据集。",
            "selected",
        )
        self.view.set_batch_busy(False)
        self.view.set_batch_status("数据就绪，等待任务导入", "success")
        self.view.set_batch_run_gate(False, "任务表尚未导入并确认")
        self.view.show_batch_stage("data")

    @staticmethod
    def _resolved_input(path: str) -> Path:
        if not path or not path.strip():
            raise ValueError("请选择批量任务 CSV")
        return Path(path).expanduser().resolve()

    def invalidate_input(self, path: str) -> None:
        """Invalidate controller state when the task source is edited."""

        if self.dataset is None or self._imported_path is None:
            return
        try:
            current = self._resolved_input(path)
        except Exception:
            current = None
        if current == self._imported_path:
            return
        self.request = None
        self._imported_path = None
        self.last_state = None
        self.output_dir = None
        self.view.set_batch_task_summary(None)
        self.view.set_batch_run_gate(False, "任务输入已变化，必须重新导入并预览")
        self.view.set_batch_export_enabled(False)
        self.view.set_batch_map_context(
            "QGIS 项目仍显示上次加载内容；当前任务输入已变化，不能将旧结果作为本次输出。",
            "error",
        )
        self.view.set_batch_status("任务输入已变化", "idle")

    def import_csv(self, path: str) -> None:
        if self.dataset is None:
            self.view.set_batch_preview("请先明确选择并加载一个数据集。", None)
            self.view.set_batch_status("拒绝导入：没有数据集", "error")
            self.view.set_batch_run_gate(False, "尚未选择数据集")
            return

        self.view.set_batch_busy(True, "import")
        try:
            resolved = self._resolved_input(path)
            request = import_tasks_csv(
                resolved,
                dataset_id=self.dataset.dataset_id,
                known_site_ids=self.dataset.site_ids,
                known_room_ids=self.dataset.room_ids,
                known_asset_ids=set(self.dataset.resources),
            )
            self.request = request
            self._imported_path = resolved
            self.last_state = None
            self.output_dir = None
            self._show_input_layers()
        except Exception as exc:
            self.request = None
            self._imported_path = None
            self.view.set_batch_preview(
                f"导入失败：{type(exc).__name__}: {exc}", None
            )
            self.view.set_batch_task_summary(None)
            self.view.set_batch_busy(False)
            self.view.set_batch_status("CSV 校验失败", "error")
            self.view.set_batch_run_gate(False, "任务表未通过校验")
            return

        priorities = Counter(task.priority for task in request.tasks)
        self.view.clear_batch_results()
        self.view.set_batch_export_path(None)
        self.view.set_batch_task_summary(
            {
                "batch_id": request.batch_id,
                "task_count": len(request.tasks),
                "priorities": dict(priorities),
            }
        )
        self.view.set_batch_preview(
            f"CSV 字段与引用校验通过，共 {len(request.tasks)} 个任务。\n"
            "尚未生成确认指纹；请继续预览任务。",
            None,
        )
        self.view.set_batch_busy(False)
        self.view.set_batch_status("任务导入通过，等待预览", "success")
        self.view.set_batch_run_gate(False, "任务已导入，但尚未预览确认")
        self.view.show_batch_stage("tasks")

    def preview(self) -> None:
        if self.dataset is None:
            self.view.set_batch_preview("请先明确选择并加载一个数据集。", None)
            self.view.set_batch_status("拒绝预览：没有数据集", "error")
            return
        try:
            current_path = self._resolved_input(self.view.batch_csv_path())
        except Exception as exc:
            self.view.set_batch_preview(f"无法预览：{exc}", None)
            self.view.set_batch_status("任务路径无效", "error")
            return
        if self.request is None or self._imported_path != current_path:
            self.import_csv(str(current_path))
        if self.request is None:
            return
        self.view.set_batch_preview(
            self.request.preview_text(), self.request.fingerprint
        )
        self.view.set_batch_status("批次已预览，等待确认执行", "success")
        self.view.set_batch_run_gate(True, "")
        self.view.show_batch_stage("tasks")

    def execute(self, confirmed_fingerprint: str | None) -> None:
        if self.dataset is None:
            self.view.set_batch_status("拒绝执行：尚未选择数据集", "error")
            self.view.set_batch_run_gate(False, "尚未选择数据集")
            return
        if self.request is None or self._imported_path is None:
            self.view.set_batch_status("拒绝执行：尚未导入并预览任务", "error")
            self.view.set_batch_run_gate(False, "任务尚未导入并预览")
            return
        try:
            if self._resolved_input(self.view.batch_csv_path()) != self._imported_path:
                raise RuntimeError("任务输入已变化，旧确认不可复用")
            self.request.assert_confirmation(confirmed_fingerprint)
        except Exception as exc:
            self.view.set_batch_status("拒绝执行：确认已失效", "error")
            self.view.set_batch_run_gate(False, str(exc))
            return

        self.view.set_batch_export_enabled(False)
        self.view.set_batch_busy(True, "run")
        try:
            state = run_batch(
                self.request,
                self.dataset,
                confirmed_fingerprint=confirmed_fingerprint,
            )
            output = (
                self.repository_root
                / "outputs"
                / "competition_batch"
                / self.request.batch_id
            )
            write_batch_outputs(state, self.dataset, output)
            plan = build_batch_layer_plan(self.repository_root, self.request.batch_id)
            plan.validate_sources()
            self.map_port.load_plan(plan)
        except Exception as exc:
            self.view.set_batch_busy(False)
            self.view.set_batch_status("批次执行失败", "error")
            self.view.set_batch_run_gate(True, "")
            self.view.append_message(
                "assistant",
                f"批次执行失败：{type(exc).__name__}: {exc}",
                "error",
            )
            return

        self.last_state, self.output_dir = state, output
        self.view.set_batch_results(state["tasks"])
        counts = state["terminal_counts"]
        self.view.set_batch_busy(False)
        self.view.set_batch_status(
            f"完成：直接 {counts['completed_direct']} / 绕行 {counts['completed_rerouted']} / "
            f"待复核 {counts['needs_review']} / 失败 {counts['failed']}",
            "success",
        )
        self.view.set_batch_map_context(
            f"QGIS 项目显示：数据集 {state['dataset_id']} / 批次 {state['batch_id']} 的真实运行结果"
            f"（{len(plan.layers)} 层）；任务表与地图使用同一结果。",
            "success",
        )
        self.view.set_batch_run_gate(True, "")
        self.view.set_batch_export_enabled(True)
        self.view.show_batch_stage("run")

    def filter_status(self, status: str) -> None:
        if self.last_state is None:
            return
        try:
            self.map_port.filter_batch_tasks(status)
            self.view.filter_batch_results(status)
            self.view.show_batch_stage("review")
        except Exception as exc:
            self.view.set_batch_status(f"状态筛选失败：{exc}", "error")

    def focus_task(self, task_id: str) -> None:
        if self.last_state is None:
            return
        try:
            self.map_port.focus_batch_task(task_id)
            self.view.set_batch_status(f"已在地图定位任务 {task_id}", "success")
        except Exception as exc:
            self.view.set_batch_status(f"任务定位失败：{exc}", "error")

    def set_route_visibility(
        self, candidate_visible: bool, final_visible: bool
    ) -> None:
        if self.last_state is None:
            return
        try:
            self.map_port.set_batch_route_visibility(
                candidate_visible, final_visible
            )
        except Exception as exc:
            self.view.set_batch_status(f"路线显隐切换失败：{exc}", "error")

    def export_atlas(self) -> None:
        if self.last_state is None or self.output_dir is None:
            self.view.set_batch_status("没有可导出的当前批次结果", "error")
            return
        destination = self.output_dir / "design_book.pdf"
        self.view.set_batch_export_enabled(False)
        self.view.set_batch_busy(True, "export")
        try:
            exported = self.map_port.export_batch_atlas(
                self.last_state, destination
            )
            if not Path(exported).is_file():
                raise RuntimeError("QGIS 报告导出完成，但目标 PDF 不存在")
        except Exception as exc:
            self.view.set_batch_busy(False)
            self.view.set_batch_export_enabled(True)
            self.view.set_batch_status("图册导出失败", "error")
            self.view.append_message(
                "assistant",
                f"批量图册导出失败：{type(exc).__name__}: {exc}",
                "error",
            )
            return
        self.view.set_batch_busy(False)
        self.view.set_batch_export_enabled(True)
        self.view.set_batch_export_path(str(exported))
        self.view.set_batch_status("完整图册与 GeoPackage 导出完成", "success")
        self.view.show_batch_stage("export")
        self.view.append_message(
            "assistant",
            f"批量设计图册已导出：{exported}。竞赛样例/非正式施工图。",
            "success",
        )
