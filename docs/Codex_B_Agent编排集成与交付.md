# Codex B 执行指令：任务解析、Agent Workflow、集成测试与交付

> 本文可直接作为 Codex B 的完整任务指令。  
> 最高约束：`docs/000通信工程Agent-MVP总设计文档.md`。  
> 开工 Gate：Quimer 已验收并合并 Codex A，当前分支已包含核心代码。  
> 目标：把核心能力接成一条命令可运行的“容量失败—自动修复—BOM”闭环。  
> 完成后由 Quimer 验收并合并；你不得合并 `main`。

## 1. 立即执行的目标

```text
中文输入
→ TelecomTask
→ 第一次规划
→ Validator
→ 读取 repair_hint 并禁用 D017
→ 第二次规划
→ 再次校核
→ BOM
→ 输出两条 GeoJSON、两次校核、BOM 和日志
```

P0 默认完全离线，不调用 LLM。这里的 Agent 价值是可观察的状态、工具编排、校核反馈和有界 Repair Loop，而不是用模型生成工程事实。

## 2. 开始前检查

先执行：

```powershell
git rev-parse --show-toplevel
git branch --show-current
git status --short
python -m pytest tests/unit -q
```

确认以下核心导入存在：

```python
from telecom_core.data_loader import ...
from telecom_core.routing import plan_route
from telecom_core.validation import validate_route
from telecom_core.bom import calculate_bom
```

开工前必须确认：

- 当前分支/worktree 由 Quimer 指定给 Codex B；
- Codex A 单元测试真实通过；
- Demo 第一次路线包含 D017；
- 核心接口与本文第 6 节一致；
- 没有无法解释的他人改动。

任一条件不成立时，不要复制 `telecom_core` 或写平行实现；把缺失文件、命令、退出码和接口差异交给 Quimer。

## 3. 文件所有权

可以创建或修改：

```text
agent/
tests/e2e/
run_demo.py
README.md
outputs/ 的生成逻辑
requirements.txt（仅添加实际必需依赖）
.gitignore
```

不得修改：

```text
telecom_core/
data/demo/
scripts/generate_demo_data.py
tests/unit/
docs/ 下四份设计/角色文档
```

发现核心 bug 时，以失败测试和最小复现交给 Quimer/Codex A，不得越界修复。

## 4. 固定运行边界

P0 不使用：

- OpenAI、Gemini、Anthropic、Ollama 或任何 LLM；
- LangChain、LangGraph、GeoAgent；
- QGIS Python API；
- 在线地图、数据库或网络服务；
- Streamlit 或 Web 框架。

除 A 已提供的依赖外，优先只用 Python 标准库和 pytest。新增运行依赖必须有必要性和测试证据。

## 5. 必须创建

```text
agent/__init__.py
agent/parser.py
agent/state.py
agent/workflow.py
tests/e2e/test_demo_workflow.py
tests/e2e/test_cli_outputs.py
run_demo.py
README.md
```

可以增加少量辅助文件，但不做框架化扩张。

## 6. 冻结接口摘要

### 6.1 TelecomTask

```python
{
    "task_type": "fiber_route",
    "start_site_id": "A",
    "end_site_id": "B",
    "fiber_cores": 24,
    "prefer_existing_duct": True
}
```

### 6.2 RouteResult 必备字段

```text
success
route_id
start_site_id
end_site_id
segments
edge_ids
geometry
total_length_m
relative_cost
forbidden_asset_ids_applied
```

### 6.3 ValidationResult 必备字段

```text
passed
violations[].rule_id
violations[].type
violations[].asset_id
violations[].severity
violations[].message
violations[].repair_hint
```

### 6.4 BOMResult 必备字段

```text
total_length_m
existing_duct_length_m
new_build_length_m
recommended_cable_length_m
slack_ratio
used_edge_ids
```

不得兼容第二套字段名。序列化辅助函数可放在 `agent/`，但不能篡改核心语义。

## 7. 离线中文解析

对外函数：

```python
parse_request(user_text, available_site_ids) -> TelecomTask
```

必须支持：

```text
从 A 机房到 B 基站规划一条 24 芯光缆，优先使用已有管道。
从A到B规划24芯光缆
A 到 B，24芯，优先走已有管道
```

固定语义：

- 识别 `从 X 到 Y` 或 `X 到 Y`；
- 识别 `N 芯`，N 必须为正整数；
- 出现“优先使用/利用/走已有管道”时设为 `True`；
- 未写时默认仍为 `True`，但日志标注使用默认值；
- `task_type` 固定为 `fiber_route`；
- 起终点必须存在于 `available_site_ids`；
- 缺起点、终点、芯数或出现未知站点时明确失败，不得猜测。

不要做通用中文 NLP，不要调用模型。

## 8. Agent State

在 `agent/state.py` 定义可序列化、可测试的状态，至少包含：

```python
{
    "user_request": str,
    "task": object | None,
    "first_route": object | None,
    "final_route": object | None,
    "validation_history": list,
    "forbidden_asset_ids": list[str],
    "repair_count": int,
    "bom_result": object | None,
    "execution_log": list[str],
    "status": "pending" | "completed" | "failed",
    "error": str | None
}
```

不得只打印日志而不保存状态。失败也必须保留已发生步骤和证据。

## 9. Workflow 固定步骤

实现普通 Python 有界状态机，不需要 LangGraph：

```text
1. 读取并校验 Demo 数据
2. parse_request
3. plan_route(task, ..., forbidden_asset_ids=[], route_id="R001")
4. 保存 first_route
5. validate_route(first_route, task, ...)
6. 若 PASS：计算 BOM（主 Case 不应走这里）
7. 若 FAIL：只处理 severity=error 且 repair_hint=forbid_asset 的 violation
8. 将 asset_id 去重加入 forbidden_asset_ids
9. repair_count += 1
10. 再次 plan_route(..., forbidden_asset_ids=["D017"], route_id="R002")
11. 保存 final_route
12. 再次 validate_route
13. 若仍 FAIL：状态设为 failed，以非零退出
14. 若 PASS：calculate_bom(final_route)
15. 状态设为 completed
```

最大 Repair 次数固定为 1。严禁无限重试、吞异常、把 FAIL 改写成 PASS，或在 Workflow 中重新计算容量和长度。

若第一次校核没有在 D017 上返回 `R_CAPACITY`，主 Demo 必须失败，不能继续输出“演示成功”。

## 10. CLI、GeoJSON 和报告

`run_demo.py` 默认输入：

```text
从 A 机房到 B 基站规划一条 24 芯光缆，优先使用已有管道。
```

允许 CLI 参数覆盖文本，但默认命令必须无交互运行：

```powershell
python run_demo.py
```

输出固定为仓库相对路径 `outputs/`。生成前只覆盖五个已知同名文件，不得递归删除整个目录：

```text
first_route.geojson
final_route.geojson
validation_report.json
bom.json
agent_log.md
```

要求：

- UTF-8；
- JSON 使用稳定键顺序和缩进；
- GeoJSON 是合法 `FeatureCollection`；
- 路线属性至少包含 `route_id`、`stage`、`edge_ids`、`total_length_m`、`relative_cost`；
- Validation JSON 保存 `validation_history`、`forbidden_asset_ids` 和 `repair_count`，不得只保留最终 PASS；
- Agent 日志为人可直接阅读的中文步骤；
- 输出不得包含本机绝对路径。

CLI 成功时打印：

```text
第一次路线：... D017 ...
第一次校核：FAIL R_CAPACITY D017
自动修复：forbid D017
第二次路线：...（不含 D017）
第二次校核：PASS
BOM：总长 ...，已有管道 ...，新建 ...，建议光缆 ...
输出目录：outputs/
```

成功退出码为 0；关键步骤失败返回非零退出码。

## 11. E2E 测试必须证明

1. 三种规定输入解析为相同核心 TelecomTask；
2. 缺芯数、未知站点、非正芯数明确失败；
3. 完整 Workflow 的第一次路线包含 D017；
4. 第一次校核为 FAIL/R_CAPACITY/D017；
5. `forbidden_asset_ids == ["D017"]`；
6. `repair_count == 1`；
7. 最终路线不包含 D017；
8. 第二次校核 PASS；
9. BOM 来自 final route，不是 first route；
10. 五个输出内容与最终状态一致；
11. 连续运行两次，核心 JSON 一致；
12. 替代路线也失败时，Workflow 为 failed 且 CLI 非零；
13. 测试期间没有网络调用。

E2E 调用真实 `telecom_core`。只允许失败路径注入最小替身，不允许 Mock 主成功链。

## 12. README 要求

只写已经验证的内容，至少包括：

```text
项目是什么
P0 能做什么/不能做什么
目录结构
Python 版本
创建虚拟环境和安装依赖
生成 Demo 数据
运行测试
运行 python run_demo.py
输出说明
用 QGIS 打开 final_route.geojson
相对成本和 10% 余量免责声明
开源依赖与许可证
已知限制
```

Windows 命令必须可复制。不得声称已经集成 GeoAgent、PYORPS 或 FiberQ；它们在 P0 只是后续候选/参考。

## 13. 实际验证

完成后必须运行：

```powershell
python -m pytest tests/unit -q
python -m pytest tests/e2e -q
python -m pytest -q
python run_demo.py
git diff --check
git status --short
```

实际读取并交叉核对：

- first route 包含 D017；
- final route 不包含 D017；
- Validation JSON 同时包含第一次 FAIL 和第二次 PASS；
- BOM 能由 final route 复算；
- Agent 日志顺序与真实 State 一致。

不得只报告 pytest 最后一行；必须报告两次 edge IDs、校核结果和 BOM 摘要。

## 14. 完成条件

只有以下条件全部满足才可报告完成：

- 默认命令真实完成主 Case；
- 完整测试返回 0；
- 输出交叉核对一致；
- 没有越界修改 Codex A 目录；
- 没有模型、网络或 QGIS 运行依赖；
- README 与实际命令一致；
- 未把 Demo 权重和 BOM 余量写成真实工程标准；
- 没有 API Key、绝对路径或不可解释文件。

## 15. 给 Quimer 的交付报告

最终回复必须包含：

```text
1. 实际完成内容
2. 修改/新增文件清单
3. 实际执行命令及退出码
4. 全部测试通过数量
5. 第一次和第二次路线 edge_ids
6. 两次校核结果
7. forbidden_asset_ids 和 repair_count
8. BOM 摘要
9. 五个输出文件核对结果
10. 未完成项、限制和 Quimer 复验步骤
```

不要创建/配置 GitHub、push 或合并 main、安装/操作 QGIS、申请 API Key、接受上游许可证或启动 P1；这些属于 Quimer。
