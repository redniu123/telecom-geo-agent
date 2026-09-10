"""Build a deterministic, offline handoff ZIP for teammate QGIS trials."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

try:
    from scripts.build_qgis_plugin import PLUGIN_VERSION, build_bundle
except ModuleNotFoundError:
    from build_qgis_plugin import PLUGIN_VERSION, build_bundle


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_BASENAME = f"telecom_geo_agent-{PLUGIN_VERSION}-team-trial"
PACKAGE_ROOT_NAME = f"TelecomGeoAgent-{PLUGIN_VERSION}-team-trial"
FIXED_ZIP_TIMESTAMP = (2026, 9, 10, 0, 0, 0)


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _copy(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"试用包缺少必需文件：{source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _read_plugin_manifest(bundle: Path) -> tuple[dict, bytes]:
    with zipfile.ZipFile(bundle) as archive:
        manifest_bytes = archive.read("telecom_geo_agent/BUNDLE_MANIFEST.json")
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        names = set(archive.namelist())
    required = {
        "telecom_geo_agent/p0_runtime/data/competition_batch/manifest.json",
        "telecom_geo_agent/p0_runtime/data/competition_batch/checksums.sha256",
        "telecom_geo_agent/p0_runtime/data/competition_batch/batch_tasks.csv",
        "telecom_geo_agent/p0_runtime/data/competition_batch/migration_tasks_10.csv",
        "telecom_geo_agent/p0_runtime/data/competition_batch/stress_tasks_100.csv",
    }
    missing = sorted(required - names)
    if missing:
        raise RuntimeError(f"插件 ZIP 未包含完整内置数据：{missing}")
    if manifest.get("plugin_version") != PLUGIN_VERSION:
        raise RuntimeError(
            f"插件版本不一致：{manifest.get('plugin_version')!r} != {PLUGIN_VERSION!r}"
        )
    return manifest, manifest_bytes


def _write_deterministic_zip(source_root: Path, output_path: Path) -> None:
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_root.rglob("*")):
            if not path.is_file():
                continue
            archive_name = path.relative_to(source_root).as_posix()
            info = zipfile.ZipInfo(archive_name, FIXED_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def build_team_trial_package(
    output_directory: str | Path,
    *,
    repository_root: str | Path = REPO_ROOT,
    plugin_bundle: str | Path | None = None,
) -> tuple[Path, Path]:
    """Create the outer trial ZIP and a sidecar SHA-256 file."""

    repo_root = Path(repository_root).resolve()
    output_dir = Path(output_directory).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    plugin_path = (
        Path(plugin_bundle).resolve()
        if plugin_bundle is not None
        else build_bundle(output_dir, repository_root=repo_root)
    )
    plugin_manifest, plugin_manifest_bytes = _read_plugin_manifest(plugin_path)

    package_path = output_dir / f"{PACKAGE_BASENAME}.zip"
    checksum_path = output_dir / f"{PACKAGE_BASENAME}.sha256"
    with tempfile.TemporaryDirectory(prefix="telecom-geo-agent-team-trial-") as temp:
        staging = Path(temp) / PACKAGE_ROOT_NAME
        _copy(
            repo_root / "docs" / "team_trial" / "队员人工试用说明.md",
            staging / "00_先看_队员人工试用说明.md",
        )
        _copy(plugin_path, staging / "01_安装插件" / plugin_path.name)
        for filename in ("manifest.json", "checksums.sha256", "expected_coverage.json"):
            _copy(
                repo_root / "data" / "competition_batch" / filename,
                staging / "02_数据审计" / filename,
            )
        _copy(
            repo_root / "docs" / "team_trial" / "team_trial_feedback.csv",
            staging / "03_试用记录" / "team_trial_feedback.csv",
        )
        _copy(
            repo_root
            / "outputs"
            / "ui_validation"
            / "batch_ui_review_t002_native100pct.png",
            staging / "04_参考界面" / "batch_ui_review_t002.png",
        )

        payload_files = [path for path in sorted(staging.rglob("*")) if path.is_file()]
        manifest = {
            "schema_version": 1,
            "package_name": PACKAGE_BASENAME,
            "plugin_version": PLUGIN_VERSION,
            "distribution": "offline_team_trial",
            "github_branch": "codex/qgis-batch-ui",
            "tested_environment": {
                "windows": "Windows",
                "python": "3.11.4",
                "qgis": "3.44.14-Solothurn",
            },
            "embedded_data": {
                "dataset_id": "osm_shanghai_public_background_synthetic_batch_v1",
                "main_tasks": 30,
                "migration_tasks": 10,
                "stress_tasks": 100,
                "public_background": "OpenStreetMap; ODbL 1.0",
                "telecom_facilities_resources_tasks": "synthetic_competition",
            },
            "plugin_bundle_manifest_sha256": _sha256_bytes(plugin_manifest_bytes),
            "files": {
                path.relative_to(staging).as_posix(): {
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
                for path in payload_files
            },
            "boundaries": [
                "Public OSM layers are geographic background only.",
                "Candidate channel geometry is derived from public roads.",
                "Telecom identities, capacity, occupancy, status, cost, tasks and BOM are synthetic.",
                "Competition prototype output; not a formal construction drawing.",
            ],
        }
        (staging / "TEAM_TRIAL_MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _write_deterministic_zip(staging.parent, package_path)

    checksum_path.write_text(
        f"{_sha256(package_path).upper()}  {package_path.name}\n",
        encoding="ascii",
    )
    return package_path, checksum_path


def main() -> int:
    parser = argparse.ArgumentParser(description="构建队员可直接使用的离线 QGIS 试用包")
    parser.add_argument("--output-dir", default="dist", help="输出目录（默认：dist）")
    args = parser.parse_args()
    package, checksum = build_team_trial_package(args.output_dir)
    print(package)
    print(checksum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
