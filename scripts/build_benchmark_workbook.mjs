import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const threadId = "01a0705f-e12b-7930-9bed-6a3f9d4fb2bf";
const outputDir = path.join(repositoryRoot, "outputs", threadId);
const previewDir = path.join(repositoryRoot, "tmp", "artifact_xlsx", "rendered");
const systemCsv = path.join(repositoryRoot, "outputs", "competition", "benchmark", "system_runs.csv");
const outputPath = path.join(outputDir, "通信线路智能设计_对比实验模板.xlsx");
await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const csvLines = (await fs.readFile(systemCsv, "utf8"))
  .replace(/^\uFEFF/, "")
  .trim()
  .split(/\r?\n/)
  .map((line) => line.split(","));
const systemHeaders = csvLines[0];
const systemRows = csvLines.slice(1).map((row) =>
  row.map((value, index) =>
    ["iteration", "elapsed_seconds", "event_count"].includes(systemHeaders[index])
      ? Number(value)
      : value,
  ),
);

const workbook = Workbook.create();
const guide = workbook.worksheets.add("Guide");
const manual = workbook.worksheets.add("ManualRaw");
const system = workbook.worksheets.add("SystemRuns");
const metrics = workbook.worksheets.add("Metrics");
for (const sheet of [guide, manual, system, metrics]) {
  sheet.showGridLines = false;
}
console.log("CHECKPOINT sheets-created");

guide.getRange("A1").values = [["通信线路智能设计竞赛 · 对比实验采集与计算模板"]];
console.log("CHECKPOINT guide-title");
guide.getRange("A1:H2").format = {
  fill: "#12324A",
  font: { name: "Microsoft YaHei", size: 18, bold: true, color: "#FFFFFF" },
  verticalAlignment: "center",
};
console.log("CHECKPOINT guide-title-format");
guide.getRange("A4:B12").values = [
  ["当前状态", "待人工基线"],
  ["赛题门槛", "效率提升 >=30%，或手工绘图操作减少 >50%"],
  ["系统数据", "由脚本真实运行三场景，每场景 3 次"],
  ["人工数据", "空白；由 Quimer 在同机、同任务说明下实测填写"],
  ["证据要求", "人工行必须填写录屏/日志路径 evidence_ref 才可采信"],
  ["时间口径", "从收到冻结参数到得到可核对结果的秒数"],
  ["操作口径", "可观察的鼠标和键盘操作，不填理论按钮数"],
  ["数据边界", "公开 OSM 背景 + 派生候选几何 + 合成通信属性"],
  ["成果声明", "竞赛样例 / 非正式施工图"],
];
console.log("CHECKPOINT guide-values");
guide.getRange("A4:A12").format = {
  fill: "#DCEAF3",
  font: { bold: true, color: "#12324A" },
  borders: { preset: "all", style: "thin", color: "#B8C8D3" },
};
console.log("CHECKPOINT guide-label-format");
guide.getRange("B4:B12").format = {
  wrapText: true,
  borders: { preset: "all", style: "thin", color: "#B8C8D3" },
};
console.log("CHECKPOINT guide-body-format");
guide.getRange("B4").format = { fill: "#FFF2CC", font: { bold: true, color: "#9C6500" } };
console.log("CHECKPOINT guide-status-format");
guide.getRange("A14:I17").values = [
  ["执行顺序", "1", "运行系统基准", "2", "填写人工原始数据", "3", "复核证据", "4", "读取指标计算"],
  ["命令", "", "python scripts/run_competition_benchmark.py --iterations 3", "", "", "", "python scripts/calculate_competition_metrics.py", "", ""],
  ["注意", "", "系统毫秒数不是人工效率提升证据", "", "留空优于估算", "", "门槛列为空时不得作达标宣传", "", ""],
  ["来源", "", "outputs/competition/benchmark/system_runs.csv", "", "competition/benchmark/manual_baseline_template.csv", "", "outputs/competition/benchmark/metric_report.json", "", ""],
];
console.log("CHECKPOINT guide-steps-values");
guide.getRange("A14:I17").format = { wrapText: true, borders: { preset: "all", style: "thin", color: "#D6DEE5" } };
console.log("CHECKPOINT guide-steps-format");
guide.getRange("A14:I14").format = { fill: "#1E637A", font: { bold: true, color: "#FFFFFF" } };
console.log("CHECKPOINT guide-steps-header");
guide.getRange("A1:I20").format.rowHeight = 28;
guide.getRange("B1:B20").format.columnWidth = 48;
guide.getRange("C1:C20").format.columnWidth = 35;
guide.getRange("E1:E20").format.columnWidth = 28;
guide.getRange("G1:G20").format.columnWidth = 38;
guide.freezePanes.freezeRows(3);
guide.getRange("A1:I17").format.font = { name: "Microsoft YaHei", size: 10 };
console.log("CHECKPOINT guide-complete");

const manualHeaders = [
  "run_id", "scenario_id", "operator_id", "environment", "started_at", "ended_at",
  "elapsed_seconds", "manual_operations", "system_observed_operations", "status", "evidence_ref", "notes",
];
manual.getRange("A1:L4").values = [
  manualHeaders,
  ["MAN-capacity-01", "capacity_reroute", "", "", null, null, null, null, null, "pending", "", "由 Quimer 实测填写；不可估算"],
  ["MAN-forbidden-01", "forbidden_reroute", "", "", null, null, null, null, null, "pending", "", "由 Quimer 实测填写；不可估算"],
  ["MAN-no-path-01", "no_path", "", "", null, null, null, null, null, "pending", "", "失败识别也需计时"],
];
manual.getRange("G2").formulas = [["=IF(OR(E2=\"\",F2=\"\"),\"\",(F2-E2)*86400)"]];
manual.getRange("G2:G4").fillDown();
manual.getRange("A1:L1").format = { fill: "#12324A", font: { bold: true, color: "#FFFFFF" }, wrapText: true };
manual.getRange("A2:L4").format.borders = { preset: "all", style: "thin", color: "#D6DEE5" };
manual.getRange("E2:F4").format.numberFormat = "yyyy-mm-dd hh:mm:ss";
manual.getRange("G2:I4").format.numberFormat = "0.000";
manual.getRange("J2:J4").dataValidation = { rule: { type: "list", values: ["pending", "completed", "failed"] } };
manual.getRange("B2:B4").dataValidation = { rule: { type: "list", values: ["capacity_reroute", "forbidden_reroute", "no_path"] } };
manual.getRange("A1:L4").format.columnWidth = 18;
manual.getRange("K1:L4").format.columnWidth = 32;
manual.freezePanes.freezeRows(1);
manual.getRange("A1:L4").format.font = { name: "Microsoft YaHei", size: 10 };
console.log("CHECKPOINT manual-complete");

system.getRangeByIndexes(0, 0, systemRows.length + 1, systemHeaders.length).values = [systemHeaders, ...systemRows];
system.getRange(`A1:I1`).format = { fill: "#12324A", font: { bold: true, color: "#FFFFFF" }, wrapText: true };
system.getRange(`A2:I${systemRows.length + 1}`).format.borders = { preset: "all", style: "thin", color: "#D6DEE5" };
system.getRange(`F2:F${systemRows.length + 1}`).format.numberFormat = "0.000000";
system.getRange(`A1:I${systemRows.length + 1}`).format.columnWidth = 20;
system.getRange(`H1:I${systemRows.length + 1}`).format.columnWidth = 38;
system.freezePanes.freezeRows(1);
system.getRange(`A1:I${systemRows.length + 1}`).format.font = { name: "Microsoft YaHei", size: 10 };
console.log("CHECKPOINT system-complete");

metrics.getRange("A1:H1").values = [["场景", "人工中位秒数", "系统中位秒数", "效率提升", "人工操作数", "插件观察操作数", "操作减少", "门槛判定"]];
metrics.getRange("A2:A4").values = [["capacity_reroute"], ["forbidden_reroute"], ["no_path"]];
metrics.getRange("B2").formulas = [["=IF(ManualRaw!K2=\"\",\"\",ManualRaw!G2)"]];
metrics.getRange("B2:B4").fillDown();
metrics.getRange("C2:C4").formulas = [
  ["=MEDIAN(SystemRuns!F2:F4)"],
  ["=MEDIAN(SystemRuns!F5:F7)"],
  ["=MEDIAN(SystemRuns!F8:F10)"],
];
metrics.getRange("D2").formulas = [["=IF(B2=\"\",\"\",(B2-C2)/B2)"]];
metrics.getRange("D2:D4").fillDown();
metrics.getRange("E2").formulas = [["=IF(ManualRaw!K2=\"\",\"\",ManualRaw!H2)"]];
metrics.getRange("E2:E4").fillDown();
metrics.getRange("F2").formulas = [["=IF(ManualRaw!K2=\"\",\"\",ManualRaw!I2)"]];
metrics.getRange("F2:F4").fillDown();
metrics.getRange("G2").formulas = [["=IF(OR(E2=\"\",F2=\"\"),\"\",(E2-F2)/E2)"]];
metrics.getRange("G2:G4").fillDown();
metrics.getRange("H2").formulas = [["=IF(B2=\"\",\"待人工基线\",IF(OR(D2>=30%,G2>50%),\"达标\",\"未达标\"))"]];
metrics.getRange("H2:H4").fillDown();
metrics.getRange("A1:H1").format = { fill: "#12324A", font: { bold: true, color: "#FFFFFF" }, wrapText: true };
metrics.getRange("A2:H4").format.borders = { preset: "all", style: "thin", color: "#D6DEE5" };
metrics.getRange("B2:C4").format.numberFormat = "0.000000";
metrics.getRange("D2:D4").format.numberFormat = "0.0%";
metrics.getRange("G2:G4").format.numberFormat = "0.0%";
metrics.getRange("H2:H4").conditionalFormats.add("containsText", { text: "待人工基线", format: { fill: "#FFF2CC", font: { color: "#9C6500", bold: true } } });
metrics.getRange("H2:H4").conditionalFormats.add("containsText", { text: "达标", format: { fill: "#D9EAD3", font: { color: "#27632A", bold: true } } });
metrics.getRange("A6:H9").values = [
  ["公式说明", "", "", "", "", "", "", ""],
  ["效率提升", "(人工中位秒数 - 系统中位秒数) / 人工中位秒数", "", "", "", "", "", ""],
  ["操作减少", "(人工操作数 - 插件观察操作数) / 人工操作数", "", "", "", "", "", ""],
  ["判定", "效率提升 >=30% 或操作减少 >50%；人工证据为空时只能待基线", "", "", "", "", "", ""],
];
metrics.getRange("A6:H9").format = { wrapText: true, borders: { preset: "all", style: "thin", color: "#D6DEE5" } };
metrics.getRange("A6:H6").format = { fill: "#1E637A", font: { bold: true, color: "#FFFFFF" } };
metrics.getRange("A1:H9").format.columnWidth = 18;
metrics.getRange("A1:A9").format.columnWidth = 24;
metrics.getRange("B1:C9").format.columnWidth = 18;
metrics.getRange("H1:H9").format.columnWidth = 18;
metrics.freezePanes.freezeRows(1);
metrics.getRange("A1:H9").format.font = { name: "Microsoft YaHei", size: 10 };
console.log("CHECKPOINT metrics-complete");

const inspection = await workbook.inspect({
  kind: "formula,region",
  sheetId: "Metrics",
  range: "A1:H9",
  maxChars: 6000,
  options: { maxResults: 80 },
});
console.log(inspection.ndjson);
console.log("CHECKPOINT inspect-complete");

const exported = await SpreadsheetFile.exportXlsx(workbook);
console.log("CHECKPOINT export-created");
await exported.save(outputPath);
console.log(outputPath);
if (process.env.SKIP_ARTIFACT_RENDER !== "1") {
  for (const sheetName of ["Guide", "ManualRaw", "SystemRuns", "Metrics"]) {
    console.log(`CHECKPOINT render-start ${sheetName}`);
    const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1.2, format: "png" });
    const safeName = sheetName.replace(/[^\p{L}\p{N}]+/gu, "_");
    await fs.writeFile(path.join(previewDir, `${safeName}.png`), new Uint8Array(await preview.arrayBuffer()));
  }
  console.log("CHECKPOINT render-complete");
}
