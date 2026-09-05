"""Portable competition dataset and scenario catalog access."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from telecom_core.data_loader import load_demo_network
from telecom_core.models import NetworkData

from .schema import DesignParameters


def data_root(repository_root: str | Path) -> Path:
    return Path(repository_root).resolve() / "data" / "competition"


def load_catalog(repository_root: str | Path) -> dict[str, Any]:
    path = data_root(repository_root) / "scenarios.json"
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if value.get("schema_version") != 1 or not isinstance(value.get("scenarios"), dict):
        raise ValueError(f"无效竞赛场景目录：{path}")
    return value


def load_competition_network(repository_root: str | Path) -> NetworkData:
    root = data_root(repository_root)
    return load_demo_network(root / "network.geojson", root / "sites.geojson")


def parameters_from_mapping(
    repository_root: str | Path, value: dict[str, Any]
) -> DesignParameters:
    catalog = load_catalog(repository_root)
    network = load_competition_network(repository_root)
    return DesignParameters.from_mapping(
        value,
        known_dataset_id=catalog["dataset_id"],
        known_scenarios=set(catalog["scenarios"]),
        known_site_ids=set(network.sites),
        known_asset_ids=set(network.edge_records),
    )


def parameters_for_scenario(
    repository_root: str | Path, scenario_id: str
) -> DesignParameters:
    catalog = load_catalog(repository_root)
    try:
        scenario = catalog["scenarios"][scenario_id]
    except KeyError as exc:
        raise ValueError(f"未知场景：{scenario_id}") from exc
    value = {"dataset_id": catalog["dataset_id"], "scenario_id": scenario_id, **scenario}
    return parameters_from_mapping(repository_root, value)
