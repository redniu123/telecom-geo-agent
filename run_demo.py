"""Command-line entry point for the deterministic TelecomGeoAgent P0 demo."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from agent.outputs import write_outputs
from agent.state import AgentState
from agent.workflow import run_workflow


DEFAULT_REQUEST = "从 A 机房到 B 基站规划一条 24 芯光缆，优先使用已有管道。"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行离线 TelecomGeoAgent P0 Demo")
    parser.add_argument(
        "user_text",
        nargs="?",
        default=DEFAULT_REQUEST,
        help="支持的中文光缆规划请求；省略时运行固定 A 到 B、24 芯 Case",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="输出目录（默认：outputs）",
    )
    return parser


def _edge_text(route: dict[str, object]) -> str:
    return " -> ".join(str(edge_id) for edge_id in route["edge_ids"])


def _first_failure_text(state: AgentState) -> str:
    if not state["validation_history"]:
        return "未执行"
    first = state["validation_history"][0]
    if first["passed"]:
        return "PASS"
    return "FAIL " + " ".join(
        f"{violation['rule_id']} {violation['asset_id'] or '-'}"
        for violation in first["violations"]
    )


def _print_success(state: AgentState, output_dir: str) -> None:
    first_route = state["first_route"]
    final_route = state["final_route"]
    bom = state["bom_result"]
    assert first_route is not None and final_route is not None and bom is not None

    print(f"第一次路线：{_edge_text(first_route)}")
    print(f"第一次校核：{_first_failure_text(state)}")
    if state["repair_count"]:
        print(f"自动修复：forbid {', '.join(state['forbidden_asset_ids'])}")
        print(f"第二次路线：{_edge_text(final_route)}")
        print("第二次校核：PASS")
    else:
        print("自动修复：无需修复")
        print(f"最终路线：{_edge_text(final_route)}")
        print("最终校核：PASS")
    print(
        "BOM："
        f"总长 {bom['total_length_m']:.2f} m，"
        f"已有管道 {bom['existing_duct_length_m']:.2f} m，"
        f"新建 {bom['new_build_length_m']:.2f} m，"
        f"建议光缆 {bom['recommended_cable_length_m']:.2f} m"
    )
    print(f"输出目录：{Path(output_dir).as_posix()}/")


def main(
    argv: Sequence[str] | None = None,
    *,
    workflow_runner: Callable[[str], AgentState] = run_workflow,
) -> int:
    args = _build_parser().parse_args(argv)
    state = workflow_runner(args.user_text)
    write_outputs(state, args.output_dir)
    if state["status"] != "completed":
        print(f"执行失败：{state['error'] or '未知错误'}", file=sys.stderr)
        return 1
    _print_success(state, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
