"""Independently reread, render and inspect every page of the QGIS Atlas PDF."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageOps, ImageStat


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run(command: list[str]) -> str:
    completed = subprocess.run(command, check=True, capture_output=True)
    return completed.stdout.decode("utf-8", errors="replace")


def verify(pdf: Path, output_dir: Path) -> dict:
    pdf = pdf.resolve()
    output_dir = output_dir.resolve()
    if not pdf.is_file() or pdf.stat().st_size < 100_000:
        raise AssertionError("Atlas PDF missing or implausibly small")
    info = _run(["pdfinfo", str(pdf)])
    parsed = {}
    for line in info.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            parsed[key.strip()] = value.strip()
    if parsed.get("Pages") != "36" or "A3" not in parsed.get("Page size", ""):
        raise AssertionError(f"expected 36 A3 pages, got {parsed.get('Pages')} / {parsed.get('Page size')}")
    text = _run(["pdftotext", "-layout", str(pdf), "-"])
    required = [
        "片区通信设施批量接入设计图册",
        "411 节点 / 444 边 / 3 机房 / 30 任务",
        "直接成功：19",
        "绕行成功：9",
        "待人工复核：1",
        "明确失败：1",
        "© OpenStreetMap contributors / ODbL 1.0",
        "合成通信属性、竞赛样例、非正式施工图",
        "数据来源、许可与成果边界",
    ]
    missing = [value for value in required if value not in text]
    if missing:
        raise AssertionError(f"Atlas required text missing: {missing}")
    missing_tasks = [f"T{index:03d}" for index in range(1, 31) if f"任务设计页 · T{index:03d}" not in text]
    if missing_tasks:
        raise AssertionError(f"Atlas task pages missing: {missing_tasks}")

    geopackage = output_dir / "batch_results.gpkg"
    expected_layer_counts = {
        "batch_rooms": 3,
        "batch_sites": 30,
        "batch_tasks": 30,
        "batch_candidates": 30,
        "batch_final": 28,
        "batch_issues": 13,
        "batch_resource": 444,
    }
    if not geopackage.is_file() or geopackage.stat().st_size < 100_000:
        raise AssertionError("batch result GeoPackage missing or implausibly small")
    with sqlite3.connect(geopackage) as connection:
        feature_layers = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM gpkg_contents WHERE data_type = 'features'"
            )
        }
        if feature_layers != set(expected_layer_counts):
            raise AssertionError(
                f"GeoPackage feature layer mismatch: {sorted(feature_layers)}"
            )
        actual_layer_counts = {
            layer: connection.execute(f'SELECT COUNT(*) FROM "{layer}"').fetchone()[0]
            for layer in sorted(expected_layer_counts)
        }
    if actual_layer_counts != expected_layer_counts:
        raise AssertionError(
            f"GeoPackage feature counts mismatch: {actual_layer_counts}"
        )

    rendered = []
    contact_paths = []
    with tempfile.TemporaryDirectory(prefix="telecom-atlas-render-") as temp_name:
        prefix = Path(temp_name) / "page"
        subprocess.run(["pdftoppm", "-jpeg", "-r", "72", str(pdf), str(prefix)], check=True, capture_output=True)
        page_paths = sorted(Path(temp_name).glob("page-*.jpg"))
        if len(page_paths) != 36:
            raise AssertionError(f"rendered page count mismatch: {len(page_paths)}")
        thumbs = []
        for index, path in enumerate(page_paths, start=1):
            with Image.open(path) as image:
                rgb = image.convert("RGB")
                if rgb.width < 1100 or rgb.height < 780:
                    raise AssertionError(f"page {index} rendered below expected A3 size: {rgb.size}")
                stat = ImageStat.Stat(rgb)
                extrema = rgb.getextrema()
                dynamic_channels = sum(high - low for low, high in extrema)
                if dynamic_channels < 60 or min(stat.mean) > 253.5:
                    raise AssertionError(f"page {index} appears blank or visually degenerate")
                rendered.append({"page": index, "width_px": rgb.width, "height_px": rgb.height, "channel_extrema": extrema, "mean_rgb": [round(value, 2) for value in stat.mean]})
                thumb = ImageOps.contain(rgb, (390, 276))
                canvas = Image.new("RGB", (400, 296), "white")
                canvas.paste(thumb, ((400 - thumb.width) // 2, 4))
                thumbs.append(canvas)
        for sheet_index in range(6):
            sheet = Image.new("RGB", (1200, 592), "#d8dde3")
            for slot, thumb in enumerate(thumbs[sheet_index * 6 : sheet_index * 6 + 6]):
                sheet.paste(thumb, ((slot % 3) * 400, (slot // 3) * 296))
            target = output_dir / f"atlas_contact_sheet_{sheet_index + 1:02d}.jpg"
            sheet.save(target, quality=88, optimize=True)
            contact_paths.append(target.name)
    report = {
        "status": "PASS",
        "pdf": pdf.name,
        "pdf_bytes": pdf.stat().st_size,
        "pages": 36,
        "paper": parsed["Page size"],
        "text_reread": "PASS",
        "all_task_page_titles_present": True,
        "osm_attribution_present": True,
        "synthetic_non_construction_disclaimer_present": True,
        "all_pages_rendered": True,
        "geopackage_reread": "PASS",
        "geopackage_bytes": geopackage.stat().st_size,
        "geopackage_layer_counts": actual_layer_counts,
        "rendered_page_checks": rendered,
        "contact_sheets": contact_paths,
        "visual_review_note": "Contact sheets require an actual human-visible inspection; automated checks only prove renderability, size, text and nonblank pixels.",
    }
    (output_dir / "atlas_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    from competition.batch.outputs import refresh_checksums

    refresh_checksums(output_dir)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="重读并逐页渲染检查 QGIS Atlas PDF")
    parser.add_argument("--pdf", type=Path, default=ROOT / "outputs" / "competition_batch" / "BATCH-MAIN-30" / "design_book.pdf")
    args = parser.parse_args()
    report = verify(args.pdf, args.pdf.resolve().parent)
    print(json.dumps({key: report[key] for key in ("status", "pdf_bytes", "pages", "paper", "text_reread", "all_pages_rendered", "geopackage_reread", "geopackage_layer_counts", "contact_sheets")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
