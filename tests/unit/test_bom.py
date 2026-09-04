from __future__ import annotations

import copy

import pytest

from telecom_core import BOMCalculationError, calculate_bom, load_demo_network, plan_route


def test_bom_is_recomputed_from_second_route_segments(telecom_task):
    network = load_demo_network()
    route = plan_route(telecom_task, network, ["D017"], "R002")

    bom = calculate_bom(route)

    assert bom == {
        "total_length_m": 400.0,
        "existing_duct_length_m": 180.0,
        "new_build_length_m": 220.0,
        "recommended_cable_length_m": 440.0,
        "slack_ratio": 0.10,
        "used_edge_ids": ["N001", "N002"],
    }
    assert bom["existing_duct_length_m"] + bom["new_build_length_m"] == bom["total_length_m"]


def test_bom_rejects_edge_list_that_is_not_bound_to_segments(telecom_task):
    network = load_demo_network()
    route = plan_route(telecom_task, network, ["D017"], "R002")
    route["edge_ids"] = ["fabricated"]

    with pytest.raises(BOMCalculationError, match="edge_ids"):
        calculate_bom(route)


def test_bom_rejects_declared_total_that_disagrees_with_segments(telecom_task):
    network = load_demo_network()
    route = plan_route(telecom_task, network, ["D017"], "R002")
    route["total_length_m"] += 10

    with pytest.raises(BOMCalculationError, match="does not match segment sum"):
        calculate_bom(route)


def test_bom_rejects_unknown_asset_type(telecom_task):
    network = load_demo_network()
    route = plan_route(telecom_task, network, ["D017"], "R002")
    route = copy.deepcopy(route)
    route["segments"][0]["asset_type"] = "mystery"

    with pytest.raises(BOMCalculationError, match="unsupported asset_type"):
        calculate_bom(route)


def test_bom_rejects_unsuccessful_or_empty_route():
    route = {
        "success": False,
        "route_id": "R000",
        "start_site_id": "A",
        "end_site_id": "B",
        "segments": [],
        "edge_ids": [],
        "geometry": {"type": "LineString", "coordinates": []},
        "total_length_m": 0.0,
        "relative_cost": 0.0,
        "forbidden_asset_ids_applied": [],
    }

    with pytest.raises(BOMCalculationError, match="unsuccessful"):
        calculate_bom(route)
