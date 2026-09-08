"""Real QGIS Layout/Atlas exporter for the complete batch design book."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qgis.PyQt import sip
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsCoordinateReferenceSystem,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsLayoutItemPage,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    Qgis,
    QgsPrintLayout,
    QgsRectangle,
    QgsRenderContext,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsVectorFileWriter,
)

from .layout_exporter import _layout_font_family


MM = QgsUnitTypes.LayoutMillimeters
DISCLAIMER = "合成通信属性、竞赛样例、非正式施工图；不用于施工、签章、概预算或现实运营商资产判断"


def _route_rectangle(route: dict[str, Any] | None, fallback: QgsRectangle) -> QgsRectangle:
    if not route:
        return QgsRectangle(fallback)
    points = route["geometry"]["coordinates"]
    rectangle = QgsRectangle(
        min(point[0] for point in points), min(point[1] for point in points),
        max(point[0] for point in points), max(point[1] for point in points),
    )
    margin = max(rectangle.width(), rectangle.height(), 0.001) * 0.25
    return QgsRectangle(rectangle.xMinimum() - margin, rectangle.yMinimum() - margin, rectangle.xMaximum() + margin, rectangle.yMaximum() + margin)


def _all_extent(layers: dict[str, Any]) -> QgsRectangle:
    extent = QgsRectangle()
    for key in ("batch_channels", "batch_rooms", "batch_sites", "batch_final"):
        layer = layers.get(key)
        if layer is None:
            continue
        layer.updateExtents()
        if extent.isNull():
            extent = QgsRectangle(layer.extent())
        else:
            extent.combineExtentWith(layer.extent())
    if extent.isNull() or extent.isEmpty():
        raise RuntimeError("批量图册缺少有效地图范围")
    return extent


def _page_records(
    state: dict[str, Any], extent: QgsRectangle, layers: dict[str, Any]
) -> list[dict[str, Any]]:
    counts = state["terminal_counts"]
    channel_count = layers["batch_channels"].featureCount()
    room_count = layers["batch_rooms"].featureCount()
    site_count = layers["batch_sites"].featureCount()
    successful = [item for item in state["tasks"] if item["status"].startswith("completed_")]
    total_length = sum(item["bom"]["total_length_m"] for item in successful)
    total_cable = sum(item["bom"]["recommended_cable_length_m"] for item in successful)
    conflict_tasks = [item for item in state["tasks"] if item["caused_by_task_ids"]]
    pages = [
        {"page_type": "cover", "task_id": "", "title": "片区通信设施批量接入设计图册", "subtitle": f"{state['batch_id']} · {channel_count} 候选边 / {room_count} 合成机房 / {site_count} 合成接入设施 / {state['task_count']} 任务", "body": f"固定顺序：{state['sorting_rule']}\n每任务最多自动改路：{state['max_replans_per_task']} 次\n参数指纹：{state['parameter_fingerprint']}\n\n真实公开 GIS 背景 + 派生候选通道几何 + 合成通信设施及资源属性\n\n{DISCLAIMER}", "extent": extent},
        {"page_type": "overview", "task_id": "", "title": "片区总览", "subtitle": "公开 OSM 背景与批量最终路线", "body": f"总任务：{state['task_count']}\n直接成功：{counts['completed_direct']}\n绕行成功：{counts['completed_rerouted']}\n待人工复核：{counts['needs_review']}\n明确失败：{counts['failed']}\n\n绿色：最终 PASS 路线\n橙色虚线：约束前候选路线\n红色：容量/状态/待复核问题", "extent": extent},
        {"page_type": "summary", "task_id": "", "title": "批次结果汇总", "subtitle": "所有任务均进入明确终态", "body": f"最终 PASS：{len(successful)} / {state['task_count']}\n资源冲突影响任务：{len(conflict_tasks)}\n总路线长度：{total_length:.2f} m\n建议光缆合计：{total_cable:.2f} m\n失败/待复核任务没有 BOM，也没有资源预占。\n\n排序规则和输入共同形成批次指纹；改变输入必须重新确认。", "extent": extent},
    ]
    for result in state["tasks"]:
        task = result["task"]
        route = result.get("final_route") or result.get("candidate_route")
        bom = result.get("bom") or {}
        validations = [item for validation in result["validation_history"] for item in validation["violations"]]
        resources = result["resource_changes"][:6]
        issue_text = "; ".join(
            f"{item['rule_id']}/{item.get('asset_id') or '-'}" for item in validations
        ) or "无"
        resource_text = "; ".join(
            f"{item['asset_id']} {item['free_subduct_before']}→{item['free_subduct_after']}"
            for item in resources
        ) or "无预占"
        body = (
            f"任务：{task['task_id']}    优先级：{task['priority']}\n"
            f"接入设施：{task['site_id']} → 汇聚机房：{task['preferred_room_id']}\n"
            f"终态：{result['status']}    自动改路：{result['repair_count']} / {state['max_replans_per_task']}\n"
            f"光缆规格：{task['cable_fiber_cores']} 芯（不等同子管占用）\n"
            f"路线长度：{bom.get('total_length_m', '-')} m    相对成本：{route.get('relative_cost', '-') if route else '-'}\n"
            f"建议光缆：{bom.get('recommended_cable_length_m', '-')} m\n"
            f"冲突来源任务：{','.join(result['caused_by_task_ids']) or '-'}\n"
            f"校核问题：{issue_text}\n"
            f"关键资源前后：{resource_text}\n"
            f"任务说明：{task.get('notes') or '-'}\n"
            f"参数指纹：{state['parameter_fingerprint'][:16]}"
        )
        pages.append({"page_type": "task", "task_id": task["task_id"], "title": f"任务设计页 · {task['task_id']}", "subtitle": f"{result['status']} · {task['site_id']} → {task['preferred_room_id']}", "body": body, "extent": _route_rectangle(route, extent)})
    bottlenecks = sorted(state["resource_after"].values(), key=lambda item: (item["free_subduct_count"], -item["subduct_reserved_batch"], item["asset_id"]))[:15]
    pages.extend([
        {"page_type": "resource", "task_id": "", "title": "资源占用与瓶颈汇总", "subtitle": "子管资源与光缆纤芯规格已分离", "body": "\n".join(f"{item['asset_id']}: free={item['free_subduct_count']} / reserved={item['subduct_reserved_batch']} / status={item['segment_status']} / by={','.join(item['reserved_by_task_ids']) or '-'}" for item in bottlenecks), "extent": extent},
        {"page_type": "bom_issues", "task_id": "", "title": "BOM 与异常汇总", "subtitle": "BOM 只来自最终 PASS 路线", "body": f"完成任务：{len(successful)}\n路线总长：{total_length:.2f} m\n建议光缆：{total_cable:.2f} m\n待人工复核：{counts['needs_review']}\n明确失败：{counts['failed']}\n\n相对成本仅用于路线权重，不是货币、造价或概预算。\n失败和待复核任务未生成 BOM。", "extent": extent},
        {"page_type": "boundary", "task_id": "", "title": "数据来源、许可与成果边界", "subtitle": "可核查公开背景与合成通信属性不得混称", "body": f"公开背景：OpenStreetMap 道路、建筑、水体、用地、铁路。\n署名：© OpenStreetMap contributors；ODbL 1.0。\n派生几何：{channel_count} 条候选通道沿公开道路坐标序列构建，但不是现实通信管道。\n合成属性：{room_count} 个机房、{site_count} 个接入设施、子管容量/占用、状态、优先级、光缆规格和相对成本。\n\n未连接真实运营商机房、管道、井位、光缆、容量或成本。\n未完成现场勘察、地下管线探测、规范全量审查、施工签章或概预算。\n\n" + DISCLAIMER, "extent": extent},
    ])
    for index, page in enumerate(pages, start=1):
        page["page_no"] = index
    return pages


def _coverage_layer(pages: list[dict[str, Any]]) -> QgsVectorLayer:
    layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "batch_atlas_pages", "memory")
    provider = layer.dataProvider()
    provider.addAttributes([
        QgsField("page_no", QVariant.Int), QgsField("page_type", QVariant.String),
        QgsField("task_id", QVariant.String), QgsField("title", QVariant.String),
        QgsField("subtitle", QVariant.String), QgsField("body", QVariant.String),
    ])
    layer.updateFields()
    features = []
    for page in pages:
        feature = QgsFeature(layer.fields())
        feature.setAttributes([page["page_no"], page["page_type"], page["task_id"], page["title"], page["subtitle"], page["body"]])
        feature.setGeometry(QgsGeometry.fromRect(page["extent"]))
        features.append(feature)
    if not provider.addFeatures(features)[0]:
        raise RuntimeError("无法创建 Atlas 覆盖要素")
    layer.updateExtents()
    return layer


def _label(layout, expression: str, x: float, y: float, width: float, height: float, size: int, *, bold=False, color="#17324A"):
    item = QgsLayoutItemLabel(layout)
    item.setText(expression)
    item.setFont(QFont(_layout_font_family(), size, QFont.Bold if bold else QFont.Normal))
    item.setFontColor(QColor(color))
    item.setMarginX(1.5)
    item.setMarginY(1.0)
    layout.addLayoutItem(item)
    item.attemptMove(QgsLayoutPoint(x, y, MM))
    item.attemptResize(QgsLayoutSize(width, height, MM))
    return item


def _export_result_geopackage(project, layers: dict[str, Any], destination: Path) -> dict[str, int]:
    """Write the complete result stack to one real GeoPackage using GDAL/QGIS."""

    export_keys = (
        "batch_rooms",
        "batch_sites",
        "batch_tasks",
        "batch_candidates",
        "batch_final",
        "batch_issues",
        "batch_resource",
    )
    counts: dict[str, int] = {}
    first = True
    for key in export_keys:
        layer = layers.get(key)
        if layer is None:
            raise RuntimeError(f"GeoPackage 缺少待导出图层：{key}")
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = key
        options.fileEncoding = "UTF-8"
        options.actionOnExistingFile = (
            QgsVectorFileWriter.CreateOrOverwriteFile
            if first
            else QgsVectorFileWriter.CreateOrOverwriteLayer
        )
        error, _new_filename, _new_layer, message = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer, str(destination), project.transformContext(), options
        )
        if error != QgsVectorFileWriter.NoError:
            raise RuntimeError(f"GeoPackage 图层写入失败：{key}: code={error}, {message}")
        counts[key] = layer.featureCount()
        first = False
    if not destination.is_file() or destination.stat().st_size < 100_000:
        raise RuntimeError("GeoPackage 缺失或体积异常")
    return counts


def export_batch_atlas(project, layers: dict[str, Any], state: dict[str, Any], destination: str | Path) -> Path:
    if state.get("status") != "completed" or state.get("task_count") != len(state.get("tasks", [])):
        raise RuntimeError("只有完整明确终态批次可以生成图册")
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    filtered_keys = ("batch_tasks", "batch_candidates", "batch_final", "batch_issues")
    previous_subsets = {
        key: layers[key].subsetString() for key in filtered_keys if key in layers
    }
    for key in previous_subsets:
        if not layers[key].setSubsetString(""):
            raise RuntimeError(f"图册导出前无法清除状态筛选：{key}")
    extent = _all_extent(layers)
    pages = _page_records(state, extent, layers)
    if len(pages) != state["task_count"] + 6:
        raise RuntimeError("图册必须包含 6 个总览/汇总页和每任务 1 页")
    coverage = _coverage_layer(pages)
    project.addMapLayer(coverage, False)
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(f"片区通信设施批量接入设计_{state['batch_id']}")
    layout.pageCollection().page(0).setPageSize("A3", QgsLayoutItemPage.Landscape)
    _label(layout, "[% attribute(@atlas_feature,'title') %]", 10, 5, 400, 13, 18, bold=True)
    _label(layout, "[% attribute(@atlas_feature,'subtitle') %]", 10, 19, 400, 8, 9, color="#35637A")
    map_item = QgsLayoutItemMap(layout)
    layout.addLayoutItem(map_item)
    map_item.attemptMove(QgsLayoutPoint(10, 31, MM))
    map_item.attemptResize(QgsLayoutSize(270, 230, MM))
    map_item.setFrameEnabled(True)
    map_item.setFrameStrokeColor(QColor("#56788A"))
    render_layers = [layers[key] for key in ("batch_landuse", "batch_buildings", "batch_water", "batch_railways", "batch_roads", "batch_channels", "batch_resource", "batch_candidates", "batch_final", "batch_issues", "batch_rooms", "batch_sites") if key in layers]
    map_item.setLayers(render_layers)
    map_item.setKeepLayerSet(True)
    # Use a metric map CRS so the scale bar is truthful. Source layers remain
    # auditable EPSG:4326 and QGIS performs on-the-fly rendering only.
    map_item.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    map_item.setAtlasDriven(True)
    map_item.setAtlasScalingMode(QgsLayoutItemMap.Auto)
    map_item.setAtlasMargin(0.12)

    _label(
        layout,
        "图例与边界\n■ 合成汇聚机房  ▲ 合成接入设施\n━━ 最终 PASS 路线  ┄┄ 约束前候选路线\n━━ 冲突/待复核问题\n公开底图：OSM；通信资源：合成",
        286,
        31,
        124,
        43,
        7,
        bold=True,
        color="#233F53",
    )
    _label(layout, "[% attribute(@atlas_feature,'body') %]", 286, 78, 124, 183, 7, color="#1E3446")
    scale = QgsLayoutItemScaleBar(layout)
    layout.addLayoutItem(scale)
    scale.setStyle("Line Ticks Up")
    scale.setLinkedMap(map_item)
    scale.setUnits(QgsUnitTypes.DistanceMeters)
    scale.setNumberOfSegments(3)
    scale.setSegmentSizeMode(Qgis.ScaleBarSegmentSizeMode.FitWidth)
    scale.setMinimumBarWidth(35)
    scale.setMaximumBarWidth(70)
    scale.setUnitLabel("m")
    scale.setFont(QFont(_layout_font_family(), 7))
    scale.attemptMove(QgsLayoutPoint(18, 243, MM))
    scale.attemptResize(QgsLayoutSize(72, 11, MM))
    _label(layout, "[% '第 ' || attribute(@atlas_feature,'page_no') || ' / " + str(len(pages)) + " 页' %]    © OpenStreetMap contributors / ODbL 1.0    " + DISCLAIMER, 10, 268, 400, 20, 7, bold=True, color="#8B2D36")

    atlas = layout.atlas()
    atlas.setCoverageLayer(coverage)
    atlas.setEnabled(True)
    atlas.setHideCoverage(True)
    atlas.setSortFeatures(True)
    atlas.setSortExpression('"page_no"')
    atlas.setSortAscending(True)
    ok, error = atlas.setFilenameExpression("'page_' || lpad(to_string(\"page_no\"), 2, '0')")
    if not ok:
        raise RuntimeError(f"Atlas 文件名表达式无效：{error}")
    settings = QgsLayoutExporter.PdfExportSettings()
    settings.dpi = 180
    settings.textRenderFormat = QgsRenderContext.TextFormatAlwaysText
    try:
        result, message = QgsLayoutExporter.exportToPdf(atlas, str(destination), settings)
        if result != QgsLayoutExporter.Success or not destination.is_file():
            raise RuntimeError(f"QGIS Atlas PDF 导出失败：code={result}, message={message}")
        manifest = [{key: page[key] for key in ("page_no", "page_type", "task_id", "title", "subtitle")} for page in pages]
        (destination.parent / "atlas_pages.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        geopackage = destination.parent / "batch_results.gpkg"
        layer_counts = _export_result_geopackage(project, layers, geopackage)
        (destination.parent / "geopackage_validation.json").write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "writer": "QgsVectorFileWriter/GPKG",
                    "file": geopackage.name,
                    "bytes": geopackage.stat().st_size,
                    "layer_counts": layer_counts,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        from competition.batch.outputs import refresh_checksums

        refresh_checksums(destination.parent)
    finally:
        map_item.setKeepLayerSet(False)
        map_item.setLayers([])
        project.removeMapLayer(coverage.id())
        sip.delete(layout)
        for key, expression in previous_subsets.items():
            layers[key].setSubsetString(expression)
    return destination
