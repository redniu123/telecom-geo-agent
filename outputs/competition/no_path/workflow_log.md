# no_path 工作流证据

数据边界：公开 OSM 背景 + 派生候选几何 + 合成通信属性。
成果声明：竞赛样例 / 非正式施工图。

1. [0.002 ms] 结构化参数指纹已确认
2. [5.223 ms] 竞赛数据集已加载
3. [6.064 ms] 已生成约束前候选路线（不代表可施工）
4. [6.099 ms] 约束前候选路线校核完成
5. [6.106 ms] 一次有界修复：禁用问题/显式禁用资产并重规划
6. [6.511 ms] 工作流明确失败；未伪造最终 PASS 或 BOM

最终状态：failed
失败原因：RoutePlanningError: no route from site 'A' (N-A) to site 'B' (N-B); forbidden_asset_ids=['C1-017', 'C2-024']
