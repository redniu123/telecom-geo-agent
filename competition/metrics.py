"""Honest competition benchmark calculations with fail-closed baselines."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any


SCENARIOS = ("capacity_reroute", "forbidden_reroute", "no_path")


def _optional_positive(row: dict[str, str], field: str) -> float | None:
    text = (row.get(field) or "").strip()
    if not text:
        return None
    value = float(text)
    if value <= 0:
        raise ValueError(f"{field} must be positive when provided")
    return value


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def calculate_metrics(
    manual_rows: list[dict[str, str]], system_rows: list[dict[str, str]]
) -> dict[str, Any]:
    manual_by_scenario: dict[str, list[dict[str, str]]] = defaultdict(list)
    system_by_scenario: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in manual_rows:
        if row.get("scenario_id") in SCENARIOS:
            manual_by_scenario[row["scenario_id"]].append(row)
    for row in system_rows:
        if row.get("scenario_id") in SCENARIOS and row.get("status") in {
            "completed",
            "failed",
        }:
            system_by_scenario[row["scenario_id"]].append(row)

    results: list[dict[str, Any]] = []
    for scenario_id in SCENARIOS:
        system_seconds = [
            _optional_positive(row, "elapsed_seconds")
            for row in system_by_scenario[scenario_id]
        ]
        system_seconds = [value for value in system_seconds if value is not None]
        manual_seconds = [
            _optional_positive(row, "elapsed_seconds")
            for row in manual_by_scenario[scenario_id]
            if (row.get("evidence_ref") or "").strip()
        ]
        manual_seconds = [value for value in manual_seconds if value is not None]
        manual_ops = [
            _optional_positive(row, "manual_operations")
            for row in manual_by_scenario[scenario_id]
            if (row.get("evidence_ref") or "").strip()
        ]
        manual_ops = [value for value in manual_ops if value is not None]
        system_observed_ops = [
            _optional_positive(row, "system_observed_operations")
            for row in manual_by_scenario[scenario_id]
            if (row.get("evidence_ref") or "").strip()
        ]
        system_observed_ops = [value for value in system_observed_ops if value is not None]

        result: dict[str, Any] = {
            "scenario_id": scenario_id,
            "status": "pending_human_baseline",
            "system_run_count": len(system_seconds),
            "human_baseline_count": len(manual_seconds),
            "system_median_seconds": round(median(system_seconds), 6)
            if system_seconds
            else None,
            "human_median_seconds": None,
            "efficiency_improvement_percent": None,
            "manual_operation_reduction_percent": None,
            "competition_threshold_met": None,
        }
        if not system_seconds:
            result["status"] = "missing_system_runs"
        elif manual_seconds:
            human_median = median(manual_seconds)
            system_median = median(system_seconds)
            efficiency = (human_median - system_median) / human_median * 100
            result["human_median_seconds"] = round(human_median, 6)
            result["efficiency_improvement_percent"] = round(efficiency, 2)
            operation_reduction = None
            if manual_ops and system_observed_ops:
                operation_reduction = (
                    (median(manual_ops) - median(system_observed_ops))
                    / median(manual_ops)
                    * 100
                )
                result["manual_operation_reduction_percent"] = round(
                    operation_reduction, 2
                )
            result["competition_threshold_met"] = (
                efficiency >= 30.0
                or (operation_reduction is not None and operation_reduction > 50.0)
            )
            result["status"] = "calculated_with_human_evidence"
        results.append(result)

    all_calculated = all(
        result["status"] == "calculated_with_human_evidence" for result in results
    )
    return {
        "schema_version": 1,
        "overall_status": "calculated" if all_calculated else "pending_human_baseline",
        "threshold_rule": "efficiency_improvement_percent >= 30 OR manual_operation_reduction_percent > 50",
        "aggregation": "median per scenario; human rows require a non-empty evidence_ref",
        "scenarios": results,
        "limitations": [
            "System timing is not a human manual-design baseline.",
            "Blank or evidence-free human rows are excluded.",
            "No competition threshold claim is valid while overall_status is pending_human_baseline.",
        ],
    }


def write_report(report: dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target
