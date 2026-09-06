import csv
import json
from dataclasses import replace
from pathlib import Path

from competition.batch.data_loader import load_batch_dataset
from competition.batch.outputs import write_batch_outputs
from competition.batch.planner import TERMINAL_STATUSES, run_batch
from competition.batch.schema import BatchRequest
from competition.batch.task_import import import_tasks_csv


ROOT = Path(__file__).resolve().parents[2]


def _request(dataset, filename="batch_tasks.csv"):
    return import_tasks_csv(dataset.root / filename, dataset_id=dataset.dataset_id, known_site_ids=dataset.site_ids, known_room_ids=dataset.room_ids, known_asset_ids=set(dataset.resources))


def _run(filename="batch_tasks.csv"):
    dataset = load_batch_dataset(ROOT)
    request = _request(dataset, filename)
    return dataset, request, run_batch(request, dataset, confirmed_fingerprint=request.fingerprint)


def test_main_30_has_four_truthful_terminal_types_and_one_bounded_replan():
    _dataset, _request_value, state = _run()
    assert state["task_count"] == 30
    assert set(state["terminal_counts"]) == TERMINAL_STATUSES
    assert state["terminal_counts"]["completed_direct"] >= 2
    assert state["terminal_counts"]["completed_rerouted"] >= 2
    assert state["terminal_counts"]["needs_review"] >= 1
    assert state["terminal_counts"]["failed"] >= 1
    assert all(item["repair_count"] in {0, 1} for item in state["tasks"])


def test_cross_task_conflict_names_prior_reserving_task():
    _dataset, _request_value, state = _run()
    task = next(item for item in state["tasks"] if item["task"]["task_id"] == "T002")
    assert task["status"] == "completed_rerouted"
    assert task["caused_by_task_ids"] == ["T001"]
    assert any(item.get("caused_by_task_ids") == ["T001"] for item in task["validation_history"][0]["violations"])


def test_failed_and_review_tasks_have_zero_resource_side_effects():
    _dataset, _request_value, state = _run()
    unsuccessful = {item["task"]["task_id"] for item in state["tasks"] if item["status"] in {"failed", "needs_review"}}
    assert unsuccessful
    assert not unsuccessful & {item["task_id"] for item in state["reservations"]}
    assert all(not item["resource_changes"] and item["bom"] is None for item in state["tasks"] if item["task"]["task_id"] in unsuccessful)


def test_same_input_is_functionally_deterministic():
    dataset = load_batch_dataset(ROOT)
    request = _request(dataset)
    left = run_batch(request, dataset, confirmed_fingerprint=request.fingerprint)
    right = run_batch(request, dataset, confirmed_fingerprint=request.fingerprint)
    assert left == right


def test_second_ten_task_dataset_runs_without_algorithm_change():
    _dataset, _request_value, state = _run("migration_tasks_10.csv")
    assert state["task_count"] == 10
    assert sum(state["terminal_counts"].values()) == 10


def test_moving_task_site_changes_computed_route():
    dataset = load_batch_dataset(ROOT)
    original = _request(dataset)
    changed_task = replace(original.tasks[5], site_id=original.tasks[6].site_id)
    changed = BatchRequest.create(dataset.dataset_id, [*original.tasks[:5], changed_task, *original.tasks[6:]])
    left = run_batch(original, dataset, confirmed_fingerprint=original.fingerprint)
    right = run_batch(changed, dataset, confirmed_fingerprint=changed.fingerprint)
    left_route = next(item for item in left["tasks"] if item["task"]["task_id"] == changed_task.task_id)["candidate_route"]["edge_ids"]
    right_route = next(item for item in right["tasks"] if item["task"]["task_id"] == changed_task.task_id)["candidate_route"]["edge_ids"]
    assert left_route != right_route


def test_output_files_reconcile_with_state(tmp_path):
    dataset, _request_value, state = _run()
    written = write_batch_outputs(state, dataset, tmp_path / state["batch_id"])
    assert {path.name for path in written} >= {"run_summary.json", "tasks.csv", "final_routes.geojson", "resource_after.json", "checksums.sha256"}
    summary = json.loads((tmp_path / state["batch_id"] / "run_summary.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader((tmp_path / state["batch_id"] / "tasks.csv").open(encoding="utf-8-sig")))
    assert summary["task_count"] == len(rows) == 30
    assert len(json.loads((tmp_path / state["batch_id"] / "final_routes.geojson").read_text(encoding="utf-8"))["features"]) == summary["terminal_counts"]["completed_direct"] + summary["terminal_counts"]["completed_rerouted"]
