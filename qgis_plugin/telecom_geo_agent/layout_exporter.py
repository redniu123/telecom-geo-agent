"""QGIS Print Layout exporter for the competition design sheet."""

from __future__ import annotations

from pathlib import Path

from qgis.PyQt import sip
from qgis.PyQt.QtGui import QColor, QFont, QFontDatabase
from qgis.core import (
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemPage,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLegendStyle,
    QgsPrintLayout,
    QgsRectangle,
    QgsRenderContext,
    QgsUnitTypes,
)


MM = QgsUnitTypes.LayoutMillimeters
_FONT_FAMILY: str | None = None


def _layout_font_family() -> str:
    """Register a real CJK font when headless Qt exposes no system families."""

    global _FONT_FAMILY
    if _FONT_FAMILY is not None:
        return _FONT_FAMILY
    candidates = (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\ARIALUNI.ttf"),
    )
    for candidate in candidates:
        if not candidate.is_file():
            continue
        font_id = QFontDatabase.addApplicationFont(str(candidate))
        if font_id < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            _FONT_FAMILY = families[0]
            return _FONT_FAMILY
    _FONT_FAMILY = "Sans Serif"
    return _FONT_FAMILY


def _label(layout, text: str, x: float, y: float, width: float, height: float, *, size: int = 9, bold: bool = False, color: str = "#17324A"):
    item = QgsLayoutItemLabel(layout)
    item.setText(text)
    item.setFont(QFont(_layout_font_family(), size, QFont.Bold if bold else QFont.Normal))
    item.setFontColor(QColor(color))
    layout.addLayoutItem(item)
    item.attemptMove(QgsLayoutPoint(x, y, MM))
    item.attemptResize(QgsLayoutSize(width, height, MM))
    item.setMarginX(1.2)
    item.setMarginY(0.8)
    item.setFrameEnabled(False)
    return item


def _route_extent(layers: dict) -> QgsRectangle:
    keys = [key for key in ("final_route", "candidate_route", "candidate_channels") if key in layers]
    if not keys:
        raise RuntimeError("图纸缺少可计算范围的路线/候选通道图层")
    extent = QgsRectangle()
    for key in keys:
        layer = layers[key]
        layer.updateExtents()
        if extent.isNull():
            extent = QgsRectangle(layer.extent())
        else:
            extent.combineExtentWith(layer.extent())
    margin = max(extent.width(), extent.height()) * 0.06
    return QgsRectangle(
        extent.xMinimum() - margin,
        extent.yMinimum() - margin,
        extent.xMaximum() + margin,
        extent.yMaximum() + margin,
    )


def export_competition_layout(
    project,
    layers: dict,
    state: dict,
    destination: str | Path,
    *,
    paper_size: str = "A3",
) -> Path:
    """Export one validated competition layout without registering stale layouts."""

    if state.get("status") != "completed" or not state.get("final_route") or not state.get("bom_result"):
        raise RuntimeError("只有最终校核 PASS 且存在 BOM 的场景可以导出标准图纸")
    if paper_size not in {"A3", "A4"}:
        raise ValueError("paper_size must be A3 or A4")
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(f"通信线路智能设计_{state['scenario_id']}")
    page = layout.pageCollection().page(0)
    page.setPageSize(paper_size, QgsLayoutItemPage.Landscape)
    page_width, page_height = ((420.0, 297.0) if paper_size == "A3" else (297.0, 210.0))
    scale = 1.0 if paper_size == "A3" else 0.70

    _label(
        layout,
        "通信线路参数化智能设计平面图",
        10,
        5,
        page_width - 20,
        14 * scale,
        size=18 if paper_size == "A3" else 14,
        bold=True,
        color="#12324A",
    )
    _label(
        layout,
        f"场景 ID：{state['scenario_id']}    最终状态：PASS    修复次数：{state['repair_count']}",
        10,
        19,
        page_width - 20,
        8 * scale,
        size=9,
        color="#35637A",
    )

    map_x, map_y = 10.0, 31.0
    sidebar_width = 105.0 if paper_size == "A3" else 78.0
    map_width = page_width - sidebar_width - 25.0
    map_height = page_height - 64.0
    map_item = QgsLayoutItemMap(layout)
    layout.addLayoutItem(map_item)
    map_item.attemptMove(QgsLayoutPoint(map_x, map_y, MM))
    map_item.attemptResize(QgsLayoutSize(map_width, map_height, MM))
    # A new layout map has a zero-sized internal viewport.  Setting its extent
    # before the item is sized makes QGIS/GDAL construct invalid LinearRings
    # during export.  Size first, then zoom so QGIS preserves the map frame's
    # aspect ratio without emitting geometry errors.
    map_item.zoomToExtent(_route_extent(layers))
    map_item.setFrameEnabled(True)
    map_item.setFrameStrokeColor(QColor("#56788A"))
    map_item.setLayers([layers[key] for key in layers])
    map_item.setKeepLayerSet(True)

    sidebar_x = map_x + map_width + 5.0
    legend = QgsLayoutItemLegend(layout)
    layout.addLayoutItem(legend)
    legend.setTitle("图例 / 数据分类")
    legend.setLinkedMap(map_item)
    legend.setLegendFilterByMapEnabled(True)
    legend.setStyleFont(
        QgsLegendStyle.Title, QFont(_layout_font_family(), 10, QFont.Bold)
    )
    legend.setStyleFont(
        QgsLegendStyle.SymbolLabel, QFont(_layout_font_family(), 8)
    )
    legend.attemptMove(QgsLayoutPoint(sidebar_x, map_y, MM))
    legend.attemptResize(QgsLayoutSize(sidebar_width, 82 * scale, MM))

    parameters = state["parameters"]
    forbidden = "、".join(state["forbidden_asset_ids_applied"]) or "无"
    parameter_text = (
        "设计参数\n"
        f"起终点：{parameters['start_site_id']} → {parameters['end_site_id']}\n"
        f"光缆芯数：{parameters['fiber_cores']} 芯\n"
        f"优先已有管道：{'是' if parameters['prefer_existing_duct'] else '否'}\n"
        f"禁用/问题资产：{forbidden}\n"
        f"参数指纹：{state['parameter_fingerprint'][:12]}"
    )
    _label(layout, parameter_text, sidebar_x, 116 * scale, sidebar_width, 47 * scale, size=8)

    route = state["final_route"]
    bom = state["bom_result"]
    summary_text = (
        "路线与 BOM 摘要\n"
        f"最终路线：{route['route_id']}\n"
        f"路线总长：{bom['total_length_m']:.2f} m\n"
        f"已有管道：{bom['existing_duct_length_m']:.2f} m\n"
        f"合成新建：{bom['new_build_length_m']:.2f} m\n"
        f"建议光缆：{bom['recommended_cable_length_m']:.2f} m\n"
        f"相对成本：{route['relative_cost']:.2f}"
    )
    _label(layout, summary_text, sidebar_x, 166 * scale, sidebar_width, 54 * scale, size=8)

    issue = state["validation_history"][0]["violations"][0]
    issue_text = (
        "冲突说明\n"
        f"{issue['rule_id']} / {issue.get('asset_id') or '-'}\n"
        f"{issue['message']}\n"
        "系统仅执行一次有界禁用重规划。"
    )
    _label(layout, issue_text, sidebar_x, 223 * scale, sidebar_width, 39 * scale, size=8, color="#8B2D36")

    north_x = map_x + map_width - 22.0
    _label(layout, "N\n↑", north_x, map_y + 5, 16, 22, size=15, bold=True, color="#12324A")
    scale_bar = QgsLayoutItemScaleBar(layout)
    layout.addLayoutItem(scale_bar)
    scale_bar.setStyle("Line Ticks Up")
    scale_bar.setLinkedMap(map_item)
    scale_bar.setUnits(QgsUnitTypes.DistanceMeters)
    scale_bar.setNumberOfSegments(4)
    scale_bar.setNumberOfSegmentsLeft(0)
    scale_bar.setUnitsPerSegment(250)
    scale_bar.setUnitLabel("m")
    scale_bar.setFont(QFont(_layout_font_family(), 8))
    scale_bar.attemptMove(QgsLayoutPoint(map_x + 7, map_y + map_height - 14, MM))
    scale_bar.attemptResize(QgsLayoutSize(75, 12, MM))

    footer = (
        "数据集：osm_shanghai_former_french_concession_north_demo_v1；"
        "公开背景 © OpenStreetMap contributors / ODbL 1.0；"
        "候选通道几何沿公开道路派生，站点及全部通信属性为合成。\n"
        "竞赛样例 / 非正式施工图 · 不用于现场施工、签章、概预算或运营商资产判断"
    )
    _label(
        layout,
        footer,
        10,
        page_height - 27.0,
        page_width - 20.0,
        20.0,
        size=8,
        bold=True,
        color="#8B2D36",
    )

    settings = QgsLayoutExporter.PdfExportSettings()
    settings.dpi = 200
    settings.textRenderFormat = QgsRenderContext.TextFormatAlwaysText
    try:
        result = QgsLayoutExporter(layout).exportToPdf(str(destination), settings)
        if result != QgsLayoutExporter.Success or not destination.is_file():
            raise RuntimeError(f"QGIS Layout PDF 导出失败：code={result}")
    finally:
        map_item.setKeepLayerSet(False)
        map_item.setLayers([])
        sip.delete(layout)
    return destination
