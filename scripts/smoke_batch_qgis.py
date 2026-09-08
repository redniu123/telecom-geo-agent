"""Real PyQGIS/Qt interaction smoke for the explicit batch-design workflow."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from qgis.core import Qgis, QgsApplication, QgsProject


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class Canvas:
    def __init__(self):
        self.extents = []
        self.refresh_count = 0

    def setExtent(self, extent):  # noqa: N802 - QGIS API shape.
        self.extents.append(
            (
                extent.xMinimum(),
                extent.yMinimum(),
                extent.xMaximum(),
                extent.yMaximum(),
            )
        )

    def refresh(self):
        self.refresh_count += 1


class Iface:
    def __init__(self):
        self.canvas = Canvas()

    def mapCanvas(self):  # noqa: N802 - QGIS API shape.
        return self.canvas


def _connect_batch(dock, controller) -> None:
    dock.batch_sample_requested.connect(controller.select_builtin_sample)
    dock.batch_input_changed.connect(controller.invalidate_input)
    dock.batch_import_requested.connect(controller.import_csv)
    dock.batch_preview_requested.connect(controller.preview)
    dock.batch_execute_requested.connect(controller.execute)
    dock.batch_filter_requested.connect(controller.filter_status)
    dock.batch_focus_requested.connect(controller.focus_task)
    dock.batch_route_visibility_requested.connect(controller.set_route_visibility)


def main() -> int:
    app = QgsApplication([], False)
    app.initQgis()
    project = QgsProject.instance()
    try:
        from qgis_plugin.telecom_geo_agent.batch_controller import BatchController
        from qgis_plugin.telecom_geo_agent.dock_widget import AgentDockWidget
        from qgis_plugin.telecom_geo_agent.map_adapter import QgisMapAdapter

        iface = Iface()
        dock = AgentDockWidget()
        dock.resize(380, 820)
        dock.show()
        adapter = QgisMapAdapter(iface)
        controller = BatchController(dock, adapter, ROOT)
        _connect_batch(dock, controller)
        app.processEvents()

        # Startup is a real empty state: the source is advertised but not bound,
        # no task path is prefilled, and no plugin layer is added to the project.
        if controller.dataset is not None or adapter.layers:
            raise AssertionError("startup silently activated batch data")
        if dock._batch.path_edit.text() or dock._batch.execute_button.isEnabled():
            raise AssertionError("startup prefilled tasks or enabled execution")
        if dock._tabs.currentWidget() is not dock._batch:
            raise AssertionError("batch design is not the primary workflow tab")

        # The click, not controller construction, activates and displays input.
        dock._batch.sample_button.click()
        app.processEvents()
        if controller.dataset is None or len(adapter.layers) != 8:
            raise AssertionError("explicit sample selection did not load 8 input layers")
        if not dock._batch.path_edit.text().endswith("batch_tasks.csv"):
            raise AssertionError("sample selection did not reveal its task source")
        if "当前操作使用同一数据集" not in dock._batch.map_context_label.text():
            raise AssertionError("map/operation dataset identity is ambiguous")

        dock._batch.import_button.click()
        dock._batch.preview_button.click()
        app.processEvents()
        fingerprint = controller.request.fingerprint
        if not dock._batch.execute_button.isEnabled():
            raise AssertionError("valid preview did not enable execution")

        # A changed task source must immediately invalidate the old fingerprint.
        main_csv = dock._batch.path_edit.text()
        migration_csv = str(
            ROOT / "data" / "competition_batch" / "migration_tasks_10.csv"
        )
        dock._batch.path_edit.setText(migration_csv)
        app.processEvents()
        if dock._batch.execute_button.isEnabled() or controller.request is not None:
            raise AssertionError("changed task source retained stale confirmation")
        dock._batch.path_edit.setText(main_csv)
        dock._batch.import_button.click()
        dock._batch.preview_button.click()
        app.processEvents()
        if controller.request.fingerprint != fingerprint:
            raise AssertionError("restored identical input produced a different fingerprint")

        dock._batch.execute_button.click()
        app.processEvents()
        if dock._batch.table.rowCount() != 30 or len(adapter.layers) != 13:
            raise AssertionError("batch UI/layer count mismatch")
        if "411" not in dock._batch.dataset_meta_label.text():
            raise AssertionError("selected dataset did not display its actual loaded counts")
        if "completed_direct" in dock._batch.table.item(0, 2).text():
            raise AssertionError("result table leaked raw status enum instead of readable text")

        status_counts = {}
        for label, status, expected in (
            ("直接成功", "completed_direct", 19),
            ("绕行成功", "completed_rerouted", 9),
            ("待人工复核", "needs_review", 1),
            ("明确失败", "failed", 1),
        ):
            controller.filter_status(status)
            app.processEvents()
            status_counts[status] = dock._batch.table.rowCount()
            if dock._batch.table.rowCount() != expected:
                raise AssertionError(f"{label} filter returned wrong row count")
            if dock._batch.table.item(0, 2).text() != label:
                raise AssertionError(f"{label} filter did not use readable status text")

        controller.filter_status("all")
        app.processEvents()
        if not dock._batch.select_task("T002"):
            raise AssertionError("T002 could not be selected from result table")
        app.processEvents()
        if adapter.layers["batch_final"].selectedFeatureCount() != 1:
            raise AssertionError("task selection did not select/zoom final route")
        business_detail = "\n".join(
            (
                dock._batch.detail_business.text(),
                dock._batch.detail_issue.text(),
                dock._batch.detail_resource.text(),
                dock._batch.detail_outcome.text(),
            )
        )
        technical_detail = dock._batch.technical_text.toPlainText()
        if "T001" not in business_detail or "子管余量不足" not in business_detail:
            raise AssertionError("business detail omitted conflict meaning or source task")
        if "R_SUBDUCT_CAPACITY" not in technical_detail or "→" not in business_detail:
            raise AssertionError("expandable evidence omitted rule or resource before/after")
        if dock._batch.technical_text.isVisible():
            raise AssertionError("technical evidence should be collapsed by default")

        controller.set_route_visibility(True, False)
        root = project.layerTreeRoot()
        if not root.findLayer(adapter.layers["batch_candidates"].id()).isVisible():
            raise AssertionError("candidate-route visibility toggle failed")
        if root.findLayer(adapter.layers["batch_final"].id()).isVisible():
            raise AssertionError("final-route visibility toggle failed")
        controller.set_route_visibility(False, True)

        # Narrow dock keeps the essential task/priority/status columns and uses a
        # vertical scroll area instead of squeezing every field into one row.
        dock.resize(360, 720)
        app.processEvents()
        if not dock._batch.table.isColumnHidden(3) or not dock._batch.table.isColumnHidden(5):
            raise AssertionError("narrow dock did not collapse secondary columns")
        if dock._batch.table.isColumnHidden(0) or dock._batch.table.isColumnHidden(2):
            raise AssertionError("narrow dock hid essential task/status columns")
        if dock._batch.scroll.horizontalScrollBar().maximum() != 0:
            raise AssertionError("batch workspace requires horizontal scrolling")

        report = {
            "status": "PASS",
            "qgis_version": Qgis.QGIS_VERSION,
            "real_qt_batch_widget": True,
            "startup_dataset_selected": False,
            "startup_prefilled_task_path": False,
            "startup_plugin_layer_count": 0,
            "explicit_sample_input_layer_count": 8,
            "result_layer_count": len(adapter.layers),
            "table_rows": len(controller.last_state["tasks"]),
            "status_filter_counts": status_counts,
            "focused_task_id": "T002",
            "focused_final_route_count": adapter.layers[
                "batch_final"
            ].selectedFeatureCount(),
            "task_detail_business_first": True,
            "technical_evidence_collapsed_by_default": True,
            "stale_confirmation_rejected_after_path_change": True,
            "candidate_final_visibility_toggle": True,
            "narrow_dock_secondary_columns_collapsed": True,
            "narrow_dock_horizontal_workspace_scroll": False,
            "canvas_extent_updates": len(iface.canvas.extents),
            "visible_gui_user_acceptance": "pending_user",
        }
        target = (
            ROOT
            / "outputs"
            / "competition_batch"
            / "BATCH-MAIN-30"
            / "qgis_batch_smoke.json"
        )
        target.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        from competition.batch.outputs import refresh_checksums

        refresh_checksums(target.parent)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        adapter.clear_layers()
        dock.close()
        dock.deleteLater()
    finally:
        project.clear()
        app.exitQgis()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
