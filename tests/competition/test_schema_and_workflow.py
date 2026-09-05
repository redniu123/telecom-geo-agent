from pathlib import Path

import pytest

from competition.catalog import parameters_for_scenario, parameters_from_mapping
from competition.schema import ParameterValidationError
from competition.workflow import run_design_workflow


ROOT = Path(__file__).resolve().parents[2]


def _run(scenario_id: str):
    parameters = parameters_for_scenario(ROOT, scenario_id)
    return parameters, run_design_workflow(
        parameters,
        ROOT,
        confirmed_fingerprint=parameters.fingerprint,
    )


def test_confirmation_fails_closed_when_missing_or_stale():
    parameters = parameters_for_scenario(ROOT, "capacity_reroute")
    with pytest.raises(ParameterValidationError, match="尚未确认"):
        run_design_workflow(parameters, ROOT, confirmed_fingerprint=None)
    with pytest.raises(ParameterValidationError, match="发生变化"):
        run_design_workflow(parameters, ROOT, confirmed_fingerprint="0" * 64)


def test_unknown_endpoint_fails_closed_before_planning():
    parameters = parameters_for_scenario(ROOT, "capacity_reroute").as_dict()
    parameters["end_site_id"] = "REAL-UNKNOWN-SITE"
    with pytest.raises(ParameterValidationError, match="终点不存在或未授权"):
        parameters_from_mapping(ROOT, parameters)


def test_clearing_existing_duct_preference_uses_length_only_weight():
    raw = parameters_for_scenario(ROOT, "capacity_reroute").as_dict()
    raw["prefer_existing_duct"] = False
    parameters = parameters_from_mapping(ROOT, raw)
    state = run_design_workflow(
        parameters,
        ROOT,
        confirmed_fingerprint=parameters.fingerprint,
    )
    assert state["status"] == "completed"
    assert state["candidate_route"]["relative_cost"] == state["candidate_route"][
        "total_length_m"
    ]
    assert state["final_route"]["relative_cost"] == state["final_route"][
        "total_length_m"
    ]
    assert state["events"][1]["details"]["routing_weight_mode"] == "length_only"


def test_capacity_scenario_really_fails_then_avoids_bottleneck_and_passes():
    _, state = _run("capacity_reroute")
    assert state["status"] == "completed"
    assert state["candidate_route"]["edge_ids"] == [
        f"C1-{index:03d}" for index in range(1, 34)
    ]
    assert state["validation_history"][0] == {
        "passed": False,
        "violations": [
            {
                "rule_id": "R_CAPACITY",
                "type": "duct_capacity",
                "asset_id": "C1-017",
                "severity": "error",
                "message": "C1-017 剩余容量不足以承载 24 芯光缆",
                "repair_hint": "forbid_asset",
            }
        ],
    }
    assert state["forbidden_asset_ids_applied"] == ["C1-017"]
    assert "C1-017" not in state["final_route"]["edge_ids"]
    assert state["final_route"]["edge_ids"] == [
        f"C2-{index:03d}" for index in range(1, 47)
    ]
    assert state["validation_history"][-1] == {"passed": True, "violations": []}
    assert state["bom_result"]["used_edge_ids"] == state["final_route"]["edge_ids"]
    assert state["bom_result"]["total_length_m"] == state["final_route"]["total_length_m"]


def test_explicit_forbidden_scenario_replans_without_forbidden_asset():
    _, state = _run("forbidden_reroute")
    first = state["validation_history"][0]
    assert state["status"] == "completed"
    assert first["passed"] is False
    assert first["violations"][0]["rule_id"] == "R_USER_FORBIDDEN"
    assert first["violations"][0]["asset_id"] == "C1-009"
    assert "C1-009" not in state["final_route"]["edge_ids"]
    assert state["validation_history"][-1]["passed"] is True


def test_no_path_is_explicit_failure_without_final_route_or_bom():
    _, state = _run("no_path")
    assert state["status"] == "failed"
    assert state["forbidden_asset_ids_applied"] == ["C1-017", "C2-024"]
    assert state["final_route"] is None
    assert state["bom_result"] is None
    assert "no route from site 'A'" in state["error"]
    assert state["events"][-1]["event_type"] == "workflow_failed"


def test_same_structured_input_has_deterministic_domain_results():
    _, left = _run("capacity_reroute")
    _, right = _run("capacity_reroute")
    for field in (
        "parameters",
        "parameter_fingerprint",
        "candidate_route",
        "final_route",
        "validation_history",
        "forbidden_asset_ids_applied",
        "repair_count",
        "bom_result",
        "status",
        "error",
    ):
        assert left[field] == right[field]
