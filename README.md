# TelecomGeoAgent MVP

这是一个完全离线、可确定性复算的通信光缆路由 P0 Demo。它把固定中文请求解析为 `TelecomTask`，调用现有 `telecom_core` 完成路线规划、独立校核、一次有界自动修复和简化 BOM 计算，并输出可由 QGIS 打开的 GeoJSON。P1A 在不修改这条冻结主链的前提下，增加了可本地安装的 QGIS 右侧对话 Dock。

默认 Case 会从 A 机房到 B 基站规划 24 芯光缆。第一次最低相对成本路线故意经过容量不足的 `D017`；Validator 独立返回失败后，Workflow 禁用 `D017` 并仅重新规划一次，最终路线校核通过后才生成 BOM。

## P0 范围

当前已经实现：

- 三种规定句式及轻微空格、措辞差异的离线中文解析；
- 固定 Demo GeoJSON 数据加载与 NetworkX Dijkstra 路由；
- `R_ENDPOINT`、`R_ASSET_STATUS`、`R_CAPACITY` 三条核心校核规则；
- 最大一次的 `forbid_asset` Repair Workflow；
- 两条路线、两次校核、BOM 和中文执行日志的确定性输出；
- 核心单元测试和真实核心调用的端到端测试。

P0 核心仍不包含 LLM、LangChain/LangGraph、GeoAgent、PYORPS、FiberQ、在线 GIS、在线数据、数据库、Web UI、真实造价、施工图或生产部署。P1A 只在适配层使用 QGIS Python API 展示 P0 结果；P0 结果仍是固定合成 Demo，不是现实工程设计结论。

## 目录结构

```text
telecom_core/       已验收的确定性核心：加载、路由、校核、BOM
agent/              中文解析、State、Workflow、输出序列化
data/demo/          固定网络与站点 GeoJSON
scripts/            可重复生成 Demo 数据的脚本
tests/unit/         telecom_core 单元测试
tests/e2e/          解析、Workflow、CLI 和输出端到端测试
tests/p1a/          不启动 QGIS 的控制器、生命周期、图层计划和安装包测试
outputs/            run_demo.py 生成的五个结果文件
qgis_plugin/        QGIS Dock、对话控制器和 PyQGIS 地图适配层
run_demo.py         默认无交互 CLI 入口
docs/               总设计和角色任务书
```

## 环境与安装

目标环境为 Python 3.11。以下 Windows PowerShell 命令可直接复制：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

运行时依赖只有 NetworkX；pytest 用于测试。不需要 API Key、模型服务、网络地图服务或 QGIS Python 环境。

## 生成固定 Demo 数据

仓库已经提交 `data/demo/network.geojson` 和 `data/demo/sites.geojson`。需要复验生成确定性时运行：

```powershell
python scripts/generate_demo_data.py
```

脚本使用固定数据定义，重复运行应生成相同内容。它不是在线数据下载器，也不代表真实城市网络。

## 测试与运行

运行全部测试：

```powershell
python -m pytest -q
```

也可以分别运行核心单测和端到端测试：

```powershell
python -m pytest tests/unit -q
python -m pytest tests/e2e -q
```

一键运行默认 Case：

```powershell
python run_demo.py
```

CLI 也允许用一个位置参数覆盖请求文本，例如：

```powershell
python run_demo.py "从A到B规划24芯光缆"
```

成功退出码为 `0`。解析、数据、路线、校核或 BOM 任一关键步骤失败时状态为 `failed`，CLI 返回非零退出码，并在可用范围内保存已经发生的步骤和失败原因；不会把失败改写成 PASS。

## 输出说明

默认命令只覆盖 `outputs/` 下五个已知同名文件，不递归删除目录：

```text
outputs/first_route.geojson       第一次路线 R001，主 Case 包含 D017
outputs/final_route.geojson       自动修复后路线 R002，不包含 D017
outputs/validation_report.json    两次校核、禁用资产和 repair_count
outputs/bom.json                  由最终路线 segments 确定性计算的简化 BOM
outputs/agent_log.md              与 Agent State 顺序一致的中文执行日志
```

JSON 和 GeoJSON 使用 UTF-8、稳定键顺序和缩进。两个路线文件都是合法 `FeatureCollection`；路线 Feature 包含 `route_id`、`stage`、`edge_ids`、`total_length_m` 和 `relative_cost` 等属性。

## 在 QGIS 中查看最终路线

QGIS 只用于人工查看，不参与程序运行：

1. 先运行 `python run_demo.py`。
2. 打开 QGIS，选择“图层”→“添加图层”→“添加矢量图层”。
3. 选择仓库相对路径 `outputs/final_route.geojson`。
4. 确认图层坐标参考系为 WGS 84（EPSG:4326），并目视检查 A 到 B 的路线是否连续。

程序和自动测试只能验证 GeoJSON 结构及坐标连续性；QGIS 实际打开与目视检查仍由 Quimer 在 H2 执行。

## P1A：QGIS 右侧对话式 Agent Dock

P1A 只增加展示与交互适配层，真实调用现有 `agent.run_workflow()` 和
`agent.write_outputs()`；没有复制或平行重写路由、校核、Repair 或 BOM 算法。
首版支持以下固定请求或按钮：

```text
从A到B规划24芯光缆
重新运行
当前状态
解释失败
定位问题段
显示第一次路线
显示最终路线
查看 BOM
清空对话
帮助
```

构建本地安装 ZIP（默认把当前环境中已安装的纯 Python NetworkX 及其许可证
一起打包，因此插件运行时不需要联网安装依赖）：

```powershell
python scripts/build_qgis_plugin.py --output-dir dist
```

如本机已安装 QGIS，可在 QGIS OSGeo4W Shell 中用它自带的 Python 对安装包
执行无界面边界 smoke：

```powershell
python-qgis-ltr.bat scripts/smoke_qgis_plugin.py
```

该命令使用真实 PyQGIS 类和真实 P0 Workflow，但不显示桌面窗口，不能替代
Quimer 的 GUI 布局、视觉和交互验收。

然后在 QGIS 中选择“插件”→“管理并安装插件”→“从 ZIP 安装”，选择：

```text
dist/telecom_geo_agent-0.2.0.zip
```

启用“通信工程 Agent”后，Dock 注册在右侧。运行规划会加载合成站点、合成
网络、第一次路线、红色 D017 问题段和最终路线。所有数据路径都由插件运行时
根目录加仓库相对路径解析；安装包中的 `BUNDLE_MANIFEST.json` 保存 canonical
P0 源码和数据的 SHA-256，便于确认打包内容没有成为另一套算法。

0.2.0 的功能层不再假定每次运行都必然经过一次 Repair：12 芯请求会如实显示
第一次校核即 PASS；24 芯主 Case 仍显示 D017 Repair；64 芯请求会保留两次
失败、问题资产和未通过路线，但不生成 BOM；未知站点会明确失败并清理上一次
运行留下的插件图层。重新运行前会先释放旧 OGR 图层，避免 Windows 文件锁
阻止 P0 输出更新。

卸载分两步：先在插件管理器取消启用，确认菜单、工具栏入口、Dock 和插件管理
图层均已移除；如需删除文件，再在插件管理器中卸载“通信工程 Agent”。构建、
安装、操作和人工验收的完整步骤见
`docs/p1/P1A_QGIS对话式Agent_Dock验收.md`。

自动测试不会启动 QGIS，也不能证明 Dock 已在真实 QGIS 中加载、交互和正确
显示。该 GUI 验收必须由 Quimer 在安装后的 QGIS 中完成并记录。

## 计算口径与免责声明

路由权重是：

```text
edge_weight = length_m × cost_multiplier
```

这里的 `cost_multiplier` 只表示 Demo 的相对选线代价，不是货币造价。推荐光缆长度固定按最终路线总长增加 10%：

```text
recommended_cable_length_m = total_length_m × 1.10
```

10% 余量同样只是 Demo 假设，不是现实工程统一标准。所有工程使用前都必须由具备资质的人员结合现场、规范、权属、容量和施工条件复核。

## 开源依赖与许可证

- NetworkX：BSD 3-Clause License，用于确定性图路由。
- pytest：MIT License，仅用于开发和测试。
- Python 标准库：用于 JSON、文件输出、正则解析和 CLI。

本仓库未复制或嵌入 GeoAgent、PYORPS、FiberQ 的源码，也未接受这些 P1 候选项目的许可证或建立运行依赖。

## 已知限制

- 解析器只支持任务书规定的固定中文句式和轻微变化，不是通用中文 NLP。
- 只有仓库内的小型 A/B Demo 网络，不含真实地理、道路、建筑、权属或造价数据。
- 只允许一次 Repair，不做无限重试或多候选路线比较。
- BOM 只有长度分类和固定 10% 余量，不是完整材料清单或预算。
- 没有并发执行、鉴权、持久化任务队列、UI 或生产运维能力。
- QGIS 目视验收不由自动化测试替代。
