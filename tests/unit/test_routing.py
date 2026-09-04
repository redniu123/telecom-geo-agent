from __future__ import annotations

import copy

import pytest

from telecom_core import RoutePlanningError, load_demo_network, plan_route


def test_first_route_uses_low_cost_d017(telecom_task):
    network = load_demo_network()

    route = plan_route(telecom_task, network, [], "R001")

    assert route["route_id"] == "R001"
    assert route["edge_ids"] == ["D001", "D017", "D003"]
    assert "D017" in route["edge_ids"]
    assert route["relative_cost"] == 175.0
    assert route["total_length_m"] == 350.0
    assert route["forbidden_asset_ids_applied"] == []


def test_second_route_excludes_d017_and_costs_more(telecom_task):
    network = load_demo_network()
    first = plan_route(telecom_task, network, [], "R001")

    second = plan_route(telecom_task, network, ["D017"], "R002")

    assert second["route_id"] == "R002"
    assert second["edge_ids"] == ["N001", "N002"]
    assert "D017" not in second["edge_ids"]
    assert second["relative_cost"] == 444.0
    assert second["relative_cost"] > first["relative_cost"]
    assert second["total_length_m"] == 400.0
    assert second["forbidden_asset_ids_applied"] == ["D017"]


def test_unavailable_shortcut_is_excluded_without_capacity_filtering(telecom_task):
    network = load_demo_network()

    route = plan_route(telecom_task, network, [], "R001")

    assert "U001" not in route["edge_ids"]
    assert "D017" in route["edge_ids"]


def test_forbidden_assets_that_disconnect_start_raise_clear_error(telecom_task):
    network = load_demo_network()

    with pytest.raises(RoutePlanningError) as error:
        plan_route(telecom_task, network, ["D001", "N001"], "R002")

    message = str(error.value)
    assert "site 'A' (N1)" in message
    assert "site 'B' (N4)" in message
    assert "D001" in message and "N001" in message


def test_reverse_route_reverses_each_segment_geometry():
    network = load_demo_network()
    task = {
        "task_type": "fiber_route",
        "start_site_id": "B",
        "end_site_id": "A",
        "fiber_cores": 24,
        "prefer_existing_duct": True,
    }

    route = plan_route(task, network, [], "R-REVERSE")

    assert route["edge_ids"] == ["D003", "D017", "D001"]
    assert route["geometry"]["coordinates"][0] == network.sites["B"]["geometry"]["coordinates"]
    assert route["geometry"]["coordinates"][-1] == network.sites["A"]["geometry"]["coordinates"]
    for previous, current in zip(route["segments"], route["segments"][1:]):
        assert previous["geometry"]["coordinates"][-1] == current["geometry"]["coordinates"][0]


def test_equal_cost_route_tie_break_is_stable(telecom_task):
    network = load_demo_network()
    modified = copy.deepcopy(network.edge_records["N001"])
    # Make the alternative exactly equal in cost, then repeat to prove a stable choice.
    network.edge_records["N001"]["length_m"] = 100.0
    network.edge_records["N001"]["cost_multiplier"] = 1.0
    network.edge_records["N002"]["length_m"] = 75.0
    network.edge_records["N002"]["cost_multiplier"] = 1.0

    routes = [plan_route(telecom_task, network, [], f"R{index}") for index in range(5)]

    assert len({tuple(route["edge_ids"]) for route in routes}) == 1
    assert routes[0]["edge_ids"] == ["D001", "D017", "D003"]
    assert modified["edge_id"] == "N001"


def test_route_id_is_caller_supplied_and_required(telecom_task):
    with pytest.raises(RoutePlanningError, match="route_id"):
        plan_route(telecom_task, load_demo_network(), [], "")
