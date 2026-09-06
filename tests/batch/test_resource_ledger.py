import copy

import pytest

from competition.batch.resource_ledger import LedgerError, ResourceLedger


def _records():
    return {
        key: {
            "asset_id": key,
            "subduct_total": total,
            "subduct_used_baseline": used,
            "subduct_reserved_batch": 0,
            "segment_status": status,
            "capacity_status": "available",
            "geometry_source": "derived_from_public_road_geometry",
            "business_attributes_source": "synthetic_competition",
        }
        for key, total, used, status in (
            ("A", 2, 0, "available"),
            ("B", 1, 1, "available"),
            ("C", 2, 0, "review_required"),
        )
    }


def test_commit_is_atomic_and_conserves_one_subduct_per_unique_segment():
    ledger = ResourceLedger(_records())
    changes = ledger.commit("T001", ["A", "A"])
    assert len(changes) == 1
    assert ledger.snapshot()["A"]["free_subduct_count"] == 1
    ledger.assert_conservation()


def test_failed_commit_has_zero_side_effect():
    ledger = ResourceLedger(_records())
    before = ledger.snapshot()
    with pytest.raises(LedgerError, match="不可用"):
        ledger.commit("T001", ["A", "B"])
    assert ledger.snapshot() == before
    assert ledger.reservations == []


def test_capacity_conflict_records_causing_prior_task():
    ledger = ResourceLedger(_records())
    ledger.commit("T001", ["A"])
    ledger.commit("T002", ["A"])
    validation = ledger.validate_route(["A"])
    assert validation["passed"] is False
    assert validation["violations"][0]["rule_id"] == "R_SUBDUCT_CAPACITY"
    assert validation["violations"][0]["caused_by_task_ids"] == ["T001", "T002"]


def test_review_required_is_not_automatically_repairable():
    violation = ResourceLedger(_records()).validate_route(["C"])["violations"][0]
    assert violation["rule_id"] == "R_REVIEW_REQUIRED"
    assert violation["repair_hint"] is None
