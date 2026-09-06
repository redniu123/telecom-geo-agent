"""Real PyQGIS smoke for batch UI, 13 layers, filtering and task focus."""

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

    def setExtent(self, extent):
        self.extents.append((extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()))

    def refresh(self):
        self.refresh_count += 1


class Iface:
    def __init__(self):
        self.canvas = Canvas()

    def mapCanvas(self):
        return self.canvas


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
        adapter = QgisMapAdapter(iface)
        controller = BatchController(dock, adapter, ROOT)
        csv_path = ROOT / "data" / "competition_batch" / "batch_tasks.csv"
        controller.import_csv(str(csv_path))
        controller.preview()
        fingerprint = controller.request.fingerprint
        controller.execute(fingerprint)
        if dock._batch.table.rowCount() != 30 or len(adapter.layers) != 13:
            raise AssertionError("batch UI/layer count mismatch")
        controller.filter_status("failed")
        failed_count = adapter.layers["batch_tasks"].featureCount()
        if failed_count != 1:
            raise AssertionError(f"failed filter returned {failed_count}, expected 1")
        if dock._batch.table.rowCount() != 1:
            raise AssertionError("failed filter did not reduce the visible task table")
        controller.filter_status("all")
        controller.focus_task("T002")
        if not iface.canvas.extents or adapter.layers["batch_final"].selectedFeatureCount() != 1:
            raise AssertionError("task focus did not select/zoom final route")
        dock._batch._show_task_detail("T002")
        detail = dock._batch.detail_text.toPlainText()
        if "T001" not in detail or "R_SUBDUCT_CAPACITY" not in detail or "→" not in detail:
            raise AssertionError("task detail omitted conflict cause or resource before/after evidence")
        controller.set_route_visibility(True, False)
        root = project.layerTreeRoot()
        if not root.findLayer(adapter.layers["batch_candidates"].id()).isVisible():
            raise AssertionError("candidate-route visibility toggle failed")
        if root.findLayer(adapter.layers["batch_final"].id()).isVisible():
            raise AssertionError("final-route visibility toggle failed")
        controller.set_route_visibility(False, True)
        report = {
            "status": "PASS",
            "qgis_version": Qgis.QGIS_VERSION,
            "real_qt_batch_widget": True,
            "table_rows": dock._batch.table.rowCount(),
            "loaded_layer_count": len(adapter.layers),
            "failed_filter_feature_count": failed_count,
            "focused_task_id": "T002",
            "focused_final_route_count": adapter.layers["batch_final"].selectedFeatureCount(),
            "task_detail_conflict_cause_present": True,
            "task_detail_resource_before_after_present": True,
            "candidate_final_visibility_toggle": True,
            "canvas_extent_updates": len(iface.canvas.extents),
            "visible_gui_user_acceptance": "pending_user",
        }
        target = ROOT / "outputs" / "competition_batch" / "BATCH-MAIN-30" / "qgis_batch_smoke.json"
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
