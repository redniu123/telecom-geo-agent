"""Execute real offline system runs and preserve raw timing rows."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from competition.catalog import load_catalog
from run_competition import run_scenario


def main() -> int:
    parser = argparse.ArgumentParser(description="运行竞赛三场景系统侧基准")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "competition" / "benchmark" / "system_runs.csv",
    )
    args = parser.parse_args()
    if not 1 <= args.iterations <= 30:
        parser.error("--iterations must be within 1..30")
    catalog = load_catalog(REPO_ROOT)
    rows = []
    matched = True
    for scenario_id, scenario in catalog["scenarios"].items():
        for iteration in range(1, args.iterations + 1):
            state = run_scenario(scenario_id)
            matched = matched and state["status"] == scenario["expected_status"]
            rows.append(
                {
                    "run_id": f"SYS-{scenario_id}-{iteration:02d}",
                    "scenario_id": scenario_id,
                    "iteration": iteration,
                    "status": state["status"],
                    "expected_status": scenario["expected_status"],
                    "elapsed_seconds": f"{state['system_elapsed_ms'] / 1000:.6f}",
                    "event_count": len(state["events"]),
                    "parameter_fingerprint": state["parameter_fingerprint"],
                    "evidence_ref": str(
                        Path("outputs") / "competition" / scenario_id / "events.jsonl"
                    ).replace("\\", "/"),
                }
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    metadata = {
        "iterations_per_scenario": args.iterations,
        "raw_csv": str(args.output.resolve()),
        "all_actual_statuses_match_catalog": matched,
        "claim_boundary": "system execution timing only; not human efficiency evidence",
    }
    metadata_path = args.output.with_suffix(".metadata.json")
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(args.output.resolve())
    print(metadata_path.resolve())
    return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
