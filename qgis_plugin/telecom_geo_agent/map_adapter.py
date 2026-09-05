"""Thin PyQGIS adapter for plugin-owned layer loading and map navigation."""

from __future__ import annotations

from qgis.core import (
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsProject,
    QgsRectangle,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)

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

    def load_plan(self, plan: LayerPlan) -> None:
        plan.validate_sources()
        self.clear_layers()
        try:
            for spec in plan.layers:
                layer = self._create_layer(plan, spec)
                self.project.addMapLayer(layer)
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
        layer.triggerRepaint()
        return layer

    @staticmethod
    def _symbol(style: str):
        if style == "sites":
            return QgsMarkerSymbol.createSimple(
                {
                    "name": "circle",
                    "color": "45,132,255,255",
                    "outline_color": "230,240,255,255",
                    "outline_width": "0.6",
                    "size": "4.2",
                }
            )
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
        self._set_visible("first_route", True)
        self._set_visible_if_present("final_route", False)
        self._set_visible_if_present("issue_d017", True)
        self._set_visible_if_present("issues", True)
        self._zoom_to("first_route")

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
        layer.selectByExpression(f'"edge_id" = \'{asset_id.replace(chr(39), chr(39) * 2)}\'')
        if layer.selectedFeatureCount() == 0:
            raise RuntimeError(f"当前问题图层不包含资产：{asset_id}")
        self._zoom_to(key, selected_only=True)

    def _set_visible_if_present(self, key: str, visible: bool) -> None:
        if key in self.layers:
            self._set_visible(key, visible)

    def _zoom_to(self, key: str, *, selected_only: bool = False) -> None:
        layer = self.layers.get(key)
        if layer is None:
            raise RuntimeError(f"图层尚未加载：{key}")
        layer.updateExtents()
        extent = layer.boundingBoxOfSelected() if selected_only else layer.extent()
        if extent.isEmpty():
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
        self.layers.clear()
