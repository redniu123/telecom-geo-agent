import csv
import hashlib
import json
from pathlib import Path

from competition.catalog import load_competition_network, parameters_for_scenario
from competition.metrics import calculate_metrics, read_csv
from competition.outputs import write_workflow_outputs
from competition.workflow import run_design_workflow


ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_repository_dataset_manifest_matches_every_generated_file():
    root = ROOT / "data" / "competition"
    manifest = json.loads((root / "source_manifest.json").read_text(encoding="utf-8"))
    assert manifest["required_notice"] == "© OpenStreetMap contributors; ODbL 1.0"
    assert manifest["classification_boundary"] == {
        "background": "public_real_derived_subset",
        "candidate_channel_geometry": "derived_from_public_road_geometry",
        "outputs": "derived_competition_output",
        "sites": "synthetic",
        "telecom_asset_type_capacity_status_cost": "synthetic",
    }
    for relative, evidence in manifest["generated_files"].items():
        path = root / relative
        assert path.is_file()
        assert _sha256(path) == evidence["sha256"]
        if path.suffix == ".geojson":
            value = json.loads(path.read_text(encoding="utf-8"))
            assert len(value["features"]) == evidence["feature_count"]


def test_every_derived_background_polygon_ring_is_closed():
    background = ROOT / "data" / "competition" / "background"
    for path in sorted(background.glob("*.geojson")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for feature in document["features"]:
            geometry = feature.get("geometry") or {}
            geometry_type = geometry.get("type")
            coordinates = geometry.get("coordinates", [])
            polygons = (
                [coordinates]
                if geometry_type == "Polygon"
                else coordinates
                if geometry_type == "MultiPolygon"
                else []
            )
            for polygon in polygons:
                for ring in polygon:
                    assert len(ring) >= 4, f"{path.name}: polygon ring too short"
                    assert ring[0] == ring[-1], f"{path.name}: polygon ring is open"


def test_network_is_two_corridors_with_synthetic_telecom_attributes():
    network = load_competition_network(ROOT)
    assert len(network.nodes) == 79
    assert len(network.edge_records) == 79
    assert network.edge_records["C1-017"]["capacity_cores"] == 48
    assert network.edge_records["C1-017"]["used_cores"] == 32
    network_document = json.loads(
        (ROOT / "data" / "competition" / "network.geojson").read_text(encoding="utf-8")
    )
    edge_properties = [
        feature["properties"]
        for feature in network_document["features"]
        if feature["properties"]["feature_type"] == "edge"
    ]
    assert all(
        edge["data_class"]
        == "derived_geometry_with_synthetic_telecom_attributes"
        for edge in edge_properties
    )
    site_document = json.loads(
        (ROOT / "data" / "competition" / "sites.geojson").read_text(encoding="utf-8")
    )
    assert all(
        feature["properties"]["data_class"] == "synthetic"
        for feature in site_document["features"]
    )


def test_failed_output_removes_stale_bom_and_final_route(tmp_path):
    network = load_competition_network(ROOT)
    success_parameters = parameters_for_scenario(ROOT, "capacity_reroute")
    success = run_design_workflow(
        success_parameters,
        ROOT,
        confirmed_fingerprint=success_parameters.fingerprint,
    )
    write_workflow_outputs(success, network, tmp_path)
    assert (tmp_path / "bom.json").is_file()
    assert (tmp_path / "final_route.geojson").is_file()

    failed_parameters = parameters_for_scenario(ROOT, "no_path")
    failed = run_design_workflow(
        failed_parameters,
        ROOT,
        confirmed_fingerprint=failed_parameters.fingerprint,
    )
    write_workflow_outputs(failed, network, tmp_path)
    assert not (tmp_path / "bom.json").exists()
    assert not (tmp_path / "final_route.geojson").exists()
    report = json.loads((tmp_path / "validation_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert "no route" in report["error"]


def test_blank_human_template_cannot_claim_threshold():
    manual = read_csv(ROOT / "competition" / "benchmark" / "manual_baseline_template.csv")
    system = read_csv(ROOT / "outputs" / "competition" / "benchmark" / "system_runs.csv")
    report = calculate_metrics(manual, system)
    assert report["overall_status"] == "pending_human_baseline"
    assert all(item["competition_threshold_met"] is None for item in report["scenarios"])


def test_metric_formula_uses_evidenced_human_rows_only():
    manual = [
        {
            "scenario_id": scenario,
            "elapsed_seconds": "100",
            "manual_operations": "20",
            "system_observed_operations": "8",
            "evidence_ref": f"evidence/{scenario}.mp4",
        }
        for scenario in ("capacity_reroute", "forbidden_reroute", "no_path")
    ]
    system = [
        {"scenario_id": scenario, "elapsed_seconds": "50", "status": "completed"}
        for scenario in ("capacity_reroute", "forbidden_reroute")
    ] + [{"scenario_id": "no_path", "elapsed_seconds": "50", "status": "failed"}]
    report = calculate_metrics(manual, system)
    assert report["overall_status"] == "calculated"
    for item in report["scenarios"]:
        assert item["efficiency_improvement_percent"] == 50.0
        assert item["manual_operation_reduction_percent"] == 60.0
        assert item["competition_threshold_met"] is True


def test_competition_handoff_docs_keep_manual_and_data_boundaries_explicit():
    docs = ROOT / "docs" / "competition"
    required = {
        "00_竞赛总体技术设计.md": ("面向 QGIS", "公开 OSM 背景"),
        "01_功能需求证据矩阵.md": ("功能—需求—证据矩阵", "人工证据"),
        "02_可复现验证报告.md": ("可复现验证报告", "pending_human_baseline"),
        "03_3-5分钟演示脚本.md": ("3–5 分钟演示", "禁止性表述"),
        "04_QGIS安装运行卸载与GUI验收.md": ("GUI 验收", "自动 smoke 不能代填"),
        "05_数据来源许可与边界.md": ("OpenStreetMap", "是否可称为现实通信资产"),
        "06_限制与待人工验证.md": ("待 Quimer 人工验证", "不能声称"),
    }
    for filename, phrases in required.items():
        text = (docs / filename).read_text(encoding="utf-8")
        assert all(phrase in text for phrase in phrases), filename
