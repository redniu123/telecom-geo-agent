"""Headless PyQGIS acceptance entry point for the real multi-page Atlas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from qgis.core import Qgis, QgsApplication, QgsProject, QgsSingleSymbolRenderer, QgsVectorLayer


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="使用真实 QGIS Layout/Atlas 导出批量设计图册")
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--project", type=Path)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    if str(root) not in __import__("sys").path:
        __import__("sys").path.insert(0, str(root))

    from competition.batch.data_loader import load_batch_dataset
    from competition.batch.planner import run_batch
    from competition.batch.task_import import import_tasks_csv
    from qgis_plugin.telecom_geo_agent.atlas_exporter import export_batch_atlas
    from qgis_plugin.telecom_geo_agent.batch_layer_plan import build_batch_layer_plan
    from qgis_plugin.telecom_geo_agent.map_adapter import QgisMapAdapter

    dataset = load_batch_dataset(root)
    task_path = (args.tasks or dataset.root / "batch_tasks.csv").resolve()
    request = import_tasks_csv(task_path, dataset_id=dataset.dataset_id, known_site_ids=dataset.site_ids, known_room_ids=dataset.room_ids, known_asset_ids=set(dataset.resources))
    state = run_batch(request, dataset, confirmed_fingerprint=request.fingerprint)
    output_dir = root / "outputs" / "competition_batch" / request.batch_id
    destination = (args.output or output_dir / "design_book.pdf").resolve()
    project_path = (args.project or output_dir / "batch_demo.qgz").resolve()

    app = QgsApplication([], False)
    app.initQgis()
    project = QgsProject.instance()
    layers = {}
    try:
        plan = build_batch_layer_plan(root, request.batch_id)
        plan.validate_sources()
        group = project.layerTreeRoot().addGroup(plan.group_name)
        for spec in plan.layers:
            layer = QgsVectorLayer(str(spec.source_path(root)), spec.name, "ogr")
            if not layer.isValid():
                raise RuntimeError(f"QGIS 无法加载图层：{spec.relative_path}")
            if spec.subset_expression and not layer.setSubsetString(spec.subset_expression):
                raise RuntimeError(f"QGIS 无法应用筛选：{spec.key}")
            layer.setRenderer(QgsSingleSymbolRenderer(QgisMapAdapter._symbol(spec.style)))
            project.addMapLayer(layer, False)
            group.addLayer(layer)
            layers[spec.key] = layer
        export_batch_atlas(project, layers, state, destination)
        project.setFileName(str(project_path))
        if not project.write():
            raise RuntimeError("QGIS 工程文件写入失败")
        from competition.batch.outputs import refresh_checksums

        refresh_checksums(output_dir)
        print(json.dumps({"qgis_version": Qgis.QGIS_VERSION, "batch_id": request.batch_id, "atlas_pdf": str(destination), "atlas_pages": state["task_count"] + 6, "qgis_project": str(project_path), "loaded_layer_count": len(layers)}, ensure_ascii=False, sort_keys=True))
    finally:
        project.clear()
        app.exitQgis()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
