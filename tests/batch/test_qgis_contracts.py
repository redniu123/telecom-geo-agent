from pathlib import Path

from qgis_plugin.telecom_geo_agent.batch_controller import BatchController
from qgis_plugin.telecom_geo_agent.batch_layer_plan import build_batch_layer_plan


ROOT = Path(__file__).resolve().parents[2]


class View:
    def __init__(self):
        self.preview_value = None
        self.status = None
        self.results = None
        self.export_enabled = None
        self.default_csv = None
        self.messages = []
        self.filters = []

    def configure_batch(self, dataset_id, default_csv):
        self.dataset_id, self.default_csv = dataset_id, default_csv

    def set_batch_export_enabled(self, enabled):
        self.export_enabled = enabled

    def set_batch_preview(self, text, fingerprint):
        self.preview_value = (text, fingerprint)

    def set_batch_status(self, text, state="idle"):
        self.status = (text, state)

    def set_batch_results(self, tasks):
        self.results = tasks

    def filter_batch_results(self, status):
        self.filters.append(status)

    def batch_csv_path(self):
        return self.default_csv

    def append_message(self, role, text, kind="info"):
        self.messages.append((role, text, kind))


class Map:
    def __init__(self):
        self.plan = None
        self.filters = []
        self.focuses = []
        self.route_visibility = []

    def load_plan(self, plan):
        self.plan = plan

    def filter_batch_tasks(self, status):
        self.filters.append(status)

    def focus_batch_task(self, task_id):
        self.focuses.append(task_id)

    def set_batch_route_visibility(self, candidate_visible, final_visible):
        self.route_visibility.append((candidate_visible, final_visible))


def test_batch_layer_plan_has_portable_complete_stack():
    plan = build_batch_layer_plan(ROOT, "BATCH-MAIN-30")
    assert len(plan.layers) == 13
    assert plan.group_name == "片区批量接入 · BATCH-MAIN-30"
    assert plan.by_key("batch_tasks").label_field == "task_id"
    assert plan.by_key("batch_final").relative_path.as_posix().endswith("final_routes.geojson")
    plan.validate_sources()


def test_batch_controller_preview_execute_filter_and_focus():
    view, map_port = View(), Map()
    controller = BatchController(view, map_port, ROOT)
    controller.import_csv(view.default_csv)
    controller.preview()
    fingerprint = view.preview_value[1]
    assert fingerprint == controller.request.fingerprint
    controller.execute(fingerprint)
    assert len(view.results) == 30
    assert view.export_enabled is True
    assert map_port.plan.group_name.endswith("BATCH-MAIN-30")
    controller.filter_status("failed")
    controller.focus_task("T002")
    controller.set_route_visibility(True, False)
    assert map_port.filters == ["failed"]
    assert view.filters == ["failed"]
    assert map_port.focuses == ["T002"]
    assert map_port.route_visibility == [(True, False)]
