from __future__ import annotations

import copy

import pytest

from telecom_core import load_demo_network, plan_route, validate_route


def test_first_validation_fails_only_for_d017_capacity(telecom_task):
    network = load_demo_network()
    route = plan_route(telecom_task, network, [], "R001")

    result = validate_route(route, telecom_task, network.edge_records)

    assert result["passed"] is False
    assert result["violations"] == [
        {
            "rule_id": "R_CAPACITY",
            "type": "duct_capacity",
            "asset_id": "D017",
            "severity": "error",
            "message": "D017 剩余容量不足以承载 24 芯光缆",
            "repair_hint": "forbid_asset",
        }
    ]


def test_second_validation_passes(telecom_task):
    network = load_demo_network()
    route = plan_route(telecom_task, network, ["D017"], "R002")

    result = validate_route(route, telecom_task, network.edge_records)

    assert result == {"passed": True, "violations": []}


def test_new_build_capacity_is_not_checked(telecom_task):
    network = load_demo_network()
    route = plan_route(telecom_task, network, ["D017"], "R002")
    assert network.edge_records["N002"]["capacity_cores"] == 0

    result = validate_route(route, telecom_task, network.edge_records)

    assert result["passed"] is True


def test_unavailable_asset_is_reported_by_independent_validator(telecom_task):
    network = load_demo_network()
    route = plan_route(telecom_task, network, ["D017"], "R002")
    network.edge_records["N001"]["status"] = "unavailable"

    result = validate_route(route, telecom_task, network.edge_records)

    assert result["passed"] is False
    assert result["violations"][0]["rule_id"] == "R_ASSET_STATUS"
    assert result["violations"][0]["asset_id"] == "N001"
    assert result["violations"][0]["repair_hint"] == "forbid_asset"


def test_wrong_route_endpoint_is_reported(telecom_task):
    network = load_demo_network()
    route = plan_route(telecom_task, network, ["D017"], "R002")
    route["end_site_id"] = "C"

    result = validate_route(route, telecom_task, network.edge_records)

    assert result["passed"] is False
    assert result["violations"][0]["rule_id"] == "R_ENDPOINT"
    assert result["violations"][0]["asset_id"] is None


def test_edge_id_and_segment_order_must_match(telecom_task):
    network = load_demo_network()
    route = plan_route(telecom_task, network, ["D017"], "R002")
    route["edge_ids"] = list(reversed(route["edge_ids"]))

    with pytest.raises(ValueError, match="edge_ids"):
        validate_route(route, telecom_task, network.edge_records)


def test_validator_does_not_replan_or_mutate_inputs(telecom_task):
    network = load_demo_network()
    route = plan_route(telecom_task, network, [], "R001")
    before_route = copy.deepcopy(route)
    before_edges = copy.deepcopy(network.edge_records)

    validate_route(route, telecom_task, network.edge_records)

    assert route == before_route
    assert network.edge_records == before_edges
