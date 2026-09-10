from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

from scripts.build_qgis_plugin import build_bundle
from scripts.build_team_trial_package import (
    PACKAGE_ROOT_NAME,
    build_team_trial_package,
)


def test_team_trial_package_is_complete_auditable_and_deterministic(tmp_path):
    root = Path(__file__).resolve().parents[2]
    plugin = build_bundle(
        tmp_path / "plugin",
        include_networkx=False,
        repository_root=root,
    )
    package_a, checksum_a = build_team_trial_package(
        tmp_path / "first",
        repository_root=root,
        plugin_bundle=plugin,
    )
    package_b, _ = build_team_trial_package(
        tmp_path / "second",
        repository_root=root,
        plugin_bundle=plugin,
    )

    assert package_a.read_bytes() == package_b.read_bytes()
    expected_hash = hashlib.sha256(package_a.read_bytes()).hexdigest()
    assert checksum_a.read_text(encoding="ascii") == (
        f"{expected_hash.upper()}  {package_a.name}\n"
    )

    prefix = f"{PACKAGE_ROOT_NAME}/"
    with zipfile.ZipFile(package_a) as archive:
        names = set(archive.namelist())
        assert prefix + "00_先看_队员人工试用说明.md" in names
        assert prefix + f"01_安装插件/{plugin.name}" in names
        assert prefix + "02_数据审计/manifest.json" in names
        assert prefix + "02_数据审计/checksums.sha256" in names
        assert prefix + "02_数据审计/expected_coverage.json" in names
        assert prefix + "03_试用记录/team_trial_feedback.csv" in names
        assert prefix + "04_参考界面/batch_ui_review_t002.png" in names
        feedback_rows = list(
            csv.reader(
                io.StringIO(
                    archive.read(prefix + "03_试用记录/team_trial_feedback.csv").decode(
                        "utf-8"
                    )
                )
            )
        )
        assert len(feedback_rows) == 2
        assert len(feedback_rows[0]) == len(feedback_rows[1])
        manifest = json.loads(
            archive.read(prefix + "TEAM_TRIAL_MANIFEST.json").decode("utf-8")
        )
        assert manifest["plugin_version"] == "0.5.0"
        assert manifest["embedded_data"] == {
            "dataset_id": "osm_shanghai_public_background_synthetic_batch_v1",
            "main_tasks": 30,
            "migration_tasks": 10,
            "stress_tasks": 100,
            "public_background": "OpenStreetMap; ODbL 1.0",
            "telecom_facilities_resources_tasks": "synthetic_competition",
        }
        for relative, metadata in manifest["files"].items():
            content = archive.read(prefix + relative)
            assert len(content) == metadata["bytes"]
            assert hashlib.sha256(content).hexdigest() == metadata["sha256"]

        inner_bundle = archive.read(prefix + f"01_安装插件/{plugin.name}")
        with zipfile.ZipFile(io.BytesIO(inner_bundle)) as inner:
            inner_names = set(inner.namelist())
            inner_manifest = inner.read("telecom_geo_agent/BUNDLE_MANIFEST.json")
            assert manifest["plugin_bundle_manifest_sha256"] == hashlib.sha256(
                inner_manifest
            ).hexdigest()
            assert (
                "telecom_geo_agent/p0_runtime/data/competition_batch/batch_tasks.csv"
                in inner_names
            )
            assert (
                "telecom_geo_agent/p0_runtime/data/competition_batch/stress_tasks_100.csv"
                in inner_names
            )
