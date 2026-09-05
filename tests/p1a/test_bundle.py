from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

from scripts.build_qgis_plugin import build_bundle


def test_bundle_contains_exact_canonical_p0_snapshot(tmp_path):
    root = Path(__file__).resolve().parents[2]
    bundle = build_bundle(tmp_path, include_networkx=False, repository_root=root)

    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        assert "telecom_geo_agent/metadata.txt" in names
        assert "telecom_geo_agent/p0_runtime/agent/workflow.py" in names
        assert "telecom_geo_agent/p0_runtime/telecom_core/routing.py" in names
        assert "telecom_geo_agent/p0_runtime/data/demo/network.geojson" in names
        assert "telecom_geo_agent/p0_runtime/competition/workflow.py" in names
        assert "telecom_geo_agent/p0_runtime/data/competition/source_manifest.json" in names
        assert "telecom_geo_agent/p0_runtime/data/competition/background/roads.geojson" in names
        assert "telecom_geo_agent/p0_runtime/data/competition/candidate_channels.geojson" in names
        manifest = json.loads(
            archive.read("telecom_geo_agent/BUNDLE_MANIFEST.json").decode("utf-8")
        )
        canonical = root / "agent" / "workflow.py"
        assert archive.read("telecom_geo_agent/p0_runtime/agent/workflow.py") == (
            canonical.read_bytes()
        )
        assert manifest["canonical_sha256"]["agent/workflow.py"] == hashlib.sha256(
            canonical.read_bytes()
        ).hexdigest()
        assert manifest["networkx_version"] is None
        assert manifest["plugin_version"] == "0.3.0"
        competition_manifest = root / "data" / "competition" / "source_manifest.json"
        assert manifest["canonical_sha256"][
            "data/competition/source_manifest.json"
        ] == hashlib.sha256(competition_manifest.read_bytes()).hexdigest()


def test_full_bundle_runs_real_workflow_from_extracted_runtime(tmp_path):
    root = Path(__file__).resolve().parents[2]
    bundle = build_bundle(tmp_path / "dist", repository_root=root)
    extracted = tmp_path / "installed"
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(extracted)

    plugin_root = extracted / "telecom_geo_agent"
    probe = (
        "import pathlib,sys; "
        f"plugin=pathlib.Path({str(plugin_root)!r}); "
        "sys.path.insert(0,str(plugin.parent)); "
        "from telecom_geo_agent.runtime import activate_runtime; "
        "root=activate_runtime(plugin); "
        "import agent,networkx; "
        "state=agent.run_workflow('从A到B规划24芯光缆'); "
        "assert pathlib.Path(networkx.__file__).resolve().is_relative_to(root); "
        "assert state['status']=='completed'; "
        "assert state['first_route']['edge_ids']==['D001','D017','D003']; "
        "assert state['final_route']['edge_ids']==['N001','N002']; "
        "assert state['bom_result']['recommended_cable_length_m']==440.0; "
        "print(networkx.__version__)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=extracted,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        assert any(name.endswith(".dist-info/licenses/LICENSE.txt") for name in names)
        manifest = json.loads(
            archive.read("telecom_geo_agent/BUNDLE_MANIFEST.json").decode("utf-8")
        )
        assert manifest["networkx_version"] == result.stdout.strip()
