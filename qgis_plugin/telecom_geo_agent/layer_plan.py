"""QGIS-independent layer plan using only repository-relative sources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath


PLUGIN_LAYER_PROPERTY = "telecom_geo_agent/layer_key"
RELATIVE_SOURCE_PROPERTY = "telecom_geo_agent/source_relative_path"


@dataclass(frozen=True)
class LayerSpec:
    key: str
    name: str
    relative_path: PurePosixPath
    style: str
    visible: bool
    subset_expression: str | None = None
    label_field: str | None = None

    def source_path(self, repository_root: Path) -> Path:
        return repository_root.joinpath(*self.relative_path.parts).resolve()


@dataclass(frozen=True)
class LayerPlan:
    repository_root: Path
    layers: tuple[LayerSpec, ...]
    group_name: str | None = None

    def by_key(self, key: str) -> LayerSpec:
        for layer in self.layers:
            if layer.key == key:
                return layer
        raise KeyError(key)

    def validate_sources(self) -> None:
        root = self.repository_root.resolve()
        for layer in self.layers:
            source = layer.source_path(root)
            try:
                source.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"图层路径越出 P0 运行时：{source}") from exc
            if not source.is_file():
                raise FileNotFoundError(f"缺少图层源文件：{layer.relative_path.as_posix()}")


def build_layer_plan(
    repository_root: str | Path,
    *,
    include_first_route: bool = True,
    include_final_route: bool = True,
    issue_assets: tuple[str, ...] = ("D017",),
    first_route_id: str = "R001",
    final_route_id: str = "R002",
    final_route_passed: bool = True,
) -> LayerPlan:
    """Describe available result layers without importing PyQGIS."""

    root = Path(repository_root).resolve()
    layers = [
            LayerSpec(
                "network",
                "P0 合成网络",
                PurePosixPath("data/demo/network.geojson"),
                "network",
                True,
                '"feature_type" = \'edge\'',
            ),
            LayerSpec(
                "sites",
                "P0 合成站点 A / B",
                PurePosixPath("data/demo/sites.geojson"),
                "sites",
                True,
            ),
    ]
    if include_first_route:
        layers.append(
            LayerSpec(
                "first_route",
                f"第一次路线 {first_route_id}",
                PurePosixPath("outputs/first_route.geojson"),
                "first_route",
                not include_final_route,
            )
        )
    if include_final_route:
        layers.append(
            LayerSpec(
                "final_route",
                f"最终路线 {final_route_id}"
                + ("（PASS）" if final_route_passed else "（未通过）"),
                PurePosixPath("outputs/final_route.geojson"),
                "final_route" if final_route_passed else "failed_route",
                True,
            )
        )
    if issue_assets:
        escaped = [asset.replace("'", "''") for asset in issue_assets]
        expression = " OR ".join(f'"edge_id" = \'{asset}\'' for asset in escaped)
        key = "issue_d017" if issue_assets == ("D017",) else "issues"
        layers.append(
            LayerSpec(
                key,
                "、".join(issue_assets) + " 问题段（合成测试数据）",
                PurePosixPath("data/demo/network.geojson"),
                "issue",
                True,
                expression,
            )
        )
    return LayerPlan(repository_root=root, layers=tuple(layers))


def build_competition_layer_plan(
    repository_root: str | Path,
    scenario_id: str,
    *,
    include_candidate_route: bool,
    include_final_route: bool,
) -> LayerPlan:
    """Describe the stable competition layer stack with portable sources."""

    root = Path(repository_root).resolve()
    output = PurePosixPath("outputs") / "competition" / scenario_id
    layers = [
        LayerSpec(
            "landuse",
            "公开用地背景（OSM）",
            PurePosixPath("data/competition/background/landuse.geojson"),
            "landuse",
            False,
        ),
        LayerSpec(
            "buildings",
            "公开建筑背景（OSM）",
            PurePosixPath("data/competition/background/buildings.geojson"),
            "buildings",
            True,
        ),
        LayerSpec(
            "water",
            "公开水体背景（OSM）",
            PurePosixPath("data/competition/background/water.geojson"),
            "water",
            True,
        ),
        LayerSpec(
            "railways",
            "公开铁路背景（OSM）",
            PurePosixPath("data/competition/background/railways.geojson"),
            "railways",
            True,
        ),
        LayerSpec(
            "roads",
            "公开道路背景（OSM）",
            PurePosixPath("data/competition/background/roads.geojson"),
            "roads",
            True,
        ),
        LayerSpec(
            "candidate_channels",
            "派生候选通道（通信属性为合成）",
            PurePosixPath("data/competition/candidate_channels.geojson"),
            "candidate_channels",
            True,
        ),
        LayerSpec(
            "rooms",
            "合成机房",
            PurePosixPath("data/competition/sites.geojson"),
            "rooms",
            True,
            '"site_type" = \'telecom_room\'',
            "site_id",
        ),
        LayerSpec(
            "base_stations",
            "合成基站",
            PurePosixPath("data/competition/sites.geojson"),
            "base_stations",
            True,
            '"site_type" = \'base_station\'',
            "site_id",
        ),
    ]
    if include_candidate_route:
        layers.append(
            LayerSpec(
                "candidate_route",
                "约束前候选路线（未批准）",
                output / "candidate_route.geojson",
                "first_route",
                not include_final_route,
            )
        )
    layers.append(
        LayerSpec(
            "issues",
            "冲突问题（合成资产）",
            output / "issues.geojson",
            "issue",
            True,
            label_field="asset_id",
        )
    )
    if include_final_route:
        layers.append(
            LayerSpec(
                "final_route",
                "最终校核路线（PASS）",
                output / "final_route.geojson",
                "final_route",
                True,
            )
        )
    return LayerPlan(
        repository_root=root,
        layers=tuple(layers),
        group_name=f"通信工程智能设计 · {scenario_id}",
    )
