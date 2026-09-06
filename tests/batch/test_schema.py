from dataclasses import replace
from pathlib import Path

import pytest

from competition.batch.data_loader import load_batch_dataset
from competition.batch.schema import BatchRequest, BatchTask, BatchValidationError
from competition.batch.task_import import import_tasks_csv


ROOT = Path(__file__).resolve().parents[2]


def _dataset():
    return load_batch_dataset(ROOT)


def _request(path="batch_tasks.csv"):
    dataset = _dataset()
    return import_tasks_csv(
        dataset.root / path,
        dataset_id=dataset.dataset_id,
        known_site_ids=dataset.site_ids,
        known_room_ids=dataset.room_ids,
        known_asset_ids=set(dataset.resources),
    )


def test_main_csv_contract_and_fixed_priority_order():
    request = _request()
    assert len(request.tasks) == 30
    assert [item.task_id for item in request.ordered_tasks] == [f"T{i:03d}" for i in range(1, 31)]
    assert [item.priority for item in request.ordered_tasks[:10]] == ["high"] * 10
    assert [item.priority for item in request.ordered_tasks[10:20]] == ["medium"] * 10
    assert [item.priority for item in request.ordered_tasks[20:]] == ["low"] * 10
    assert len(request.fingerprint) == 64


def test_request_rejects_duplicate_task_id():
    request = _request()
    duplicate = replace(request.tasks[1], task_id=request.tasks[0].task_id)
    with pytest.raises(BatchValidationError, match="task_id 重复"):
        BatchRequest.create(request.dataset_id, [request.tasks[0], duplicate])


def test_task_rejects_fiber_and_subduct_semantic_confusion():
    dataset = _dataset()
    raw = _request().tasks[0].as_dict()
    raw["cable_fiber_cores"] = "1.5"
    raw["subduct_total"] = 99
    with pytest.raises(BatchValidationError, match="cable_fiber_cores"):
        BatchTask.from_mapping(raw, known_site_ids=dataset.site_ids, known_room_ids=dataset.room_ids, known_asset_ids=set(dataset.resources))


def test_confirmation_fails_closed_after_parameter_change():
    request = _request()
    changed = BatchRequest.create(request.dataset_id, [replace(request.tasks[0], cable_fiber_cores=48), *request.tasks[1:]])
    with pytest.raises(BatchValidationError, match="尚未确认"):
        changed.assert_confirmation(request.fingerprint)
