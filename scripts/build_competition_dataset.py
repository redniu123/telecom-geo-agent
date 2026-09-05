"""Build the offline competition dataset from the audited staging selection.

The public road geometry remains OpenStreetMap data.  Candidate channels and
all telecom attributes are explicitly derived/synthetic; they are never
described as real carrier assets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import networkx as nx


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGING = Path(
    r"E:\Users\zhubinhua\Documents\ChatGPT\通信工程agent_data_staging\selected"
)
OUTPUT_ROOT = REPO_ROOT / "data" / "competition"
EXPECTED_DATASET_ID = "osm_shanghai_former_french_concession_north_demo_v1"
EXPECTED_SOURCE_MANIFEST_SHA256 = (
    "61306c80f0baec19740aca865c8b78a522fd435766428e9fa165c2a82a02c4ef"
)
SENSITIVE_KEY = re.compile(
    r"^(?:contact(?::.*)?|phone|email|military|aeroway|power|telecom|"
    r"communication|government)$",
    re.IGNORECASE,
)
EARTH_RADIUS_M = 6_371_008.8


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "name": "telecom_competition_demo",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::4326"},
        },
        "features": features,
    }


def _iter_points(coordinates: Any) -> Iterable[list[float]]:
    if (
        isinstance(coordinates, list)
        and len(coordinates) >= 2
        and all(isinstance(value, (int, float)) for value in coordinates[:2])
    ):
        yield [float(coordinates[0]), float(coordinates[1])]
        return
    if isinstance(coordinates, list):
        for child in coordinates:
            yield from _iter_points(child)


def _geometry_bbox(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    points = list(_iter_points(geometry.get("coordinates")))
    if not points:
        raise ValueError("geometry has no coordinate")
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def _intersects(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> bool:
    return not (
        left[2] < right[0]
        or left[0] > right[2]
        or left[3] < right[1]
        or left[1] > right[3]
    )


def _normalized_polygon_geometry(
    geometry: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Close GeoJSON polygon rings without changing any existing coordinate."""

    geometry_type = geometry.get("type")
    if geometry_type not in {"Polygon", "MultiPolygon"}:
        return geometry, 0
    polygons = (
        [geometry["coordinates"]]
        if geometry_type == "Polygon"
        else geometry["coordinates"]
    )
    normalized_polygons = []
    repairs = 0
    for polygon in polygons:
        normalized_rings = []
        for ring in polygon:
            normalized = [list(point) for point in ring]
            if normalized and normalized[0] != normalized[-1]:
                normalized.append(list(normalized[0]))
                repairs += 1
            normalized_rings.append(normalized)
        normalized_polygons.append(normalized_rings)
    coordinates = (
        normalized_polygons[0]
        if geometry_type == "Polygon"
        else normalized_polygons
    )
    return {"type": geometry_type, "coordinates": coordinates}, repairs


def _coord_key(point: list[float]) -> tuple[float, float]:
    return (round(float(point[0]), 7), round(float(point[1]), 7))


def _distance_m(left: tuple[float, float], right: tuple[float, float]) -> float:
    left_lat = math.radians(left[1])
    right_lat = math.radians(right[1])
    delta_lat = math.radians(right[1] - left[1])
    delta_lon = math.radians(right[0] - left[0])
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(left_lat) * math.cos(right_lat) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(haversine))


def _validate_source(staging: Path) -> dict[str, Any]:
    manifest_path = staging / "source_manifest.json"
    if _sha256(manifest_path) != EXPECTED_SOURCE_MANIFEST_SHA256:
        raise ValueError("staging source_manifest.json SHA-256 mismatch")
    manifest = _read_json(manifest_path)
    if manifest.get("dataset_id") != EXPECTED_DATASET_ID:
        raise ValueError("unexpected staging dataset_id")
    if manifest.get("output_crs") != "EPSG:4326 (GeoJSON longitude, latitude)":
        raise ValueError("staging CRS is not the audited EPSG:4326 value")

    for layer_name, entry in manifest["layers"].items():
        source = staging / Path(entry["file"]).name
        if not source.is_file():
            raise FileNotFoundError(source)
        if _sha256(source) != entry["sha256"]:
            raise ValueError(f"source SHA-256 mismatch: {layer_name}")
        document = _read_json(source)
        features = document.get("features")
        if not isinstance(features, list) or len(features) != entry["feature_count"]:
            raise ValueError(f"source feature count mismatch: {layer_name}")
        crs_name = document.get("crs", {}).get("properties", {}).get("name")
        if crs_name != "urn:ogc:def:crs:EPSG::4326":
            raise ValueError(f"source CRS mismatch: {layer_name}")
        for feature in features:
            properties = feature.get("properties", {})
            matched = sorted(key for key in properties if SENSITIVE_KEY.match(key))
            if matched:
                raise ValueError(
                    f"forbidden sensitive tag key(s) in {layer_name}: {matched}"
                )

    for entry in manifest.get("raw_files", []):
        source = Path(entry["path"])
        if not source.is_file() or source.stat().st_size != entry["bytes"]:
            raise ValueError(f"raw source missing or size mismatch: {source}")
        if _sha256(source) != entry["sha256"]:
            raise ValueError(f"raw source SHA-256 mismatch: {source}")
    return manifest


def _road_graph(roads: dict[str, Any]) -> nx.Graph:
    graph = nx.Graph()
    for feature_index, feature in enumerate(roads["features"]):
        geometry = feature["geometry"]
        lines = (
            geometry["coordinates"]
            if geometry["type"] == "MultiLineString"
            else [geometry["coordinates"]]
        )
        for line_index, line in enumerate(lines):
            for segment_index, (left_raw, right_raw) in enumerate(zip(line, line[1:])):
                left, right = _coord_key(left_raw), _coord_key(right_raw)
                length_m = _distance_m(left, right)
                key = (feature_index, line_index, segment_index)
                if graph.has_edge(left, right):
                    existing = graph[left][right]
                    if (length_m, key) < (existing["length_m"], existing["source_key"]):
                        existing.update(length_m=length_m, source_key=key)
                else:
                    graph.add_edge(
                        left,
                        right,
                        length_m=length_m,
                        source_key=key,
                    )
    return graph


def _two_paths(
    roads: dict[str, Any],
    site_coordinates: list[list[float]],
) -> list[list[tuple[float, float]]]:
    graph = _road_graph(roads)
    start, end = (_coord_key(point) for point in site_coordinates)
    if start not in graph or end not in graph:
        raise ValueError("synthetic endpoints are not exact public-road vertices")
    candidates = list(nx.edge_disjoint_paths(graph, start, end))
    candidates.sort(
        key=lambda path: (
            sum(graph[left][right]["length_m"] for left, right in zip(path, path[1:])),
            tuple(path),
        )
    )
    if len(candidates) < 2:
        raise ValueError("audited road graph does not have two edge-disjoint paths")
    return [list(path) for path in candidates[:2]]


def _network_features(
    paths: list[list[tuple[float, float]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    features: list[dict[str, Any]] = []
    node_features: dict[str, dict[str, Any]] = {}
    path_edge_ids: list[list[str]] = []

    def node_id(path_index: int, position: int, path_length: int) -> str:
        if position == 0:
            return "N-A"
        if position == path_length - 1:
            return "N-B"
        return f"N{path_index}-{position:03d}"

    for path_index, path in enumerate(paths, start=1):
        edge_ids: list[str] = []
        for position, coordinate in enumerate(path):
            identifier = node_id(path_index, position, len(path))
            if identifier not in node_features:
                node_features[identifier] = {
                    "type": "Feature",
                    "id": f"node:{identifier}",
                    "properties": {
                        "feature_type": "node",
                        "node_id": identifier,
                        "status": "available",
                        "data_class": "derived_from_public_road_geometry",
                    },
                    "geometry": {"type": "Point", "coordinates": list(coordinate)},
                }
        for segment_index, (left, right) in enumerate(zip(path, path[1:]), start=1):
            edge_id = f"C{path_index}-{segment_index:03d}"
            edge_ids.append(edge_id)
            from_node = node_id(path_index, segment_index - 1, len(path))
            to_node = node_id(path_index, segment_index, len(path))
            is_new_build = path_index == 2 and segment_index % 5 == 0
            features.append(
                {
                    "type": "Feature",
                    "id": f"edge:{edge_id}",
                    "properties": {
                        "feature_type": "edge",
                        "edge_id": edge_id,
                        "from_node": from_node,
                        "to_node": to_node,
                        "asset_type": "new_build" if is_new_build else "existing_duct",
                        "laying_type": "synthetic_trench" if is_new_build else "synthetic_duct",
                        "length_m": round(_distance_m(left, right), 2),
                        "cost_multiplier": 1.25 if is_new_build else (0.85 if path_index == 1 else 1.05),
                        "capacity_cores": 0 if is_new_build else 96,
                        "used_cores": 0 if is_new_build else 12,
                        "status": "available",
                        "data_class": "derived_geometry_with_synthetic_telecom_attributes",
                        "source_geometry": "OpenStreetMap road coordinate sequence",
                        "attribution": "© OpenStreetMap contributors",
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [list(left), list(right)],
                    },
                }
            )
        path_edge_ids.append(edge_ids)

    capacity_edge = path_edge_ids[0][len(path_edge_ids[0]) // 2]
    forbidden_edge = path_edge_ids[0][len(path_edge_ids[0]) // 4]
    cut_edge_1 = path_edge_ids[0][len(path_edge_ids[0]) // 2]
    cut_edge_2 = path_edge_ids[1][len(path_edge_ids[1]) // 2]
    for feature in features:
        props = feature["properties"]
        if props["edge_id"] == capacity_edge:
            props["capacity_cores"] = 48
            props["used_cores"] = 32
            props["scenario_role"] = "capacity_bottleneck"
        elif props["edge_id"] == forbidden_edge:
            props["scenario_role"] = "explicit_forbidden_example"
        elif props["edge_id"] == cut_edge_2:
            props["scenario_role"] = "second_corridor_cut"

    ordered_nodes = [node_features[key] for key in sorted(node_features)]
    metadata = {
        "path_edge_ids": path_edge_ids,
        "capacity_edge": capacity_edge,
        "forbidden_edge": forbidden_edge,
        "no_path_cut_edges": [cut_edge_1, cut_edge_2],
    }
    return ordered_nodes + features, metadata


def _site_features(site_source: dict[str, Any]) -> list[dict[str, Any]]:
    source_features = site_source["features"]
    roles = (("A", "样例 A 机房", "telecom_room", "N-A"), ("B", "样例 B 基站", "base_station", "N-B"))
    features = []
    for source, (site_id, name, site_type, node_id) in zip(source_features, roles):
        features.append(
            {
                "type": "Feature",
                "id": f"site:{site_id}",
                "properties": {
                    "site_id": site_id,
                    "name": name,
                    "site_type": site_type,
                    "node_id": node_id,
                    "status": "available",
                    "data_class": "synthetic",
                    "source": "synthetic_site_on_public_road_network",
                },
                "geometry": source["geometry"],
            }
        )
    return features


def _background_subset(
    document: dict[str, Any],
    bounds: tuple[float, float, float, float],
    layer_name: str,
) -> dict[str, Any]:
    allowed_properties = {
        "roads": ("osm_id", "highway", "name", "surface", "attribution", "source"),
        "buildings": ("osm_id", "building", "building_levels", "attribution", "source"),
        "water": ("osm_id", "natural", "water", "waterway", "attribution", "source"),
        "landuse": ("osm_id", "landuse", "leisure", "attribution", "source"),
        "railways": ("osm_id", "railway", "service", "attribution", "source"),
    }[layer_name]
    selected = []
    ring_closures = 0
    for feature in document["features"]:
        if not _intersects(_geometry_bbox(feature["geometry"]), bounds):
            continue
        properties = {
            key: feature.get("properties", {}).get(key)
            for key in allowed_properties
            if feature.get("properties", {}).get(key) not in (None, "")
        }
        properties["data_class"] = "public_real_derived_subset"
        geometry, repairs = _normalized_polygon_geometry(feature["geometry"])
        ring_closures += repairs
        if repairs:
            properties["geometry_repair"] = "closed_unclosed_polygon_ring"
        selected.append(
            {
                "type": "Feature",
                "id": feature.get("id"),
                "properties": properties,
                "geometry": geometry,
            }
        )
    result = _feature_collection(selected)
    result["geometry_ring_closures"] = ring_closures
    return result


def build_dataset(staging: Path = DEFAULT_STAGING, output_root: Path = OUTPUT_ROOT) -> Path:
    source_manifest = _validate_source(staging)
    roads = _read_json(staging / "roads.geojson")
    site_source = _read_json(staging / "site_candidates.geojson")
    coordinates = [feature["geometry"]["coordinates"] for feature in site_source["features"]]
    paths = _two_paths(roads, coordinates)
    network_features, topology = _network_features(paths)

    all_path_points = [point for path in paths for point in path]
    bounds = (
        min(point[0] for point in all_path_points) - 0.0005,
        min(point[1] for point in all_path_points) - 0.0005,
        max(point[0] for point in all_path_points) + 0.0005,
        max(point[1] for point in all_path_points) + 0.0005,
    )

    generated: dict[str, dict[str, Any]] = {}
    artifacts = {
        "network.geojson": _feature_collection(network_features),
        "candidate_channels.geojson": _feature_collection(
            [
                feature
                for feature in network_features
                if feature["properties"]["feature_type"] == "edge"
            ]
        ),
        "sites.geojson": _feature_collection(_site_features(site_source)),
    }
    for layer_name in ("roads", "buildings", "water", "landuse", "railways"):
        artifacts[f"background/{layer_name}.geojson"] = _background_subset(
            _read_json(staging / f"{layer_name}.geojson"), bounds, layer_name
        )

    for relative_name, document in artifacts.items():
        target = output_root / relative_name
        _write_json(target, document)
        generated[relative_name] = {
            "sha256": _sha256(target),
            "feature_count": len(document["features"]),
            "crs": "EPSG:4326",
            "classification": (
                "public_real_derived_subset"
                if relative_name.startswith("background/")
                else (
                    "synthetic"
                    if relative_name == "sites.geojson"
                    else "derived_geometry_with_synthetic_telecom_attributes"
                )
            ),
        }
        if relative_name.startswith("background/"):
            generated[relative_name]["geometry_ring_closures"] = document.get(
                "geometry_ring_closures", 0
            )

    scenarios = {
        "schema_version": 1,
        "dataset_id": EXPECTED_DATASET_ID,
        "scenarios": {
            "capacity_reroute": {
                "name": "容量不足自动绕行",
                "description": "约束前候选路线命中合成容量不足段，一次禁用后改走第二走廊。",
                "start_site_id": "A",
                "end_site_id": "B",
                "fiber_cores": 24,
                "prefer_existing_duct": True,
                "forbidden_asset_ids": [],
                "expected_issue_asset_ids": [topology["capacity_edge"]],
                "expected_status": "completed",
            },
            "forbidden_reroute": {
                "name": "显式禁用资源绕行",
                "description": "约束前候选路线命中显式禁用段，确认后改走第二走廊。",
                "start_site_id": "A",
                "end_site_id": "B",
                "fiber_cores": 12,
                "prefer_existing_duct": True,
                "forbidden_asset_ids": [topology["forbidden_edge"]],
                "expected_issue_asset_ids": [topology["forbidden_edge"]],
                "expected_status": "completed",
            },
            "no_path": {
                "name": "双走廊中断明确失败",
                "description": "两条独立候选走廊各禁用一段，应用约束后无路可达。",
                "start_site_id": "A",
                "end_site_id": "B",
                "fiber_cores": 12,
                "prefer_existing_duct": True,
                "forbidden_asset_ids": topology["no_path_cut_edges"],
                "expected_issue_asset_ids": topology["no_path_cut_edges"],
                "expected_status": "failed",
            },
        },
    }
    scenarios_path = output_root / "scenarios.json"
    _write_json(scenarios_path, scenarios)
    generated["scenarios.json"] = {
        "sha256": _sha256(scenarios_path),
        "scenario_count": len(scenarios["scenarios"]),
        "classification": "synthetic_competition_configuration",
    }

    manifest = {
        "schema_version": 1,
        "dataset_id": EXPECTED_DATASET_ID,
        "dataset_name": "上海公开 GIS 背景上的合成通信候选路线竞赛样例",
        "output_crs": "EPSG:4326",
        "build_rule": "two shortest edge-disjoint paths sorted by geodesic length; fixed attribute rules",
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
        "source_dataset": {
            "source": source_manifest["original_source"],
            "osm_base_timestamp": source_manifest["osm_base_timestamp"],
            "bounding_box": source_manifest["bounding_box"],
            "license": source_manifest["data_license"],
            "required_attribution": source_manifest["required_attribution"],
            "selected_layer_sha256": {
                name: entry["sha256"] for name, entry in source_manifest["layers"].items()
            },
        },
        "topology_evidence": {
            "edge_disjoint_path_count_used": 2,
            "path_lengths_m": [
                round(sum(_distance_m(left, right) for left, right in zip(path, path[1:])), 2)
                for path in paths
            ],
            "path_edge_counts": [len(path) - 1 for path in paths],
            **topology,
        },
        "classification_boundary": {
            "background": "public_real_derived_subset",
            "sites": "synthetic",
            "candidate_channel_geometry": "derived_from_public_road_geometry",
            "telecom_asset_type_capacity_status_cost": "synthetic",
            "outputs": "derived_competition_output",
        },
        "generated_files": generated,
        "required_notice": "© OpenStreetMap contributors; ODbL 1.0",
        "limitations": [
            "Only selected OSM way geometries are used; multipolygon relations are not assembled.",
            "Candidate channels are not real ducts, cables, chambers, or carrier assets.",
            "Capacity, occupancy, availability, laying type, cost multiplier, and BOM are synthetic.",
            "Competition sample only; not a formal construction drawing.",
        ],
    }
    manifest_path = output_root / "source_manifest.json"
    _write_json(manifest_path, manifest)
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="构建并审计竞赛离线数据包")
    parser.add_argument("--staging", type=Path, default=DEFAULT_STAGING)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    manifest = build_dataset(args.staging.resolve(), args.output_root.resolve())
    print(manifest)
    print(_sha256(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
