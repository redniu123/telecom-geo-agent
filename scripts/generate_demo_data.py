"""Generate the fixed, synthetic and reproducible P0 GeoJSON demo data."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any


DEMO_SEED = 20260904
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "data" / "demo"


NODE_COORDINATES = {
    "N1": [121.4700, 31.2300],
    "N2": [121.4800, 31.2300],
    "N3": [121.4900, 31.2350],
    "N4": [121.5000, 31.2400],
    "N5": [121.4800, 31.2450],
}


EDGE_DEFINITIONS = [
    ("D001", "N1", "N2", "existing_duct", 100.0, 0.50, 96, 20, "available"),
    ("D017", "N2", "N3", "existing_duct", 120.0, 0.50, 48, 32, "available"),
    ("D003", "N3", "N4", "existing_duct", 130.0, 0.50, 96, 50, "available"),
    ("N001", "N1", "N5", "existing_duct", 180.0, 1.00, 72, 20, "available"),
    ("N002", "N5", "N4", "new_build", 220.0, 1.20, 0, 0, "available"),
    ("U001", "N1", "N4", "existing_duct", 50.0, 0.10, 96, 0, "unavailable"),
]


def _feature_sort_key(feature: dict[str, Any]) -> tuple[str, str]:
    properties = feature["properties"]
    identity = properties.get("node_id", properties.get("edge_id", ""))
    return properties["feature_type"], identity


def build_documents() -> tuple[dict[str, Any], dict[str, Any]]:
    """Build in-memory documents using the fixed seed and stable final order."""

    randomizer = random.Random(DEMO_SEED)
    network_features: list[dict[str, Any]] = []
    for node_id, coordinates in NODE_COORDINATES.items():
        network_features.append(
            {
                "type": "Feature",
                "id": f"node:{node_id}",
                "properties": {
                    "feature_type": "node",
                    "node_id": node_id,
                    "status": "available",
                },
                "geometry": {"type": "Point", "coordinates": coordinates},
            }
        )
    for (
        edge_id,
        from_node,
        to_node,
        asset_type,
        length_m,
        cost_multiplier,
        capacity_cores,
        used_cores,
        status,
    ) in EDGE_DEFINITIONS:
        network_features.append(
            {
                "type": "Feature",
                "id": f"edge:{edge_id}",
                "properties": {
                    "feature_type": "edge",
                    "edge_id": edge_id,
                    "from_node": from_node,
                    "to_node": to_node,
                    "asset_type": asset_type,
                    "length_m": length_m,
                    "cost_multiplier": cost_multiplier,
                    "capacity_cores": capacity_cores,
                    "used_cores": used_cores,
                    "status": status,
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [NODE_COORDINATES[from_node], NODE_COORDINATES[to_node]],
                },
            }
        )
    # Seed controls construction order; explicit sorting controls serialized order.
    randomizer.shuffle(network_features)
    network_features.sort(key=_feature_sort_key)

    sites = [
        ("A", "A 机房", "telecom_room", "N1"),
        ("B", "B 基站", "base_station", "N4"),
    ]
    site_features = [
        {
            "type": "Feature",
            "id": f"site:{site_id}",
            "properties": {
                "site_id": site_id,
                "name": name,
                "site_type": site_type,
                "node_id": node_id,
                "status": "available",
            },
            "geometry": {"type": "Point", "coordinates": NODE_COORDINATES[node_id]},
        }
        for site_id, name, site_type, node_id in sites
    ]
    metadata = {
        "source": "synthetic fixed P0 demo; not a real engineering dataset",
        "seed": DEMO_SEED,
        "coordinate_order": "longitude, latitude",
    }
    return (
        {"type": "FeatureCollection", "metadata": metadata, "features": site_features},
        {"type": "FeatureCollection", "metadata": metadata, "features": network_features},
    )


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(serialized, encoding="utf-8", newline="\n")


def write_demo_data(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> tuple[Path, Path]:
    destination = Path(output_dir)
    sites_document, network_document = build_documents()
    sites_path = destination / "sites.geojson"
    network_path = destination / "network.geojson"
    _write_json(sites_path, sites_document)
    _write_json(network_path, network_document)
    return sites_path, network_path


if __name__ == "__main__":
    written = write_demo_data()
    for path in written:
        print(path.relative_to(REPOSITORY_ROOT).as_posix())
