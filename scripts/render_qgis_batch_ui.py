"""Render and measure the real Qt/QGIS batch dock for automated visual QA."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QMainWindow
from qgis.core import QgsApplication, QgsProject
from qgis.gui import QgsMapCanvas


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class RenderIface:
    def __init__(self, window: QMainWindow, canvas: QgsMapCanvas) -> None:
        self._window = window
        self._canvas = canvas

    def mainWindow(self):  # noqa: N802 - QGIS API shape.
        return self._window

    def mapCanvas(self):  # noqa: N802 - QGIS API shape.
        return self._canvas


def _connect_batch(dock, controller) -> None:
    dock.batch_sample_requested.connect(controller.select_builtin_sample)
    dock.batch_input_changed.connect(controller.invalidate_input)
    dock.batch_import_requested.connect(controller.import_csv)
    dock.batch_preview_requested.connect(controller.preview)
    dock.batch_execute_requested.connect(controller.execute)
    dock.batch_filter_requested.connect(controller.filter_status)
    dock.batch_focus_requested.connect(controller.focus_task)
    dock.batch_route_visibility_requested.connect(controller.set_route_visibility)


def _sync_canvas(canvas: QgsMapCanvas, adapter) -> None:
    visible = []
    root = QgsProject.instance().layerTreeRoot()
    for layer in adapter.layers.values():
        node = root.findLayer(layer.id())
        if node is not None and node.isVisible():
            visible.append(layer)
    canvas.setLayers(visible)
    if "batch_channels" in adapter.layers:
        layer = adapter.layers["batch_channels"]
        layer.updateExtents()
        canvas.setExtent(layer.extent())
    canvas.refresh()
    canvas.waitWhileRendering()
    QgsApplication.processEvents()


def _save(widget, path: Path) -> dict:
    QgsApplication.processEvents()
    image = widget.grab()
    if image.isNull() or not image.save(str(path), "PNG"):
        raise RuntimeError(f"无法保存界面截图：{path}")
    return {
        "file": path.name,
        "pixel_width": image.width(),
        "pixel_height": image.height(),
        "device_pixel_ratio": image.devicePixelRatio(),
        "bytes": path.stat().st_size,
    }


def _button_measurement(button) -> dict:
    return {
        "text": button.text(),
        "width": button.width(),
        "size_hint_width": button.sizeHint().width(),
        "height": button.height(),
        "size_hint_height": button.sizeHint().height(),
        "enabled": button.isEnabled(),
        "text_fits_size_hint": button.width() >= button.sizeHint().width(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="自动渲染真实 QGIS 批量设计 Dock")
    parser.add_argument("--output-dir", default="outputs/ui_validation")
    parser.add_argument("--tag", default="100pct")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    app = QgsApplication([], True)
    app.initQgis()
    project = QgsProject.instance()
    qt_platform = os.environ.get("QT_QPA_PLATFORM", "default")
    report: dict = {
        "status": "RUNNING",
        "validation_type": (
            "automated_native_qt_qgis_render"
            if qt_platform == "default"
            else "automated_offscreen_qt_qgis_render"
        ),
        "not_user_visible_acceptance": True,
        "qt_platform": qt_platform,
        "qt_scale_factor": os.environ.get("QT_SCALE_FACTOR", "default"),
        "tag": args.tag,
        "screenshots": [],
    }
    try:
        from qgis_plugin.telecom_geo_agent.batch_controller import BatchController
        from qgis_plugin.telecom_geo_agent.dock_widget import AgentDockWidget
        from qgis_plugin.telecom_geo_agent.map_adapter import QgisMapAdapter

        window = QMainWindow()
        window.setWindowTitle("QGIS · 通信工程 Agent UI 自动验证")
        canvas = QgsMapCanvas(window)
        canvas.setCanvasColor(QColor("#10151D"))
        window.setCentralWidget(canvas)
        iface = RenderIface(window, canvas)
        dock = AgentDockWidget(window)
        window.addDockWidget(Qt.RightDockWidgetArea, dock)
        adapter = QgisMapAdapter(iface)
        controller = BatchController(dock, adapter, ROOT)
        _connect_batch(dock, controller)

        window.resize(1280, 900)
        window.show()
        window.resizeDocks([dock], [440], Qt.Horizontal)
        QgsApplication.processEvents()

        if controller.dataset is not None or adapter.layers:
            raise AssertionError("空状态渲染前已经绑定数据")
        report["screenshots"].append(
            _save(window, output_dir / f"batch_ui_empty_{args.tag}.png")
        )

        dock._batch.sample_button.click()
        dock._batch.import_button.click()
        dock._batch.preview_button.click()
        _sync_canvas(canvas, adapter)
        dock._batch.show_stage("tasks")
        QgsApplication.processEvents()
        report["screenshots"].append(
            _save(window, output_dir / f"batch_ui_preview_{args.tag}.png")
        )

        dock._batch.execute_button.click()
        _sync_canvas(canvas, adapter)
        if not dock._batch.select_task("T002"):
            raise AssertionError("结果复核截图无法选择 T002")
        _sync_canvas(canvas, adapter)
        dock._batch.scroll.ensureWidgetVisible(dock._batch.review_card, 0, 20)
        QgsApplication.processEvents()
        report["screenshots"].append(
            _save(window, output_dir / f"batch_ui_review_t002_{args.tag}.png")
        )

        window.resize(1024, 760)
        window.resizeDocks([dock], [350], Qt.Horizontal)
        dock._batch.scroll.ensureWidgetVisible(dock._batch.run_card, 0, 18)
        QgsApplication.processEvents()
        report["screenshots"].append(
            _save(window, output_dir / f"batch_ui_narrow_{args.tag}.png")
        )

        viewport_width = dock._batch.scroll.viewport().width()
        content_width = dock._batch.scroll.widget().width()
        measurements = {
            "window_logical_size": [window.width(), window.height()],
            "dock_logical_size": [dock.width(), dock.height()],
            "scroll_viewport_width": viewport_width,
            "scroll_content_width": content_width,
            "horizontal_scroll_max": dock._batch.scroll.horizontalScrollBar().maximum(),
            "vertical_scroll_max": dock._batch.scroll.verticalScrollBar().maximum(),
            "hidden_table_columns": [
                index
                for index in range(dock._batch.table.columnCount())
                if dock._batch.table.isColumnHidden(index)
            ],
            "critical_buttons": [
                _button_measurement(button)
                for button in (
                    dock._batch.sample_button,
                    dock._batch.import_button,
                    dock._batch.preview_button,
                    dock._batch.execute_button,
                    dock._batch.export_button,
                )
            ],
        }
        report["measurements"] = measurements
        if measurements["horizontal_scroll_max"] != 0:
            raise AssertionError("窄 Dock 内容仍需要水平滚动")
        if any(
            not item["text_fits_size_hint"]
            for item in measurements["critical_buttons"]
        ):
            raise AssertionError("窄 Dock 中存在主按钮文字宽度不足")
        if 0 in measurements["hidden_table_columns"] or 2 in measurements["hidden_table_columns"]:
            raise AssertionError("窄 Dock 隐藏了任务或状态主列")
        if not {3, 5}.issubset(set(measurements["hidden_table_columns"])):
            raise AssertionError("窄 Dock 未折叠次要表格列")

        report["status"] = "PASS"
        report_path = output_dir / f"batch_ui_render_report_{args.tag}.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        adapter.clear_layers()
        window.close()
        window.deleteLater()
    finally:
        project.clear()
        app.exitQgis()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
