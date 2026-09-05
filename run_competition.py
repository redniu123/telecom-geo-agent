"""CLI for the three offline competition scenarios."""

from __future__ import annotations

import argparse
from pathlib import Path

from competition.catalog import load_catalog, load_competition_network, parameters_for_scenario
from competition.outputs import write_workflow_outputs
from competition.workflow import run_design_workflow


REPO_ROOT = Path(__file__).resolve().parent


def run_scenario(scenario_id: str) -> dict:
    parameters = parameters_for_scenario(REPO_ROOT, scenario_id)
    state = run_design_workflow(
        parameters,
        REPO_ROOT,
        confirmed_fingerprint=parameters.fingerprint,
    )
    network = load_competition_network(REPO_ROOT)
    write_workflow_outputs(
        state,
        network,
        REPO_ROOT / "outputs" / "competition" / scenario_id,
    )
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="运行离线通信线路竞赛场景")
    parser.add_argument("--scenario", choices=("capacity_reroute", "forbidden_reroute", "no_path"))
    parser.add_argument("--all", action="store_true", help="运行全部场景并按目录中的期望状态验收")
    args = parser.parse_args()
    if bool(args.scenario) == bool(args.all):
        parser.error("必须且只能选择 --scenario 或 --all")

    catalog = load_catalog(REPO_ROOT)
    scenario_ids = list(catalog["scenarios"]) if args.all else [args.scenario]
    matches = True
    for scenario_id in scenario_ids:
        state = run_scenario(scenario_id)
        expected = catalog["scenarios"][scenario_id]["expected_status"]
        print(
            f"{scenario_id}: actual={state['status']} expected={expected} "
            f"elapsed_ms={state['system_elapsed_ms']:.3f} error={state['error'] or '-'}"
        )
        matches = matches and state["status"] == expected
    if args.all:
        return 0 if matches else 1
    return 0 if state["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
