from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from agent.outputs import OUTPUT_FILENAMES, write_outputs
from agent.workflow import run_workflow
from run_demo import main
from telecom_core.validation import validate_route


REPO_ROOT = Path(__file__).resolve().parents[2]
REQUEST = "从 A 机房到 B 基站规划一条 24 芯光缆，优先使用已有管道。"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_five_outputs_match_completed_state(tmp_path):
    state = run_workflow(REQUEST)
    written = write_outputs(state, tmp_path)

    assert {path.name for path in written} == set(OUTPUT_FILENAMES)
    assert {path.name for path in tmp_path.iterdir()} == set(OUTPUT_FILENAMES)

    first_geojson = _read_json(tmp_path / "first_route.geojson")
    final_geojson = _read_json(tmp_path / "final_route.geojson")
    first_properties = first_geojson["features"][0]["properties"]
    final_properties = final_geojson["features"][0]["properties"]
    assert first_geojson["type"] == final_geojson["type"] == "FeatureCollection"
    assert first_properties["route_id"] == "R001"
    assert first_properties["stage"] == "first"
    assert "D017" in first_properties["edge_ids"]
    assert final_properties["route_id"] == "R002"
    assert final_properties["stage"] == "final"
    assert "D017" not in final_properties["edge_ids"]
    assert final_geojson["features"][0]["geometry"] == state["final_route"]["geometry"]

    report = _read_json(tmp_path / "validation_report.json")
    assert report == {
        "status": "completed",
        "validation_history": state["validation_history"],
        "forbidden_asset_ids": ["D017"],
        "repair_count": 1,
        "error": None,
    }
    bom = _read_json(tmp_path / "bom.json")
    assert bom == state["bom_result"]
    assert bom["used_edge_ids"] == final_properties["edge_ids"]
    assert bom["total_length_m"] == (
        bom["existing_duct_length_m"] + bom["new_build_length_m"]
    )
    assert bom["recommended_cable_length_m"] == round(
        bom["total_length_m"] * 1.10, 2
    )

    log_text = (tmp_path / "agent_log.md").read_text(encoding="utf-8")
    assert log_text.index("第一次路线") < log_text.index("第一次校核")
    assert log_text.index("第一次校核") < log_text.index("自动修复")
    assert log_text.index("自动修复") < log_text.index("第二次路线")
    assert log_text.index("第二次路线") < log_text.index("第二次校核")
    assert "R_CAPACITY/D017" in log_text
    assert "最终状态：completed" in log_text
    assert str(REPO_ROOT) not in log_text


def test_two_runs_produce_identical_core_json(tmp_path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    write_outputs(run_workflow(REQUEST), first_dir)
    write_outputs(run_workflow(REQUEST), second_dir)

    for filename in (
        "first_route.geojson",
        "final_route.geojson",
        "validation_report.json",
        "bom.json",
    ):
        assert (first_dir / filename).read_bytes() == (second_dir / filename).read_bytes()


def test_real_cli_returns_zero_and_prints_required_summary(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "run_demo.py"),
            "--output-dir",
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "第一次路线：D001 -> D017 -> D003" in result.stdout
    assert "第一次校核：FAIL R_CAPACITY D017" in result.stdout
    assert "自动修复：forbid D017" in result.stdout
    assert "第二次路线：N001 -> N002" in result.stdout
    assert "第二次校核：PASS" in result.stdout
    assert "建议光缆 440.00 m" in result.stdout
    assert set(path.name for path in tmp_path.iterdir()) == set(OUTPUT_FILENAMES)


def test_cli_returns_nonzero_when_second_route_still_fails(tmp_path, capsys):
    def fail_final_route(route, task, edge_records):
        result = validate_route(route, task, edge_records)
        if route["route_id"] == "R002":
            return {
                "passed": False,
                "violations": [
                    {
                        "rule_id": "R_CAPACITY",
                        "type": "duct_capacity",
                        "asset_id": "N001",
                        "severity": "error",
                        "message": "替代路线容量仍不足",
                        "repair_hint": "forbid_asset",
                    }
                ],
            }
        return result

    def failed_runner(user_text):
        return run_workflow(user_text, validator=fail_final_route)

    exit_code = main(
        [REQUEST, "--output-dir", str(tmp_path)],
        workflow_runner=failed_runner,
    )
    captured = capsys.readouterr()

    assert exit_code != 0
    assert "第二次校核仍失败" in captured.err
    report = _read_json(tmp_path / "validation_report.json")
    assert report["status"] == "failed"
    assert report["repair_count"] == 1
    assert len(report["validation_history"]) == 2
    assert not (tmp_path / "bom.json").exists()
