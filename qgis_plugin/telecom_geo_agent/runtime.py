"""Locate and activate the one canonical P0 runtime used by the plugin."""

from __future__ import annotations

import os
import sys
from pathlib import Path


RUNTIME_ENVIRONMENT_VARIABLE = "TELECOM_GEO_AGENT_ROOT"


def _is_runtime_root(path: Path) -> bool:
    return all(
        candidate.is_file()
        for candidate in (
            path / "agent" / "workflow.py",
            path / "telecom_core" / "routing.py",
            path / "data" / "demo" / "network.geojson",
            path / "data" / "demo" / "sites.geojson",
            path / "competition" / "workflow.py",
            path / "data" / "competition" / "source_manifest.json",
            path / "data" / "competition" / "network.geojson",
            path / "data" / "competition" / "sites.geojson",
        )
    )


def resolve_runtime_root(plugin_directory: str | Path | None = None) -> Path:
    """Resolve either the bundled P0 snapshot or a source-checkout root."""

    plugin_root = Path(plugin_directory or Path(__file__).resolve().parent).resolve()
    candidates: list[Path] = [plugin_root / "p0_runtime"]
    configured_root = os.environ.get(RUNTIME_ENVIRONMENT_VARIABLE)
    if configured_root:
        candidates.append(Path(configured_root).expanduser())
    candidates.extend(plugin_root.parents)

    checked: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in checked:
            continue
        checked.add(resolved)
        if _is_runtime_root(resolved):
            return resolved
    raise RuntimeError(
        "找不到 TelecomGeoAgent 0.3 运行时。请使用 scripts/build_qgis_plugin.py "
        "生成的 ZIP 安装，或设置 TELECOM_GEO_AGENT_ROOT 指向仓库根目录。"
    )


def _assert_no_foreign_module(module_name: str, runtime_root: Path) -> None:
    module = sys.modules.get(module_name)
    module_file = getattr(module, "__file__", None) if module is not None else None
    if not module_file:
        return
    try:
        Path(module_file).resolve().relative_to(runtime_root)
    except ValueError as exc:
        raise RuntimeError(
            f"Python 已从其他位置加载同名模块 {module_name!r}：{module_file}"
        ) from exc


def activate_runtime(plugin_directory: str | Path | None = None) -> Path:
    """Put the resolved P0 root first on sys.path and reject name collisions."""

    runtime_root = resolve_runtime_root(plugin_directory)
    _assert_no_foreign_module("agent", runtime_root)
    _assert_no_foreign_module("telecom_core", runtime_root)
    runtime_text = str(runtime_root)
    if runtime_text in sys.path:
        sys.path.remove(runtime_text)
    sys.path.insert(0, runtime_text)
    return runtime_root
