"""Thin PyQGIS adapter for plugin-owned layer loading and map navigation."""

from __future__ import annotations

from qgis.core import (
    QgsFillSymbol,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsProject,
    QgsRectangle,
    QgsSingleSymbolRenderer,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtGui import QColor, QFont

from .layer_plan import (
    PLUGIN_LAYER_PROPERTY,
    RELATIVE_SOURCE_PROPERTY,
    LayerPlan,
    LayerSpec,
)


class QgisMapAdapter:
    """Own only P1A layers and never alter the P0 data or algorithms."""

    def __init__(self, iface) -> None:
        self.iface = iface
        self.project = QgsProject.instance()
        self.layers: dict[str, QgsVectorLayer] = {}
        self.group_name: str | None = None

    def load_plan(self, plan: LayerPlan) -> None:
        plan.validate_sources()
        self.clear_layers()
        try:
            group = None
            if plan.group_name:
                group = self.project.layerTreeRoot().addGroup(plan.group_name)
                group.setCustomProperty(PLUGIN_LAYER_PROPERTY, "group")
                self.group_name = plan.group_name
            for spec in plan.layers:
                layer = self._create_layer(plan, spec)
                self.project.addMapLayer(layer, not bool(group))
                if group is not None:
                    group.addLayer(layer)
                self.layers[spec.key] = layer
                self._set_visible(spec.key, spec.visible)
        except Exception:
            self.clear_layers()
            raise

    def _create_layer(self, plan: LayerPlan, spec: LayerSpec) -> QgsVectorLayer:
        source = spec.source_path(plan.repository_root)
        layer = QgsVectorLayer(str(source), spec.name, "ogr")
        if not layer.isValid():
            raise RuntimeError(f"QGIS 无法加载图层：{spec.relative_path.as_posix()}")
        if spec.subset_expression and not layer.setSubsetString(spec.subset_expression):
            raise RuntimeError(
                f"QGIS 无法应用图层筛选：{spec.key} / {spec.subset_expression}"
            )
        layer.setCustomProperty(PLUGIN_LAYER_PROPERTY, spec.key)
        layer.setCustomProperty(
            RELATIVE_SOURCE_PROPERTY, spec.relative_path.as_posix()
        )
        layer.setRenderer(QgsSingleSymbolRenderer(self._symbol(spec.style)))
        if spec.label_field:
            settings = QgsPalLayerSettings()
            settings.fieldName = spec.label_field
            text_format = QgsTextFormat()
            text_format.setFont(QFont("Microsoft YaHei", 8))
            text_format.setColor(QColor("#ecf2f8"))
            settings.setFormat(text_format)
            layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
            layer.setLabelsEnabled(True)
        layer.triggerRepaint()
        return layer

    @staticmethod
    def _symbol(style: str):
        if style in {"sites", "rooms", "base_stations"}:
            colors = {
                "sites": ("45,132,255,255", "circle"),
                "rooms": ("65,145,255,255", "square"),
                "base_stations": ("255,108,76,255", "triangle"),
            }
            color, name = colors[style]
            return QgsMarkerSymbol.createSimple(
                {
                    "name": name,
                    "color": color,
                    "outline_color": "230,240,255,255",
                    "outline_width": "0.6",
                    "size": "4.2",
                }
            )
        fill_styles = {
            "buildings": {
                "color": "94,104,118,95",
                "outline_color": "120,130,145,120",
                "outline_width": "0.15",
            },
            "landuse": {
                "color": "81,112,87,55",
                "outline_color": "81,112,87,60",
                "outline_width": "0.1",
            },
            "water": {
                "color": "65,154,210,115",
                "outline_color": "65,154,210,210",
                "outline_width": "0.35",
            },
        }
        if style in fill_styles:
            return QgsFillSymbol.createSimple(fill_styles[style])
        line_styles = {
            "network": {
                "color": "117,126,140,145",
                "width": "0.7",
                "line_style": "solid",
            },
            "first_route": {
                "color": "245,166,35,255",
                "width": "1.7",
                "line_style": "dash",
            },
            "final_route": {
                "color": "38,208,124,255",
                "width": "2.2",
                "line_style": "solid",
            },
            "failed_route": {
                "color": "191,86,214,255",
                "width": "2.0",
                "line_style": "dash",
            },
            "issue": {
                "color": "235,64,72,255",
                "width": "3.2",
                "line_style": "solid",
            },
            "roads": {
                "color": "137,148,164,150",
                "width": "0.55",
                "line_style": "solid",
            },
            "railways": {
                "color": "125,92,145,170",
                "width": "0.8",
                "line_style": "dash",
            },
            "candidate_channels": {
                "color": "86,191,206,165",
                "width": "0.9",
                "line_style": "dash",
            },
        }
        return QgsLineSymbol.createSimple(line_styles[style])

    def _set_visible(self, key: str, visible: bool) -> None:
        layer = self.layers.get(key)
        if layer is None:
            raise RuntimeError(f"图层尚未加载：{key}")
        tree_layer = self.project.layerTreeRoot().findLayer(layer.id())
        if tree_layer is None:
            raise RuntimeError(f"QGIS 图层树缺少插件图层：{key}")
        tree_layer.setItemVisibilityChecked(visible)

    def show_first_route(self) -> None:
        key = "first_route" if "first_route" in self.layers else "candidate_route"
        self._set_visible(key, True)
        self._set_visible_if_present("final_route", False)
        self._set_visible_if_present("issue_d017", True)
        self._set_visible_if_present("issues", True)
        self._zoom_to(key)

    def show_final_route(self) -> None:
        self._set_visible_if_present("first_route", False)
        self._set_visible("final_route", True)
        self._set_visible_if_present("issue_d017", True)
        self._set_visible_if_present("issues", True)
        self._zoom_to("final_route")

    def focus_issue(self, asset_id: str) -> None:
        key = "issue_d017" if "issue_d017" in self.layers else "issues"
        if key not in self.layers:
            raise RuntimeError("当前规划没有可定位的问题段")
        self._set_visible(key, True)
        layer = self.layers[key]
        layer.removeSelection()
        field = "edge_id" if "edge_id" in layer.fields().names() else "asset_id"
        layer.selectByExpression(f'"{field}" = \'{asset_id.replace(chr(39), chr(39) * 2)}\'')
        if layer.selectedFeatureCount() == 0:
            raise RuntimeError(f"当前问题图层不包含资产：{asset_id}")
        self._zoom_to(key, selected_only=True)

    def filter_batch_tasks(self, status: str) -> None:
        allowed = {"all", "completed_direct", "completed_rerouted", "needs_review", "failed"}
        if status not in allowed:
            raise ValueError(f"未知批量状态筛选：{status}")
        expression = "" if status == "all" else f'"status" = \'{status}\''
        for key in ("batch_tasks", "batch_candidates", "batch_final", "batch_issues"):
            layer = self.layers.get(key)
            if layer is not None and not layer.setSubsetString(expression):
                raise RuntimeError(f"QGIS 无法应用批量状态筛选：{key}")
        if "batch_tasks" in self.layers:
            self._zoom_to("batch_tasks")

    def focus_batch_task(self, task_id: str) -> None:
        escaped = task_id.replace("'", "''")
        selected_key = None
        for key in ("batch_final", "batch_candidates", "batch_tasks", "batch_issues"):
            layer = self.layers.get(key)
            if layer is None or "task_id" not in layer.fields().names():
                continue
            layer.removeSelection()
            layer.selectByExpression(f'"task_id" = \'{escaped}\'')
            if selected_key is None and layer.selectedFeatureCount() > 0:
                selected_key = key
        if selected_key is None:
            raise RuntimeError(f"当前批次不存在可定位任务：{task_id}")
        self._zoom_to(selected_key, selected_only=True)

    def set_batch_route_visibility(
        self, candidate_visible: bool, final_visible: bool
    ) -> None:
        self._set_visible_if_present("batch_candidates", candidate_visible)
        self._set_visible_if_present("batch_final", final_visible)
        self.iface.mapCanvas().refresh()

    def _set_visible_if_present(self, key: str, visible: bool) -> None:
        if key in self.layers:
            self._set_visible(key, visible)

    def _zoom_to(self, key: str, *, selected_only: bool = False) -> None:
        layer = self.layers.get(key)
        if layer is None:
            raise RuntimeError(f"图层尚未加载：{key}")
        layer.updateExtents()
        extent = layer.boundingBoxOfSelected() if selected_only else layer.extent()
        # Point-only task filters legitimately yield a zero-width/height
        # rectangle. Only a null extent means there is no locatable feature.
        if extent.isNull():
            raise RuntimeError(f"图层没有可定位要素：{key}")
        margin = max(extent.width(), extent.height(), 0.002) * 0.35
        buffered = QgsRectangle(
            extent.xMinimum() - margin,
            extent.yMinimum() - margin,
            extent.xMaximum() + margin,
            extent.yMaximum() + margin,
        )
        canvas = self.iface.mapCanvas()
        canvas.setExtent(buffered)
        canvas.refresh()

    def clear_layers(self) -> None:
        managed_ids = [
            layer_id
            for layer_id, layer in self.project.mapLayers().items()
            if layer.customProperty(PLUGIN_LAYER_PROPERTY, "")
        ]
        if managed_ids:
            self.project.removeMapLayers(managed_ids)
        root = self.project.layerTreeRoot()
        for group in list(root.children()):
            if group.customProperty(PLUGIN_LAYER_PROPERTY, "") == "group":
                root.removeChildNode(group)
        self.layers.clear()
        self.group_name = None

    def export_competition_pdf(
        self, state: dict, destination, *, paper_size: str = "A3"
    ):
        from .layout_exporter import export_competition_layout

        return export_competition_layout(
            self.project,
            self.layers,
            state,
            destination,
            paper_size=paper_size,
        )

    def export_batch_atlas(self, state: dict, destination):
        from .atlas_exporter import export_batch_atlas

        return export_batch_atlas(self.project, self.layers, state, destination)
