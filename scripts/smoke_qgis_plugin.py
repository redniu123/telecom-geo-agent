"""Headless PyQGIS smoke for an extracted local plugin bundle.

Run this script with QGIS' own Python launcher. It exercises real PyQGIS
classes and the real P0 Workflow, but it is not a visual GUI acceptance test.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import zipfile
from pathlib import Path

from qgis.core import QgsApplication, QgsProject


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


def run_smoke(bundle: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="telecom-qgis-smoke-") as temporary:
        install_root = Path(temporary)
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
        default="dist/telecom_geo_agent-0.2.0.zip",
        help="待验证的插件 ZIP",
    )
    args = parser.parse_args()
    bundle = Path(args.bundle).resolve()
    if not bundle.is_file():
        parser.error(f"插件 ZIP 不存在：{bundle}")

    app = QgsApplication([], False)
    app.initQgis()
    try:
        run_smoke(bundle)
    finally:
        app.exitQgis()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
