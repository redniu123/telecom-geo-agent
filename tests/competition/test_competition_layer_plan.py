from pathlib import Path

from qgis_plugin.telecom_geo_agent.layer_plan import build_competition_layer_plan


ROOT = Path(__file__).resolve().parents[2]


def test_competition_layer_plan_has_stable_order_and_portable_sources():
    plan = build_competition_layer_plan(
        ROOT,
        "capacity_reroute",
        include_candidate_route=True,
        include_final_route=True,
    )
    assert plan.group_name == "通信工程智能设计 · capacity_reroute"
    assert [layer.key for layer in plan.layers] == [
        "landuse",
        "buildings",
        "water",
        "railways",
        "roads",
        "candidate_channels",
        "rooms",
        "base_stations",
        "candidate_route",
        "issues",
        "final_route",
    ]
    assert all(not layer.relative_path.is_absolute() for layer in plan.layers)
    assert plan.by_key("candidate_route").visible is False
    assert plan.by_key("final_route").visible is True
    assert plan.by_key("landuse").visible is False
    assert plan.by_key("candidate_channels").relative_path.as_posix() == (
        "data/competition/candidate_channels.geojson"
    )
    assert plan.by_key("candidate_channels").subset_expression is None
    assert plan.by_key("rooms").label_field == "site_id"
    plan.validate_sources()


def test_failed_plan_has_candidate_and_issues_but_no_final():
    plan = build_competition_layer_plan(
        ROOT,
        "no_path",
        include_candidate_route=True,
        include_final_route=False,
    )
    assert "candidate_route" in [layer.key for layer in plan.layers]
    assert "issues" in [layer.key for layer in plan.layers]
    assert "final_route" not in [layer.key for layer in plan.layers]
    plan.validate_sources()
