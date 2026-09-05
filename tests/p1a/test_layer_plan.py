from pathlib import Path

from qgis_plugin.telecom_geo_agent.layer_plan import build_layer_plan


def test_layer_plan_uses_portable_relative_sources_and_expected_visibility():
    root = Path(__file__).resolve().parents[2]
    plan = build_layer_plan(root)

    assert [layer.key for layer in plan.layers] == [
        "network",
        "sites",
        "first_route",
        "final_route",
        "issue_d017",
    ]
    assert all(not layer.relative_path.is_absolute() for layer in plan.layers)
    assert plan.by_key("first_route").visible is False
    assert plan.by_key("final_route").visible is True
    assert plan.by_key("issue_d017").visible is True
    assert plan.by_key("issue_d017").style == "issue"
    assert plan.by_key("issue_d017").subset_expression == '"edge_id" = \'D017\''
    plan.validate_sources()


def test_layer_plan_rejects_missing_outputs(tmp_path):
    plan = build_layer_plan(tmp_path)

    try:
        plan.validate_sources()
    except FileNotFoundError as exc:
        assert "data/demo/network.geojson" in str(exc)
    else:
        raise AssertionError("missing layer sources must fail closed")


def test_layer_plan_can_represent_no_issue_and_failed_final_route():
    root = Path(__file__).resolve().parents[2]
    plan = build_layer_plan(
        root,
        issue_assets=(),
        first_route_id="R001",
        final_route_id="R001",
    )
    assert all(not layer.key.startswith("issue") for layer in plan.layers)
    assert plan.by_key("final_route").name == "最终路线 R001（PASS）"

    failed = build_layer_plan(
        root,
        issue_assets=("D017", "N001"),
        final_route_passed=False,
    )
    assert failed.by_key("final_route").style == "failed_route"
    assert failed.by_key("issues").name == "D017、N001 问题段（合成测试数据）"
