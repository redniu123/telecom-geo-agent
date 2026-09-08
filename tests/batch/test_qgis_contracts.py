import shutil
from pathlib import Path

from qgis_plugin.telecom_geo_agent.batch_controller import BatchController
from qgis_plugin.telecom_geo_agent.batch_layer_plan import (
    build_batch_input_layer_plan,
    build_batch_layer_plan,
)


ROOT = Path(__file__).resolve().parents[2]


def _temporary_batch_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    shutil.copytree(
        ROOT / "data" / "competition_batch",
        repository / "data" / "competition_batch",
    )
    return repository


class View:
    def __init__(self):
        self.available_descriptor = None
        self.selected_descriptor = None
        self.preview_value = None
        self.status = None
        self.results = None
        self.export_enabled = None
        self.default_csv = ""
        self.messages = []
        self.filters = []
        self.run_gate = None
        self.map_context = None
        self.busy = None
        self.task_summary = None
        self.export_path = None
        self.clear_results_count = 0
        self.clear_dataset_reason = None
        self.stage = None

    def configure_batch(self, descriptor):
        self.available_descriptor = descriptor

    def set_batch_dataset(self, descriptor, default_csv):
        self.selected_descriptor = descriptor
        self.default_csv = default_csv

    def clear_batch_dataset(self, reason):
        self.clear_dataset_reason = reason

    def set_batch_export_enabled(self, enabled):
        self.export_enabled = enabled

    def set_batch_export_path(self, path):
        self.export_path = path

    def set_batch_preview(self, text, fingerprint):
        self.preview_value = (text, fingerprint)

    def set_batch_status(self, text, state="idle"):
        self.status = (text, state)

    def set_batch_busy(self, busy, stage=""):
        self.busy = (busy, stage)

    def set_batch_run_gate(self, enabled, reason=""):
        self.run_gate = (enabled, reason)

    def set_batch_task_summary(self, summary):
        self.task_summary = summary

    def set_batch_map_context(self, text, state="idle"):
        self.map_context = (text, state)

    def show_batch_stage(self, stage):
        self.stage = stage

    def set_batch_results(self, tasks):
        self.results = tasks

    def clear_batch_results(self):
        self.results = None
        self.clear_results_count += 1

    def filter_batch_results(self, status):
        self.filters.append(status)

    def batch_csv_path(self):
        return self.default_csv

    def append_message(self, role, text, kind="info"):
        self.messages.append((role, text, kind))


class Map:
    def __init__(self):
        self.plan = None
        self.plans = []
        self.filters = []
        self.focuses = []
        self.route_visibility = []
        self.dataset_focus_count = 0
        self.clear_count = 0

    def load_plan(self, plan):
        self.plan = plan
        self.plans.append(plan)

    def show_batch_dataset(self):
        self.dataset_focus_count += 1

    def clear_layers(self):
        self.clear_count += 1

    def filter_batch_tasks(self, status):
        self.filters.append(status)

    def focus_batch_task(self, task_id):
        self.focuses.append(task_id)

    def set_batch_route_visibility(self, candidate_visible, final_visible):
        self.route_visibility.append((candidate_visible, final_visible))


def test_batch_layer_plans_are_portable_and_truthfully_named():
    input_plan = build_batch_input_layer_plan(ROOT, "sample_dataset")
    assert len(input_plan.layers) == 8
    assert input_plan.group_name == "批量设计输入 · sample_dataset"
    assert "合成" in input_plan.by_key("batch_rooms").name
    assert "3 个" not in input_plan.by_key("batch_rooms").name
    input_plan.validate_sources()

    result_plan = build_batch_layer_plan(ROOT, "BATCH-MAIN-30")
    assert len(result_plan.layers) == 13
    assert result_plan.group_name == "片区批量接入 · BATCH-MAIN-30"
    assert result_plan.by_key("batch_tasks").label_field == "task_id"
    assert result_plan.by_key("batch_final").relative_path.as_posix().endswith(
        "final_routes.geojson"
    )
    result_plan.validate_sources()


def test_controller_starts_empty_and_refuses_silent_sample_use():
    view, map_port = View(), Map()
    controller = BatchController(view, map_port, ROOT)

    assert controller.dataset is None
    assert controller.request is None
    assert map_port.plan is None
    assert view.default_csv == ""
    assert view.run_gate == (False, "尚未选择数据集")
    assert "未加载" in view.map_context[0]
    assert view.available_descriptor["dataset_id"].startswith("osm_shanghai")

    controller.import_csv(str(ROOT / "data" / "competition_batch" / "batch_tasks.csv"))
    assert controller.request is None
    assert view.status == ("拒绝导入：没有数据集", "error")


def test_explicit_sample_selection_reports_actual_counts_then_executes(tmp_path):
    repository = _temporary_batch_repository(tmp_path)
    view, map_port = View(), Map()
    controller = BatchController(view, map_port, repository)

    controller.select_builtin_sample()
    assert controller.dataset is not None
    assert len(map_port.plan.layers) == 8
    assert map_port.dataset_focus_count == 1
    assert view.default_csv.endswith("batch_tasks.csv")
    assert view.selected_descriptor["counts"] == {
        "nodes": len(controller.dataset.network.nodes),
        "edges": len(controller.dataset.network.edge_records),
        "rooms": len(controller.dataset.room_ids),
        "sites": len(controller.dataset.site_ids),
    }
    assert "当前操作使用同一数据集" in view.map_context[0]

    controller.import_csv(view.default_csv)
    assert view.task_summary["task_count"] == len(controller.request.tasks)
    assert view.task_summary["priorities"] == {"high": 10, "medium": 10, "low": 10}
    controller.preview()
    fingerprint = view.preview_value[1]
    assert fingerprint == controller.request.fingerprint
    assert view.run_gate == (True, "")

    controller.execute(fingerprint)
    assert len(view.results) == 30
    assert view.export_enabled is True
    assert map_port.plan.group_name.endswith("BATCH-MAIN-30")
    assert "真实运行结果" in view.map_context[0]

    controller.filter_status("failed")
    controller.focus_task("T002")
    controller.set_route_visibility(True, False)
    assert map_port.filters == ["failed"]
    assert view.filters == ["failed"]
    assert map_port.focuses == ["T002"]
    assert map_port.route_visibility == [(True, False)]


def test_changed_task_path_invalidates_confirmation_and_old_delivery():
    view, map_port = View(), Map()
    controller = BatchController(view, map_port, ROOT)
    controller.select_builtin_sample()
    controller.import_csv(view.default_csv)
    controller.preview()
    fingerprint = view.preview_value[1]

    changed = str(ROOT / "data" / "competition_batch" / "migration_tasks_10.csv")
    view.default_csv = changed
    controller.invalidate_input(changed)

    assert controller.request is None
    assert controller.last_state is None
    assert controller.output_dir is None
    assert view.export_enabled is False
    assert view.run_gate[0] is False
    assert "旧结果" in view.map_context[0]

    controller.execute(fingerprint)
    assert view.status == ("拒绝执行：尚未导入并预览任务", "error")
