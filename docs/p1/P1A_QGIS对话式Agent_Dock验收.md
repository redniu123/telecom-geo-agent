# P1A：QGIS 对话式 Agent Dock 安装、操作与人工验收

> 状态：本地实现与自动测试候选；QGIS GUI 人工验收待 Quimer 执行。
> 产品范围：冻结 P0 Workflow 的 QGIS 右侧对话展示层。
> 数据边界：只允许仓库内合成 P0 Demo；D017 不是现实管道。

当前插件版本：`0.2.0`。P1A 最小切片和功能可靠性层已实现；UI 精修尚未
开始，待本版本人工功能复验后单独进行。

## 1. 交付边界

P1A 真实调用 canonical `agent.run_workflow()`，并用 `write_outputs()` 生成 P0
结果。控制器不会自己计算路线、容量、Repair 或 BOM。PyQGIS 只负责：

1. 注册/卸载右侧 `QDockWidget`、菜单和工具栏入口；
2. 显示对话历史、多行输入、执行状态和分阶段结果卡片；
3. 加载 `data/demo/sites.geojson`、`data/demo/network.geojson`、
   `outputs/first_route.geojson` 与 `outputs/final_route.geojson`；
4. 从合成网络筛选 D017 为独立红色问题图层；
5. 切换第一次/最终路线以及定位 D017。

没有 LLM、本地模型、云模型、API Key、在线服务、现实数据 Adapter、生产
数据库、自动发布或现实通信网络。插件不会读取仓库外的 staging OSM 数据。

## 2. 构建可安装 ZIP

在仓库根目录、Python 3.11 环境执行：

```powershell
python -m pytest -q
python scripts/build_qgis_plugin.py --output-dir dist
```

本机若有 QGIS，可在构建后从 QGIS OSGeo4W Shell 运行可复现的 headless
边界 smoke：

```powershell
python-qgis-ltr.bat scripts/smoke_qgis_plugin.py
```

它从 ZIP 临时解压插件，使用真实 PyQGIS/Qt 类、真实 OGR 图层和真实 P0
Workflow，验证路线切换、D017 选择以及 unload 清理；它不打开桌面窗口，仍
不能替代第 7 节的人工 GUI 验收。

默认安装包会把以下内容放在唯一的 `telecom_geo_agent/` 顶层目录中：

```text
插件 UI / 控制器 / PyQGIS 适配层
p0_runtime/agent/                 canonical P0 Agent 源码的原样快照
p0_runtime/telecom_core/          canonical P0 核心源码的原样快照
p0_runtime/data/demo/             canonical 合成 P0 数据
p0_runtime/networkx/              本机构建环境中的 NetworkX
p0_runtime/networkx-*.dist-info/  版本元数据和 BSD 3-Clause 许可证
BUNDLE_MANIFEST.json              canonical 文件 SHA-256 和依赖版本
```

这里的快照是安装打包，不是仓库内维护的第二套实现。构建测试会逐字节比较
关键 canonical 文件，运行时只导入 `p0_runtime` 中这一份 P0。如果不希望把
NetworkX 打包，只有在确认 QGIS Python 已能 `import networkx` 后才可使用：

```powershell
python scripts/build_qgis_plugin.py --output-dir dist --without-networkx
```

## 3. QGIS 本地安装与启用

1. 打开 QGIS 3.28—3.x。
2. 选择“插件”→“管理并安装插件”→“从 ZIP 安装”。
3. 选择 `dist/telecom_geo_agent-0.2.0.zip`。
4. 接受本地实验插件提示并完成安装。
5. 在“已安装”列表勾选“通信工程 Agent”。
6. 确认右侧出现标题为“通信工程 Agent”的 Dock；若被关闭，可从插件菜单或
   工具栏图标重新打开。

不应把 `qgis_plugin/telecom_geo_agent` 源目录直接复制到插件目录后再期待它
独立运行，因为源码模式需要仓库中的 canonical P0。正式本地验收应使用构建
出的 ZIP。

## 4. 操作步骤与预期事实

在多行输入框输入：

```text
从A到B规划24芯光缆
```

点击“发送”或按 `Ctrl+Enter`。对话卡片必须按以下顺序出现：

1. 第一次路线 `R001`：`D001 → D017 → D003`；
2. 第一次校核 `FAIL / R_CAPACITY`；
3. 明示 D017 是“仓库内合成 P0 测试段，不是现实管道”；
4. 明示总容量 48 芯、已用 32 芯、剩余 16 芯，小于 24 芯需求；
5. 自动修复禁用 D017，`repair_count=1`；
6. 重新规划 `R002`：`N001 → N002`；
7. 最终校核 `PASS`；
8. BOM：总长 400.00 m、已有管道 180.00 m、新建 220.00 m、建议光缆
   440.00 m、`used_edge_ids=N001 → N002`。

地图图层组中必须能辨认：

```text
P0 合成网络                         灰色细线
P0 合成站点 A / B                   蓝色点
第一次路线 R001                     橙色虚线，默认隐藏
最终路线 R002（PASS）               绿色实线，默认显示
D017 容量不足（合成测试段）         红色粗线，默认显示
```

逐一输入或点击：

```text
解释失败
重新运行
当前状态
定位问题段
显示第一次路线
显示最终路线
查看 BOM
清空对话
帮助
```

预期行为：解释失败重复给出可复算容量事实；定位问题段选择并缩放到红色
D017；两条路线命令互斥切换并缩放；BOM 取自当前真实 Workflow 状态；清空
只清除对话卡片，保留本次规划上下文和地图结果。

### 4.1 功能可靠性补充 Case

这些 Case 仍使用同一套合成 P0 数据，用于证明面板没有把 24 芯主流程写死。

输入：

```text
从A到B规划12芯光缆
```

预期：第一次路线 `R001` 校核即 PASS；`repair_count=0`；最终路线沿用 R001；
建议光缆 385.00 m；不出现红色问题图层。

输入：

```text
从A到B规划64芯光缆
```

预期：第一次和第二次校核均保留真实容量失败；状态为 failed；问题资产为
D017、D003、N001；第二次路线可作为“未通过路线”查看，但不得显示成 PASS，
也不得生成 BOM。

输入：

```text
从A到C规划24芯光缆
```

预期：明确报告未知站点 C，不生成路线/BOM，并清理上一次运行的插件图层。
连续运行不同 Case 时，插件必须先释放自己持有的旧 OGR 图层，再由 P0 输出器
更新结果，不能因 Windows 文件锁而保留过期地图结果。

## 5. 相对路径与项目可移植性

图层计划只保存以下 POSIX 风格相对路径：

```text
data/demo/sites.geojson
data/demo/network.geojson
outputs/first_route.geojson
outputs/final_route.geojson
```

运行时以安装包内 `p0_runtime/` 为根解析。每个 QGIS 图层同时写入自定义属性
`telecom_geo_agent/source_relative_path`，不会在源码、安装包清单或对话日志中
写入构建机器的绝对路径。若保存 `.qgz` 项目并需要跨机器搬移，应把 QGIS
项目的路径存储设置为“相对”，并连同完整插件/运行时一起移动；Quimer 需要
在目标机重新打开项目验证，自动测试不能代替该步骤。

## 6. 禁用与卸载验收

1. 在插件管理器取消勾选“通信工程 Agent”。
2. 确认 Dock 消失。
3. 确认“通信工程 Agent”插件菜单项和工具栏图标消失。
4. 确认五个由插件管理的图层被移除；用户自己的其他图层不得被移除。
5. 重新启用一次，确认不会重复注册菜单、Dock 或图层。
6. 如需删除安装文件，在插件管理器选择卸载。

插件 `unload()` 只清理带 `telecom_geo_agent/layer_key` 属性的自有图层，不
递归删除文件，也不关闭 QGIS。

## 7. Quimer 人工验收记录模板

```text
QGIS 完整版本：
操作系统：
安装包 SHA-256：
安装/启用：PASS / FAIL
右侧 Dock 和布局：PASS / FAIL
固定请求真实运行：PASS / FAIL
卡片顺序与 D017 合成声明：PASS / FAIL
D017 红色显示及定位：PASS / FAIL
第一次/最终路线切换：PASS / FAIL
最终 PASS / BOM：PASS / FAIL
禁用后菜单、工具栏、Dock、插件图层无残留：PASS / FAIL
截图/录屏路径：
实际错误文本（如有）：
结论：
```

只有上述真实 QGIS 操作完成后，才能写“QGIS GUI 人工验收通过”。ZIP 构建
成功、文件存在、普通 Python 测试通过或静态截图都不能单独替代该结论。
