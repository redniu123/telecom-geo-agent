# 竞赛对比实验原始数据

`manual_baseline_template.csv` 只是一份空白采集模板，不包含人类被试结果。Quimer 应在同一台机器、同一数据、同一任务说明下，分别完成手工 QGIS 流程与插件流程，并保存录屏或操作日志路径到 `evidence_ref`。

字段口径：

- `elapsed_seconds`：从收到已冻结任务参数到得到可核对结果的真实秒数；
- `manual_operations`：手工基线中可观察的鼠标/键盘操作数；
- `system_observed_operations`：插件流程中实际观察到的操作数，不能直接填理论按钮数；
- `evidence_ref`：本地录屏、日志或验收记录的可追溯路径；为空的人工行不会参与计算；
- `status`：`completed`、`failed` 或 `pending`，按真实结果填写。

运行系统侧三场景基准：

```powershell
python scripts/run_competition_benchmark.py --iterations 3
```

计算报告：

```powershell
python scripts/calculate_competition_metrics.py
```

人工证据为空时，报告必须保持 `pending_human_baseline`。这不是未完成的自动化错误，而是防止伪造“效率提升 >=30% / 操作减少 >50%”结论的验收门。
