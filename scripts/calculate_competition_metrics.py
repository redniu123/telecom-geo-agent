"""Calculate competition metrics without inventing a human baseline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from competition.metrics import calculate_metrics, read_csv, write_report


def main() -> int:
    parser = argparse.ArgumentParser(description="计算竞赛效率/操作指标")
    parser.add_argument(
        "--manual-csv",
        type=Path,
        default=REPO_ROOT / "competition" / "benchmark" / "manual_baseline_template.csv",
    )
    parser.add_argument(
        "--system-csv",
        type=Path,
        default=REPO_ROOT / "outputs" / "competition" / "benchmark" / "system_runs.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "competition" / "benchmark" / "metric_report.json",
    )
    args = parser.parse_args()
    report = calculate_metrics(read_csv(args.manual_csv), read_csv(args.system_csv))
    target = write_report(report, args.output)
    print(target.resolve())
    print(report["overall_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
