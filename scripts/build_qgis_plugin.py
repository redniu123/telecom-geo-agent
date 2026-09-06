"""Build an auditable, locally installable QGIS plugin ZIP."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import shutil
import tempfile
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SOURCE = REPO_ROOT / "qgis_plugin" / "telecom_geo_agent"
PLUGIN_VERSION = "0.4.0"
FIXED_ZIP_TIMESTAMP = (2026, 9, 4, 0, 0, 0)


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "p0_runtime"),
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_networkx(runtime_root: Path) -> str:
    distribution = importlib.metadata.distribution("networkx")
    version = distribution.version
    package_source = Path(distribution.locate_file("networkx")).resolve()
    dist_info_candidates = sorted(package_source.parent.glob("networkx-*.dist-info"))
    if not package_source.is_dir() or not dist_info_candidates:
        raise RuntimeError("当前 Python 环境中的 NetworkX 安装不完整")
    dist_info = next(
        (
            path
            for path in dist_info_candidates
            if path.name.startswith(f"networkx-{version}.dist-info")
        ),
        dist_info_candidates[0],
    )
    license_path = dist_info / "licenses" / "LICENSE.txt"
    if not license_path.is_file():
        raise RuntimeError(f"NetworkX 安装缺少许可证文件：{license_path}")
    _copy_tree(package_source, runtime_root / "networkx")
    _copy_tree(dist_info, runtime_root / dist_info.name)
    return version


def _write_deterministic_zip(source_root: Path, output_path: Path) -> None:
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(source_root.rglob("*")):
            if not path.is_file():
                continue
            archive_name = path.relative_to(source_root).as_posix()
            info = zipfile.ZipInfo(archive_name, FIXED_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            bundle.writestr(info, path.read_bytes())


def build_bundle(
    output_directory: str | Path,
    *,
    include_networkx: bool = True,
    repository_root: str | Path = REPO_ROOT,
) -> Path:
    """Package plugin UI plus byte-identical canonical P0 source and data."""

    repo_root = Path(repository_root).resolve()
    output_dir = Path(output_directory).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"telecom_geo_agent-{PLUGIN_VERSION}.zip"

    with tempfile.TemporaryDirectory(prefix="telecom-geo-agent-qgis-") as temporary:
        staging_root = Path(temporary)
        plugin_root = staging_root / "telecom_geo_agent"
        _copy_tree(repo_root / "qgis_plugin" / "telecom_geo_agent", plugin_root)
        runtime_root = plugin_root / "p0_runtime"
        _copy_tree(repo_root / "agent", runtime_root / "agent")
        _copy_tree(repo_root / "telecom_core", runtime_root / "telecom_core")
        _copy_tree(repo_root / "data" / "demo", runtime_root / "data" / "demo")
        _copy_tree(repo_root / "competition", runtime_root / "competition")
        _copy_tree(
            repo_root / "data" / "competition",
            runtime_root / "data" / "competition",
        )
        _copy_tree(
            repo_root / "data" / "competition_batch",
            runtime_root / "data" / "competition_batch",
        )

        canonical_files = [
            path
            for source in (repo_root / "agent", repo_root / "telecom_core")
            for path in source.rglob("*.py")
        ]
        canonical_files.extend((repo_root / "data" / "demo").glob("*.geojson"))
        canonical_files.extend((repo_root / "competition").rglob("*.py"))
        canonical_files.extend(
            path
            for path in (repo_root / "data" / "competition").rglob("*")
            if path.is_file()
        )
        canonical_files.extend(
            path
            for path in (repo_root / "data" / "competition_batch").rglob("*")
            if path.is_file()
        )
        manifest = {
            "schema_version": 1,
            "plugin_version": PLUGIN_VERSION,
            "p0_packaging": "byte-identical canonical source snapshot; no parallel algorithm",
            "competition_packaging": (
                "audited public background plus derived geometry and synthetic telecom attributes"
            ),
            "canonical_sha256": {
                path.relative_to(repo_root).as_posix(): _sha256(path)
                for path in sorted(canonical_files)
            },
            "networkx_version": None,
        }
        if include_networkx:
            manifest["networkx_version"] = _copy_networkx(runtime_root)
        (plugin_root / "BUNDLE_MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _write_deterministic_zip(staging_root, output_path)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="构建本地可安装的 QGIS 插件 ZIP")
    parser.add_argument(
        "--output-dir",
        default="dist",
        help="ZIP 输出目录（默认：dist）",
    )
    parser.add_argument(
        "--without-networkx",
        action="store_true",
        help="不打包 NetworkX；仅用于已有 NetworkX 的 QGIS Python 环境",
    )
    args = parser.parse_args()
    bundle = build_bundle(
        args.output_dir,
        include_networkx=not args.without_networkx,
    )
    print(bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
