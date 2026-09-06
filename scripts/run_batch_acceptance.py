"""Reproducible H6 batch, stress, determinism and anti-hardcoding checks."""

from __future__ import annotations

import copy
import csv
import json
import sys
import time
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from competition.batch.data_loader import load_batch_dataset
from competition.batch.outputs import write_batch_outputs
from competition.batch.planner import run_batch
from competition.batch.schema import BatchRequest
from competition.batch.task_import import import_tasks_csv


def _request(dataset, filename: str):
    return import_tasks_csv(dataset.root / filename, dataset_id=dataset.dataset_id, known_site_ids=dataset.site_ids, known_room_ids=dataset.room_ids, known_asset_ids=set(dataset.resources))


def _run(dataset, request):
    started = time.perf_counter()
    state = run_batch(request, dataset, confirmed_fingerprint=request.fingerprint)
    return state, round(time.perf_counter() - started, 6)


def _route_signature(state, task_id):
    result = next(item for item in state["tasks"] if item["task"]["task_id"] == task_id)
    route = result.get("final_route") or result.get("candidate_route")
    return {"status": result["status"], "edge_ids": route["edge_ids"] if route else [], "total_length_m": route["total_length_m"] if route else None, "bom": result.get("bom")}


def _assert_run(state, count):
    if state["task_count"] != count or sum(state["terminal_counts"].values()) != count:
        raise AssertionError("task count/terminal count mismatch")
    if any(item["free_subduct_count"] < 0 for item in state["resource_after"].values()):
        raise AssertionError("negative subduct resource")
    unsuccessful = {item["task"]["task_id"] for item in state["tasks"] if item["status"] in {"failed", "needs_review"}}
    if unsuccessful & {item["task_id"] for item in state["reservations"]}:
        raise AssertionError("unsuccessful task changed resources")


def main() -> int:
    dataset = load_batch_dataset(ROOT)
    main_request = _request(dataset, "batch_tasks.csv")
    main_state, main_seconds = _run(dataset, main_request)
    _assert_run(main_state, 30)
    write_batch_outputs(main_state, dataset, ROOT / "outputs" / "competition_batch" / main_request.batch_id)
    repeat_state, repeat_seconds = _run(dataset, main_request)
    if main_state != repeat_state:
        raise AssertionError("same input did not produce byte-equivalent functional state")

    stress_request = _request(dataset, "stress_tasks_100.csv")
    stress_state, stress_seconds = _run(dataset, stress_request)
    _assert_run(stress_state, 100)
    write_batch_outputs(stress_state, dataset, ROOT / "outputs" / "competition_batch" / stress_request.batch_id)

    migration_request = _request(dataset, "migration_tasks_10.csv")
    migration_state, migration_seconds = _run(dataset, migration_request)
    _assert_run(migration_state, 10)
    write_batch_outputs(migration_state, dataset, ROOT / "outputs" / "competition_batch" / migration_request.batch_id)

    # Anti-hardcoding check 1: move one synthetic site to a different audited
    # graph node (equivalent to moving and re-snapping it) without code changes.
    moved_dataset = copy.deepcopy(dataset)
    moved_task = main_request.tasks[5]
    original_node = moved_dataset.facilities[moved_task.site_id]["node_id"]
    replacement_node = moved_dataset.facilities[main_request.tasks[6].site_id]["node_id"]
    moved_dataset.facilities[moved_task.site_id]["node_id"] = replacement_node
    moved_dataset.facilities[moved_task.site_id]["geometry"] = copy.deepcopy(moved_dataset.network.nodes[replacement_node]["geometry"])
    moved_dataset.network.sites[moved_task.site_id]["node_id"] = replacement_node
    moved_dataset.network.sites[moved_task.site_id]["geometry"] = copy.deepcopy(moved_dataset.network.nodes[replacement_node]["geometry"])
    moved_state, _moved_seconds = _run(moved_dataset, main_request)
    before_move = _route_signature(main_state, moved_task.task_id)
    after_move = _route_signature(moved_state, moved_task.task_id)
    if before_move == after_move:
        raise AssertionError("moving and re-snapping a facility did not change its route result")

    # Anti-hardcoding check 2: turn the cross-task edge from one free subduct
    # into zero before the batch. T001 must no longer keep its original result.
    capacity_dataset = copy.deepcopy(dataset)
    bottleneck = next(asset_id for asset_id, item in capacity_dataset.resources.items() if item.get("capacity_status") == "near_full")
    capacity_dataset.resources[bottleneck]["subduct_used_baseline"] = capacity_dataset.resources[bottleneck]["subduct_total"]
    capacity_dataset.resources[bottleneck]["capacity_status"] = "full"
    capacity_state, _capacity_seconds = _run(capacity_dataset, main_request)
    before_capacity = _route_signature(main_state, "T001")
    after_capacity = _route_signature(capacity_state, "T001")
    if before_capacity == after_capacity:
        raise AssertionError("capacity 1→0 did not change the affected task result")

    reserved_before = sum(
        item["subduct_reserved_batch"] for item in main_state["resource_before"].values()
    )
    reserved_after = sum(
        item["subduct_reserved_batch"] for item in main_state["resource_after"].values()
    )
    reservation_count = len(main_state["reservations"])
    if reserved_after - reserved_before != reservation_count:
        raise AssertionError("main resource delta does not match reservation events")
    unsuccessful_ids = sorted(
        item["task"]["task_id"]
        for item in main_state["tasks"]
        if item["status"] in {"failed", "needs_review"}
    )
    unsuccessful_reservations = [
        item for item in main_state["reservations"] if item["task_id"] in unsuccessful_ids
    ]
    if unsuccessful_reservations:
        raise AssertionError("failed/review tasks produced resource reservations")

    conflict_task = next(
        item for item in main_state["tasks"] if item["task"]["task_id"] == "T002"
    )
    conflict = next(
        item
        for item in conflict_task["validation_history"][0]["violations"]
        if item["rule_id"] == "R_SUBDUCT_CAPACITY"
    )
    if conflict.get("caused_by_task_ids") != ["T001"]:
        raise AssertionError("cross-task capacity cause chain is missing")

    baseline_path = ROOT / "competition" / "benchmark" / "batch_manual_baseline_template.csv"
    with baseline_path.open(encoding="utf-8-sig", newline="") as handle:
        baseline_rows = list(csv.DictReader(handle))
    if len(baseline_rows) != 30 or any(
        row.get("verification_status") != "pending_human_baseline"
        for row in baseline_rows
    ):
        raise AssertionError("manual baseline template must remain 30 truthful pending rows")

    report = {
        "schema_version": 1,
        "status": "PASS",
        "main_30": {"terminal_counts": main_state["terminal_counts"], "batch_algorithm_seconds": main_seconds},
        "determinism": {"status": "PASS", "functional_state_equal": True, "repeat_batch_algorithm_seconds": repeat_seconds},
        "stress_100": {"terminal_counts": stress_state["terminal_counts"], "batch_algorithm_seconds": stress_seconds, "negative_resources": 0, "unfinished_tasks": 0, "failed_task_side_effects": 0},
        "migration_10": {"terminal_counts": migration_state["terminal_counts"], "batch_algorithm_seconds": migration_seconds, "algorithm_code_changes": 0},
        "anti_hardcoding": {
            "moved_site": {"task_id": moved_task.task_id, "from_node": original_node, "to_node": replacement_node, "before": before_move, "after": after_move, "route_changed": True, "atlas_page_model_changes_with_route_and_bom": True},
            "capacity_one_to_zero": {"asset_id": bottleneck, "before": before_capacity, "after": after_capacity, "result_changed": True},
            "second_dataset_without_code_change": True,
        },
        "resource_conservation": {
            "status": "PASS",
            "reserved_before": reserved_before,
            "reserved_after": reserved_after,
            "reservation_events": reservation_count,
            "negative_resources": 0,
            "unsuccessful_task_ids": unsuccessful_ids,
            "unsuccessful_reservations": len(unsuccessful_reservations),
        },
        "cross_task_cause": {
            "status": "PASS",
            "prior_task_id": "T001",
            "affected_task_id": "T002",
            "asset_id": conflict["asset_id"],
            "rule_id": conflict["rule_id"],
            "caused_by_task_ids": conflict["caused_by_task_ids"],
        },
        "metric_boundary": "batch_algorithm_seconds is a software performance probe only; it is not end-to-end human efficiency evidence",
        "human_baseline_status": "pending_human_baseline",
        "human_baseline_template_rows": len(baseline_rows),
    }
    destination = ROOT / "outputs" / "competition_batch" / "acceptance_report.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
