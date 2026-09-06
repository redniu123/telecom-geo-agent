"""Run one confirmed deterministic batch from a UTF-8 CSV file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from competition.batch.data_loader import load_batch_dataset
from competition.batch.outputs import write_batch_outputs
from competition.batch.planner import run_batch
from competition.batch.task_import import import_tasks_csv


ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="片区通信设施批量接入设计（固定排序、一次有界改路）")
    parser.add_argument("--tasks", type=Path, default=ROOT / "data" / "competition_batch" / "batch_tasks.csv")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--preview", action="store_true", help="只校验并输出确认指纹")
    parser.add_argument("--confirm", help="必须与预览的完整 SHA-256 指纹一致")
    args = parser.parse_args()

    dataset = load_batch_dataset(ROOT)
    request = import_tasks_csv(
        args.tasks,
        dataset_id=dataset.dataset_id,
        known_site_ids=dataset.site_ids,
        known_room_ids=dataset.room_ids,
        known_asset_ids=set(dataset.resources),
    )
    if args.preview:
        print(request.preview_text())
        print(f"FULL_FINGERPRINT={request.fingerprint}")
        return 0
    request.assert_confirmation(args.confirm)
    state = run_batch(request, dataset, confirmed_fingerprint=args.confirm)
    output = args.output or ROOT / "outputs" / "competition_batch" / request.batch_id
    written = write_batch_outputs(state, dataset, output)
    print(json.dumps({
        "batch_id": state["batch_id"],
        "task_count": state["task_count"],
        "terminal_counts": state["terminal_counts"],
        "output": str(output.resolve()),
        "written_files": [path.name for path in written],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
