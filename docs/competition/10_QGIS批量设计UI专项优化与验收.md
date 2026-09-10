# QGIS 批量设计 UI 专项优化与验收

> 验证日期：2026-09-08
> 开发 checkout：`C:\Users\zhubinhua\.codex\worktrees\6906\通信工程agent`
> 开发分支：`codex/qgis-batch-ui`
> 继承基线：`68226b065fd558894b646879abb35eb0ae50956b`
> 插件版本：`0.5.0`
> QGIS：`3.44.14-Solothurn`

## 1. 结论

QGIS 右侧“通信工程 Agent”已完成一轮独立、可安装、可回归的批量设计 UI 专项优化。默认主页改为“批量设计”，插件启动时保持真正空状态；数据必须由用户明确选择并校验后，才能按“数据准备 → 任务确认 → 运行 → 结果复核 → 导出”继续。界面不再用固定样例数字冒充当前状态，数据量、任务量、状态分布、图层数、来源与地图上下文均从实际载入或实际运行结果生成。

自动化代码、真实 PyQGIS 交互、原生 Qt/QGIS 截图渲染、100%/150% 缩放、窄 Dock、Atlas/GeoPackage 和安装包解压运行均已通过。可见 QGIS 窗口中的最终用户点击与主观视觉验收仍保持 `pending_user`；人工端到端效率基线仍保持 `pending_human_baseline`。本次没有把自动化渲染冒充用户验收，也没有宣称已证明效率提升百分比。

## 2. 范围与边界

本次只优化既有 H0—H6 QGIS 交互与交付，不重写确定性规划核心，不启动 H7，不连接模型、云平台、运营商系统或外部 API。

- 保留 P0 对话与 0.3 单任务参数化设计，批量设计成为主要工作流；
- 没有推送远端、创建或合并 PR，也没有修改 `main`；
- 没有安装或替换用户当前 QGIS 配置目录中的插件；安装包烟测只解压到受控临时目录，测试后清理；
- `E:\Users\zhubinhua\Desktop\data\prepared_20260907` 仅做只读核对。其多个工程包虽有外部校验结果，但 `plugin_gui_integration` 明确为 `not_implemented`，所以界面只显示禁用的“我的工程包 · 待接入”，没有伪造可导入状态；
- 公开 OSM 数据仅作为背景；候选通道几何沿公开道路派生，但通信设施身份、通道身份、容量、占用、状态、优先级、相对成本和 BOM 均为合成竞赛属性；
- 所有输出继续标记“竞赛样例 / 非正式施工图”，不能用于施工、签章、概预算、招标、竣工验收或现实资产判断。

## 3. UI 行为变更

### 3.1 真正空启动与明确数据选择

`BatchController` 构造时只读取内置样例的来源目录说明，不加载完整数据、不预填 CSV、不创建 QGIS 图层。界面显示“未选择数据集”“QGIS 项目显示：未加载本插件数据”，运行和导出入口保持禁用。

用户点击“加载内置样例”后，控制器才执行清单与 SHA-256 校验、加载输入图层、缩放地图，并显示：

- 数据集名称和 ID；
- 公开来源数据集 ID；
- OSM/ODbL 署名；
- 实际网络节点、候选边、机房、接入设施和公开背景要素数量；
- 当前 QGIS 地图显示的是输入图层还是本批次运行结果；
- 当前操作是否与地图使用同一数据集。

任务路径一旦变化，旧请求、确认指纹、运行结果和导出许可立即失效。地图若仍显示旧内容，界面会明确标记它不是当前输入的有效结果。

### 3.2 五阶段主流程

1. **数据准备**：选择数据来源，查看真实性边界、许可、数量和地图上下文；
2. **任务确认**：导入并校验 CSV，显示实际批次、任务数和优先级分布，再生成确认指纹；
3. **运行**：仅在数据与任务均通过、指纹仍有效时启用，显示真实忙碌状态和阻断原因；
4. **结果复核**：按四种中文终态筛选，任务表与地图同步；选择任务可定位路线并显示业务结论；
5. **导出**：只有当前批次执行完成时启用，真实导出 Atlas PDF 与 GeoPackage 后才报告成功。

顶部持续显示“下一步”和当前阻断原因。用户完成操作后，工作区自动滚动到相关阶段，减少在长 Dock 中寻找入口的成本。

### 3.3 结果复核与技术证据

任务表使用“直接成功、绕行成功、待人工复核、明确失败”和“高、中、低”等业务文本，并用颜色区分状态。选择任务后首先显示：

- 业务结论；
- 问题的业务含义及资产 ID；
- 造成冲突的前序任务；
- 合成子管资源 `before→after`；
- 路线长度、建议光缆长度、规格和改路次数，或明确失败原因。

规则 ID、逐次校核、边 ID 和原始错误等技术内容放入默认折叠的“展开技术证据”，既保留可审计性，又避免技术日志压过业务结论。候选路线和最终 PASS 路线可独立显隐；任务选择会选中并缩放对应地图对象。

### 3.4 窄屏与高缩放

批量页改为单一纵向滚动工作区，并允许 Dock 在较小高度下收缩。窄宽度时保留“任务、优先级、状态”主列，自动隐藏机房、长度、改路次数等次要列；详情仍可纵向查看。关键按钮根据可用宽度伸展，不截断中文。

在逻辑窗口 `1024 × 760`、Dock `350 × 760` 下，100% 与 150% 缩放均测得：

- 内容 viewport 与内容宽度同为 `317`；
- 横向滚动最大值为 `0`；
- 隐藏表格列为 `3、4、5`，任务列 `0` 与状态列 `2` 保留；
- 所有五个关键按钮宽度均不小于其 `sizeHint`；
- 150% 下窄屏截图实际像素为 `1536 × 1140`，设备像素比为 `1.5`。

## 4. 主要实现文件

- `qgis_plugin/telecom_geo_agent/batch_widget.py`：五阶段批量工作区、空状态、数据/地图上下文、业务详情、折叠技术证据、响应式任务表；
- `qgis_plugin/telecom_geo_agent/batch_controller.py`：显式数据选择门、输入失效、真实忙碌/阻断状态、运行与导出门控；
- `qgis_plugin/telecom_geo_agent/ui_style.py`：共享的原生 Qt 深色专业样式及状态元数据；
- `qgis_plugin/telecom_geo_agent/dock_widget.py`：批量主页、页签兼容、Dock 尺寸策略与控制器桥接；
- `qgis_plugin/telecom_geo_agent/map_adapter.py` 与 `batch_layer_plan.py`：输入数据地图呈现、实际分组命名和批量联动；
- `qgis_plugin/telecom_geo_agent/atlas_exporter.py`：封面数量改为从实际图层/状态计算；
- `scripts/smoke_batch_qgis.py`：源码级真实 PyQGIS/Qt 交互烟测；
- `scripts/render_qgis_batch_ui.py`：原生 Qt/QGIS 截图与几何测量；
- `scripts/smoke_qgis_plugin.py`：从 ZIP 解压后的插件级回归；
- `tests/batch/test_qgis_contracts.py`：空启动、显式选择、动态结果与输入失效合同。

`.gitattributes` 将经 manifest 审计的公开背景 GeoJSON 标为 `-text`，避免 Windows `core.autocrlf=true` 在 checkout 时改变字节并破坏 SHA-256。此修复只固定字节保真，没有修改公开数据语义。

## 5. 自动化与真实 QGIS 验证

| 验证项 | 命令或入口 | 实际结果 |
|---|---|---|
| 继承关系 | `git merge-base --is-ancestor 68226b... HEAD` | PASS；当前分支继承指定基线 |
| 全量测试 | `python -m pytest -q` | `96 passed` |
| Python 编译 | `python -m compileall -q agent telecom_core competition qgis_plugin scripts tests` | PASS |
| 数据审计 | `python scripts/audit_batch_dataset.py` | PASS；实际计数 411 节点、444 边、3 合成机房、30 合成设施、30 主任务 |
| 批量验收 | `python scripts/run_batch_acceptance.py` | PASS；主批次 19/9/1/1，迁移集不改算法，100 任务无未终态，守恒与反写死检查通过 |
| 源码级 UI | QGIS Python 运行 `scripts/smoke_batch_qgis.py` | PASS；空启动、显式样例 8 输入层、13 结果层、30 行、筛选 19/9/1/1、T002 联动、窄 Dock 均通过 |
| 100% 原生渲染 | `scripts/render_qgis_batch_ui.py --tag native100pct` | PASS；原生平台、DPR 1.0、窄屏 1024×760、无横向滚动 |
| 150% 原生渲染 | `QT_SCALE_FACTOR=1.5` + 同一脚本 | PASS；DPR 1.5、无横向滚动、关键按钮文字完整 |
| Atlas/GeoPackage | QGIS Python 运行 `scripts/export_batch_atlas.py`，再运行 `scripts/verify_batch_atlas.py` | PASS；36 页 A3，PDF 文本重读与全页渲染通过，7 个 GeoPackage 图层重读通过 |
| 安装包内容 | 解读 ZIP metadata 与 `BUNDLE_MANIFEST.json` | PASS；两处版本均为 0.5.0，含 UI 样式和批量数据快照 |
| 安装包运行 | QGIS Python 运行 `scripts/smoke_qgis_plugin.py --bundle dist/telecom_geo_agent-0.5.0.zip` | PASS；P0、单任务、批量、导出、卸载均从解压包通过 |
| 构建可复现性 | 连续两次构建并比较 SHA-256 | PASS；哈希完全一致 |
| 差异检查 | `git diff --check` | PASS |

`outputs/competition_batch/BATCH-MAIN-30/qgis_batch_smoke.json` 明确保留 `visible_gui_user_acceptance: pending_user`；`outputs/competition_batch/acceptance_report.json` 明确保留 `human_baseline_status: pending_human_baseline`。

## 6. 失败证据与最小修复

本次没有用 Mock 或假 PASS 绕过真实失败：

1. 初次全量测试为 `13 failed, 81 passed`。失败集中在批量数据清单哈希，原因是 Windows Git 自动把五个已审计背景 GeoJSON 的 LF 改成 CRLF；加入精确范围的 `.gitattributes` 并恢复其原始 LF 字节后，12 项 manifest 哈希全部匹配，全量测试变为 96 项通过。
2. 初次以 `QT_QPA_PLATFORM=offscreen` 渲染时，中文字体显示为方块。该组图片和其“PASS”报告被拒绝并删除，没有作为视觉证据；随后使用机器默认原生 Qt 平台重跑，中文可读，并生成当前 `native100pct`/`native150pct` 证据。
3. 第一次安装包烟测在单任务场景之后错误断言“整个 QGIS 项目无图层”而失败。空启动断言被移到插件初始化、任何工作流尚未执行的准确时点；修正后同一 ZIP 完整通过。产品逻辑未用假数据规避该失败。

## 7. 交付物与校验值

### 7.1 可安装插件

- 文件：`dist/telecom_geo_agent-0.5.0.zip`
- 大小：`2,479,692` bytes
- SHA-256：`DC5B51AA56A8E19CE8143EE255101A49EBD4BCB88F4EFAD7A16F0899725A7F5E`

### 7.2 UI 证据

- 空启动：`outputs/ui_validation/batch_ui_empty_native100pct.png`
- 数据与任务预览：`outputs/ui_validation/batch_ui_preview_native100pct.png`
- T002 结果复核：`outputs/ui_validation/batch_ui_review_t002_native100pct.png`
- 窄 Dock：`outputs/ui_validation/batch_ui_narrow_native100pct.png`
- 100% 测量报告：`outputs/ui_validation/batch_ui_render_report_native100pct.json`
- 150% 测量报告：`outputs/ui_validation/batch_ui_render_report_native150pct.json`

四张 100% 图片的 SHA-256 依次为：

- `9CDBAE4970A83604D4CF49244B002261EEB391E8B863ABBC4CEC4D6331A7B9FC`
- `3582ECD8DE492CD5561B371D5FF94E2491FBF5085AA8F97F656A4E88A9EECECF`
- `4F4A8D21D848D7671AEB9627982D141A362184ADD5398A2A806E4E815371D755`
- `7794AD2AD769A71E989C21BCA36EDCEB0AAE45147AEB3B16D2E1FC9F0542FD57`

### 7.3 工程输出

> 2026-09-10 发包前使用同一 QGIS 3.44.14 环境重新生成并重读；页数、图层数和内容验证结果不变。QGIS/PDF/GeoPackage 会写入运行元数据，所以重新生成后以下当前哈希取代 2026-09-08 快照值。

- `outputs/competition_batch/BATCH-MAIN-30/design_book.pdf`：25,343,103 bytes，36 页 A3，SHA-256 `4E13ED95A3D72C6E0A776AF6A30384B1FA4EBAC6FD952E314888712A988BB7C3`；
- `outputs/competition_batch/BATCH-MAIN-30/batch_results.gpkg`：442,368 bytes，7 图层，SHA-256 `30467646B4C6B6014166E181EC10B72F912D3E4E93D3127206800178004E2541`。

## 8. 用户在可见 QGIS 中的最终验收

1. 备份当前 QGIS 用户配置；打开可见的 QGIS 3.44 LTR。
2. 进入“插件 → 管理并安装插件 → 从 ZIP 安装”，选择 `dist/telecom_geo_agent-0.5.0.zip`。
3. 打开“通信工程 Agent”，确认默认页签是“批量设计”；启动页不应预选数据、不应预填 CSV，图层面板不应出现本插件图层。
4. 确认“我的工程包 · 待接入”为禁用状态，并显示尚未接入的真实原因。
5. 点击“加载内置样例”，核对数据集 ID、来源/许可、实际计数和地图上的输入层；确认地图上下文注明“尚未运行”。
6. 点击“导入并校验”，再点击“预览任务并生成确认指纹”；核对实际任务数、优先级分布、固定顺序和指纹。
7. 临时修改任务路径，确认旧指纹和运行按钮立即失效；恢复默认路径后重新导入、预览。
8. 点击“确认并运行批量设计”，确认终态为直接 19、绕行 9、待人工复核 1、明确失败 1，地图上下文切换为本批次真实运行结果。
9. 依次使用四种状态筛选，确认任务表与地图同步；选择 T002，确认地图定位、业务详情出现前序任务 T001、合成子管余量不足和资源 `before→after`。
10. 展开“技术证据”，确认可见 `R_SUBDUCT_CAPACITY`、逐次校核和边 ID；折叠后业务详情仍完整。
11. 切换候选/最终路线显隐；把右侧 Dock 缩窄到约 350 px，并在系统 150% 缩放下检查中文按钮、表格主列、滚动和详情无截断。
12. 导出并打开 36 页 PDF，抽查封面、T002、T029、T030、资源、BOM/异常和边界页；核对 OSM 署名、合成属性和“非正式施工图”声明。
13. 加载 `batch_results.gpkg`，核对 7 个图层及任务 30、候选 30、最终 28、问题 13、资源 444、机房 3、设施 30。
14. 禁用插件，确认菜单、工具栏、Dock 和插件自有图层被清理，用户原有图层不受影响。
15. 记录截图或录屏、QGIS 版本、Windows 缩放、Dock 宽度、机器信息、操作时间与结论；完成后才能把 `pending_user` 改为人工验收结果。

## 9. 未完成项

- 可见 QGIS 用户验收：`pending_user`；
- 人工端到端效率基线：`pending_human_baseline`；
- 外部工程包到插件 GUI 的适配器：`not_implemented`；
- H7 模型入口、真实运营商系统、生产级工程规则和正式施工图：不在本次授权范围内。
