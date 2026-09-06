"""Headless PyQGIS smoke for an extracted local plugin bundle.

Run this script with QGIS' own Python launcher. It exercises real PyQGIS
classes and the real P0 Workflow, but it is not a visual GUI acceptance test.
"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from qgis.core import Qgis, QgsApplication, QgsProject


DEFAULT_REQUEST = "从A到B规划24芯光缆"


class HeadlessCanvas:
    def __init__(self) -> None:
        self.extent_updates = 0
        self.refreshes = 0

    def setExtent(self, _extent) -> None:  # noqa: N802 - QGIS API shape.
        self.extent_updates += 1

    def refresh(self) -> None:
        self.refreshes += 1


class HeadlessIface:
    """Record QGIS host calls while real QAction/QDockWidget classes execute."""

    def __init__(self) -> None:
        self.canvas = HeadlessCanvas()
        self.registered: list[str] = []
        self.removed: list[str] = []

    def mainWindow(self):  # noqa: N802 - QGIS iface shape.
        return None

    def mapCanvas(self):  # noqa: N802 - QGIS iface shape.
        return self.canvas

    def addPluginToMenu(self, *_args) -> None:  # noqa: N802
        self.registered.append("menu")

    def removePluginMenu(self, *_args) -> None:  # noqa: N802
        self.removed.append("menu")

    def addToolBarIcon(self, *_args) -> None:  # noqa: N802
        self.registered.append("toolbar")

    def removeToolBarIcon(self, *_args) -> None:  # noqa: N802
        self.removed.append("toolbar")

    def addDockWidget(self, *_args) -> None:  # noqa: N802
        self.registered.append("dock")

    def removeDockWidget(self, *_args) -> None:  # noqa: N802
        self.removed.append("dock")


def _visible(plugin, key: str) -> bool:
    layer = plugin.map_adapter.layers[key]
    tree_layer = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
    if tree_layer is None:
        raise AssertionError(f"missing layer tree item: {key}")
    return tree_layer.itemVisibilityChecked()


def run_smoke(
    bundle: Path, install_root: Path, export_pdf: Path | None = None
) -> None:
    # The caller owns cleanup so it can release QGIS/OGR providers first.
    with nullcontext(install_root):
        with zipfile.ZipFile(bundle) as archive:
            archive.extractall(install_root)
        sys.path.insert(0, str(install_root))

        import telecom_geo_agent

        iface = HeadlessIface()
        plugin = telecom_geo_agent.classFactory(iface)
        plugin.initGui()
        try:
            plugin.controller.handle_user_input(DEFAULT_REQUEST)
            state = plugin.controller.last_state
            assert state is not None and state["status"] == "completed"
            assert state["first_route"]["edge_ids"] == ["D001", "D017", "D003"]
            assert state["final_route"]["edge_ids"] == ["N001", "N002"]
            assert state["validation_history"][0]["passed"] is False
            assert state["validation_history"][1] == {
                "passed": True,
                "violations": [],
            }
            assert state["bom_result"]["recommended_cable_length_m"] == 440.0
            assert set(plugin.map_adapter.layers) == {
                "network",
                "sites",
                "first_route",
                "final_route",
                "issue_d017",
            }
            assert plugin.map_adapter.layers["issue_d017"].featureCount() == 1
            assert not _visible(plugin, "first_route")
            assert _visible(plugin, "final_route")

            plugin.controller.handle_user_input("显示第一次路线")
            assert _visible(plugin, "first_route")
            assert not _visible(plugin, "final_route")
            plugin.controller.handle_user_input("显示最终路线")
            assert not _visible(plugin, "first_route")
            assert _visible(plugin, "final_route")
            plugin.controller.handle_user_input("定位问题段")
            assert plugin.map_adapter.layers["issue_d017"].selectedFeatureCount() == 1

            print("main_case=PASS")
            print("first_route=D001,D017,D003")
            print("final_route=N001,N002")
            print("recommended_cable_length_m=440.0")

            plugin.controller.handle_user_input("从A到B规划12芯光缆")
            no_repair = plugin.controller.last_state
            assert no_repair["status"] == "completed"
            assert no_repair["repair_count"] == 0
            assert no_repair["first_route"] is no_repair["final_route"]
            assert len(plugin.map_adapter.layers) == 4
            assert "issue_d017" not in plugin.map_adapter.layers
            print("no_repair_case=PASS")

            plugin.controller.handle_user_input("从A到B规划64芯光缆")
            failed = plugin.controller.last_state
            assert failed["status"] == "failed"
            assert failed["bom_result"] is None
            assert plugin.map_adapter.layers["issues"].featureCount() == 3
            assert plugin.map_adapter.layers["final_route"].name().endswith("（未通过）")
            plugin.controller.handle_user_input("定位问题段")
            assert plugin.map_adapter.layers["issues"].selectedFeatureCount() == 1
            print("failed_case_with_evidence=PASS")

            plugin.controller.handle_user_input("从A到C规划24芯光缆")
            parse_failed = plugin.controller.last_state
            assert parse_failed["status"] == "failed"
            assert parse_failed["first_route"] is None
            assert not QgsProject.instance().mapLayers()
            print("parse_failure_clears_stale_layers=PASS")

            from competition.catalog import parameters_for_scenario

            capacity = parameters_for_scenario(
                plugin.controller.competition.repository_root,
                "capacity_reroute",
            )
            plugin.controller.preview_competition(capacity.as_dict())
            plugin.controller.execute_competition(
                capacity.as_dict(), capacity.fingerprint
            )
            competition_state = plugin.controller.competition.last_state
            assert competition_state["status"] == "completed"
            assert competition_state["validation_history"][0]["violations"][0][
                "asset_id"
            ] == "C1-017"
            assert competition_state["validation_history"][-1]["passed"] is True
            assert "C1-017" not in competition_state["final_route"]["edge_ids"]
            assert set(plugin.map_adapter.layers) == {
                "landuse",
                "buildings",
                "water",
                "railways",
                "roads",
                "candidate_channels",
                "rooms",
                "base_stations",
                "candidate_route",
                "issues",
                "final_route",
            }
            assert plugin.map_adapter.layers["candidate_channels"].featureCount() == 79
            assert (
                plugin.map_adapter.layers["candidate_channels"].geometryType()
                == Qgis.GeometryType.Line
            )
            assert plugin.map_adapter.layers["buildings"].featureCount() == 848
            assert plugin.map_adapter.layers["issues"].featureCount() == 1
            assert not _visible(plugin, "candidate_route")
            assert _visible(plugin, "final_route")
            layout_pdf = install_root / "competition_capacity_A3.pdf"
            plugin.map_adapter.export_competition_pdf(
                competition_state, layout_pdf, paper_size="A3"
            )
            assert layout_pdf.is_file() and layout_pdf.stat().st_size > 10_000
            if export_pdf is not None:
                export_pdf.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(layout_pdf, export_pdf)
            print(f"competition_capacity=PASS pdf_bytes={layout_pdf.stat().st_size}")

            no_path = parameters_for_scenario(
                plugin.controller.competition.repository_root,
                "no_path",
            )
            plugin.controller.preview_competition(no_path.as_dict())
            plugin.controller.execute_competition(no_path.as_dict(), no_path.fingerprint)
            failed_competition = plugin.controller.competition.last_state
            assert failed_competition["status"] == "failed"
            assert failed_competition["final_route"] is None
            assert failed_competition["bom_result"] is None
            assert "no route" in failed_competition["error"]
            assert "final_route" not in plugin.map_adapter.layers
            print("competition_no_path=EXPECTED_FAIL_WITH_EVIDENCE")

            batch = plugin.controller.batch
            batch_csv = (
                batch.repository_root
                / "data"
                / "competition_batch"
                / "batch_tasks.csv"
            )
            plugin.controller.import_batch(str(batch_csv))
            plugin.controller.preview_batch()
            plugin.controller.execute_batch(batch.request.fingerprint)
            batch_state = batch.last_state
            assert batch_state is not None and batch_state["task_count"] == 30
            assert batch_state["terminal_counts"] == {
                "completed_direct": 19,
                "completed_rerouted": 9,
                "failed": 1,
                "needs_review": 1,
            }
            assert len(plugin.map_adapter.layers) == 13
            plugin.controller.filter_batch("failed")
            assert plugin.dock._batch.table.rowCount() == 1
            assert plugin.map_adapter.layers["batch_tasks"].featureCount() == 1
            plugin.controller.filter_batch("all")
            plugin.controller.focus_batch("T002")
            assert plugin.map_adapter.layers["batch_final"].selectedFeatureCount() == 1
            plugin.dock._batch._show_task_detail("T002")
            detail = plugin.dock._batch.detail_text.toPlainText()
            assert "T001" in detail and "R_SUBDUCT_CAPACITY" in detail and "→" in detail
            plugin.controller.set_batch_route_visibility(True, False)
            assert _visible(plugin, "batch_candidates")
            assert not _visible(plugin, "batch_final")
            plugin.controller.set_batch_route_visibility(False, True)
            assert not _visible(plugin, "batch_candidates")
            assert _visible(plugin, "batch_final")
            print("batch_30_installed_bundle=PASS")
            print("batch_filter_focus_conflict_resource_visibility=PASS")
            print(f"extent_updates={iface.canvas.extent_updates}")
        finally:
            plugin.unload()
        assert iface.registered == ["menu", "toolbar", "dock"]
        assert iface.removed == ["menu", "toolbar", "dock"]
        assert not QgsProject.instance().mapLayers()
        print("unload_layers=0")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="用 QGIS Python 对本地插件 ZIP 做无界面边界 smoke"
    )
    parser.add_argument(
        "--bundle",
        default="dist/telecom_geo_agent-0.4.0.zip",
        help="待验证的插件 ZIP",
    )
    parser.add_argument(
        "--export-pdf",
        type=Path,
        help="可选：把 smoke 中真实导出的容量场景 A3 图纸复制到该路径",
    )
    args = parser.parse_args()
    bundle = Path(args.bundle).resolve()
    if not bundle.is_file():
        parser.error(f"插件 ZIP 不存在：{bundle}")

    install_root = Path(tempfile.mkdtemp(prefix="telecom-qgis-smoke-")).resolve()
    expected_parent = Path(tempfile.gettempdir()).resolve()
    if install_root.parent != expected_parent or not install_root.name.startswith(
        "telecom-qgis-smoke-"
    ):
        raise RuntimeError(f"拒绝使用未验证的临时目录：{install_root}")
    app = QgsApplication([], False)
    app.initQgis()
    try:
        run_smoke(
            bundle,
            install_root,
            args.export_pdf.resolve() if args.export_pdf else None,
        )
    finally:
        app.exitQgis()
        shutil.rmtree(install_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
