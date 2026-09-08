"""QGIS-independent layer contracts for batch inputs and results."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from .layer_plan import LayerPlan, LayerSpec


def build_batch_input_layer_plan(
    repository_root: str | Path, dataset_id: str
) -> LayerPlan:
    """Describe the selected input dataset before any planning output exists."""

    root = Path(repository_root).resolve()
    data = PurePosixPath("data/competition_batch")
    layers = (
        LayerSpec("batch_landuse", "公开用地背景（OSM）", data / "background/landuse.geojson", "landuse", False),
        LayerSpec("batch_buildings", "公开建筑背景（OSM）", data / "background/buildings.geojson", "buildings", True),
        LayerSpec("batch_water", "公开水体背景（OSM）", data / "background/water.geojson", "water", True),
        LayerSpec("batch_railways", "公开铁路背景（OSM）", data / "background/railways.geojson", "railways", True),
        LayerSpec("batch_roads", "公开道路背景（OSM）", data / "background/roads.geojson", "roads", True),
        LayerSpec("batch_channels", "派生候选走廊（通信属性合成）", data / "candidate_channels.geojson", "candidate_channels", True),
        LayerSpec("batch_rooms", "合成汇聚机房", data / "facilities.geojson", "rooms", True, '"site_type" = \'aggregation_room\'', "site_id"),
        LayerSpec("batch_sites", "合成接入设施", data / "facilities.geojson", "base_stations", True, '"site_type" = \'access_site\'', "site_id"),
    )
    return LayerPlan(
        repository_root=root,
        layers=layers,
        group_name=f"批量设计输入 · {dataset_id}",
    )


def build_batch_layer_plan(repository_root: str | Path, batch_id: str) -> LayerPlan:
    root = Path(repository_root).resolve()
    data = PurePosixPath("data/competition_batch")
    output = PurePosixPath("outputs/competition_batch") / batch_id
    layers = (
        LayerSpec("batch_landuse", "公开用地背景（OSM）", data / "background/landuse.geojson", "landuse", False),
        LayerSpec("batch_buildings", "公开建筑背景（OSM）", data / "background/buildings.geojson", "buildings", True),
        LayerSpec("batch_water", "公开水体背景（OSM）", data / "background/water.geojson", "water", True),
        LayerSpec("batch_railways", "公开铁路背景（OSM）", data / "background/railways.geojson", "railways", True),
        LayerSpec("batch_roads", "公开道路背景（OSM）", data / "background/roads.geojson", "roads", True),
        LayerSpec("batch_channels", "派生候选走廊（通信属性合成）", data / "candidate_channels.geojson", "candidate_channels", True),
        LayerSpec("batch_rooms", "合成汇聚机房", data / "facilities.geojson", "rooms", True, '"site_type" = \'aggregation_room\'', "site_id"),
        LayerSpec("batch_sites", "合成接入设施", data / "facilities.geojson", "base_stations", True, '"site_type" = \'access_site\'', "site_id"),
        LayerSpec("batch_resource", "批次后合成子管资源", output / "resource_utilization.geojson", "candidate_channels", True, label_field="asset_id"),
        LayerSpec("batch_candidates", "约束前候选路线", output / "candidate_routes.geojson", "first_route", False, label_field="task_id"),
        LayerSpec("batch_issues", "冲突与待复核问题", output / "issues.geojson", "issue", True, label_field="task_id"),
        LayerSpec("batch_final", "最终 PASS 路线", output / "final_routes.geojson", "final_route", True, label_field="task_id"),
        LayerSpec("batch_tasks", "批量任务终态", output / "task_results.geojson", "base_stations", True, label_field="task_id"),
    )
    return LayerPlan(repository_root=root, layers=layers, group_name=f"片区批量接入 · {batch_id}")
