from pathlib import Path

from scripts.audit_batch_dataset import audit_dataset, audit_run


ROOT = Path(__file__).resolve().parents[2]


def test_independent_dataset_audit_passes_exact_contract():
    report = audit_dataset(ROOT / "data" / "competition_batch")
    assert report["status"] == "PASS"
    assert (report["network_nodes"], report["network_edges"]) == (411, 444)
    assert report["legacy_capacity_fields_present"] is False


def test_independent_main_run_audit_proves_conservation_and_failure_rollback():
    report = audit_run(ROOT / "outputs" / "competition_batch" / "BATCH-MAIN-30")
    assert report["status"] == "PASS"
    assert report["negative_resources"] == 0
    assert report["failed_task_resource_side_effects"] == 0
