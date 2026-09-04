# Quimer 执行手册：人工介入、验收与 GitHub 协作

> 本文收纳本项目全部需要人介入的事项。  
> 最高约束：`docs/000通信工程Agent-MVP总设计文档.md`。  
> Quimer 不替 Codex 写代码；Quimer 准备环境、守住范围、验收真实结果、处理 GitHub 权限与合并，并对最终演示负责。

## 1. 人必须介入的节点

```text
H0  开工前：建仓、初始提交、main、分支/worktree、Python 环境
H1  Codex A 完成后：复验核心、审查边界、合并 A
H1.5 Codex B 开工前：把已验收核心带入 B 分支/worktree
H2  Codex B 完成后：全量测试、CLI、QGIS 目视、README 冷启动、合并 B
H3  P0 冻结后：录屏/展示、许可证核对、决定是否启动 P1
```

Codex 正常编写和测试时，人不要逐行遥控，也不要临时增加功能。涉及账号、权限、外部服务、真实环境、许可证或产品取舍时，Codex 停止并交给 Quimer。

## 2. H0：开工准备

### 2.1 确认唯一有效文档

`docs/` 只以以下四份为任务依据：

```text
000通信工程Agent-MVP总设计文档.md
Codex_A_核心路由校核与数据.md
Codex_B_Agent编排集成与交付.md
Quimer_人工介入验收与GitHub协作.md
```

旧版 Codex C/D/E/Human 任务书不得继续发送或执行。

### 2.2 GitHub 仓库和 main

以下动作涉及人的账号和外部写入，由 Quimer 完成：

1. 创建 GitHub 仓库，例如 `telecom-geo-agent`；
2. 选择公开或私有；
3. 将默认分支统一为 `main`；
4. 配置正确的 `origin`；
5. 检查没有凭据、密钥或无关文件；
6. 把四份文档作为初始基线提交并推送；
7. 按团队需要开启 main 分支保护和 PR 审查。

亲自核对：

```powershell
git remote -v
git branch --show-current
git status --short
git log --oneline -3
```

不要把访问令牌写进仓库、任务书或聊天。

### 2.3 两个隔离工作区

推荐：

```text
feature/codex-a-core
feature/codex-b-agent-integration
```

并为两者建立独立 worktree。要求：

- A、B 不在同一目录同时修改；
- A、B 不直接修改 main；
- Quimer 记录每个 Codex 的分支和绝对目录；
- B 正式集成前必须拿到已经通过 H1 的 A 代码。

具体 Git 命令由 Quimer 根据实际仓库状态执行，不把含凭据的命令交给 Codex。

### 2.4 Python 环境

确认 Python 3.11，并为工作区建立独立虚拟环境或明确共用规则：

```powershell
python --version
python -m pip --version
```

P0 不需要安装 QGIS Python 包、GeoAgent、PYORPS、FiberQ 或配置模型 API。

### 2.5 启动 Codex A

把 `Codex_A_核心路由校核与数据.md` 全文直接交给 Codex A，并补充：

```text
这是完整任务指令，总设计为最高约束。
只在指定 A 工作区和允许目录内工作。
完成真实测试后按模板报告，不得合并 main。
```

不要另外口头增加功能。

## 3. Codex A 运行期间何时介入

正常情况不介入。仅处理：

- 找不到正确仓库或分支；
- 工作区有不明改动或目录冲突；
- Python/虚拟环境不可用；
- 安装依赖需要网络代理或系统权限；
- 冻结接口无法实现，需要产品取舍；
- Codex 试图接入 GeoAgent、PYORPS、FiberQ、在线 GIS 或 LLM；
- Codex 要修改 B 的目录或四份文档；
- 测试失败且已有最小复现，需要决定修复还是砍功能。

原则：先修环境和边界，再修最小核心 bug，最后才考虑改总设计；绝不通过新增框架绕过失败。

## 4. H1：Codex A 人工验收

不要只看 Codex 的完成说明。在 A worktree 亲自运行：

```powershell
python scripts/generate_demo_data.py
python -m pytest tests/unit -q
python -m pytest -q
git diff --check
git status --short
```

取得真实核心调用并核对：

```text
第一次 edge_ids 包含 D017
第一次校核 passed=false
rule_id == R_CAPACITY
asset_id == D017
repair_hint == forbid_asset
禁用 D017 后的 edge_ids 不包含 D017
第二次校核 passed=true
BOM 来自第二次路线
```

### 4.1 边界检查

- A 只修改允许目录；
- 没有模型、网络、QGIS 或重型 GIS 依赖；
- 没有本机绝对路径；
- 没把容量检查塞进第一次 Planner；
- RouteResult 保留真实 `edge_ids` 和 `segments`；
- 测试调用真实实现，不是 Mock 主链；
- 生成器固定且可复现；
- 错误输入明确失败。

### 4.2 H1 通过与合并

只有命令返回 0 且事实核对一致，H1 才通过。然后由 Quimer：

1. 审查 A 的 commit/PR；
2. 合并到 main；
3. 在 main 重跑 A 的完整测试；
4. 记录合并 commit。

H1 不通过时，把失败命令、退出码和期望/实际差异发回 A。不要让 B 为错误核心写兼容层。

## 5. H1.5：启动 Codex B

Quimer：

1. 将已验收的最新 main 同步到 B 分支/worktree；
2. 解决 Git 冲突；
3. 在 B 工作区运行 `python -m pytest tests/unit -q`；
4. 确认核心导入和接口与总设计一致；
5. 确认没有 A 的未提交改动。

再把 `Codex_B_Agent编排集成与交付.md` 全文交给 B，并补充：

```text
H1 已通过。必须使用现有 telecom_core，不得复制或越界修改核心。
完成 E2E 和默认 CLI 后按模板报告，不得合并 main。
```

## 6. Codex B 运行期间何时介入

- A 的接口/实现有缺陷，需要跨目录修改；
- B 请求改变冻结字段、重试次数或主 Demo 语义；
- B 想加入 LLM、GeoAgent、UI 或额外 Case；
- B 想使用 GitHub 账号、push/merge main；
- README 声称采用某上游，但代码没有使用；
- 需要运行 QGIS 或视觉判断；
- 需要决定是否提交生成 outputs；
- 测试与演示结果冲突，需要判断代码、数据或文档错误。

跨角色 bug：Quimer 把最小复现交回 A，在 A 分支修复和验证后合并，再同步给 B。不要让 B 永久维护补丁核心。

## 7. H2：完整系统人工验收

在 B 最终候选 worktree，从干净环境亲自执行：

```powershell
python -m pip install -r requirements.txt
python scripts/generate_demo_data.py
python -m pytest tests/unit -q
python -m pytest tests/e2e -q
python -m pytest -q
python run_demo.py
git diff --check
git status --short
```

记录每条命令的退出码和关键输出。

### 7.1 文件和数值交叉核对

打开：

```text
outputs/first_route.geojson
outputs/final_route.geojson
outputs/validation_report.json
outputs/bom.json
outputs/agent_log.md
```

确认：

- first route 包含 D017；
- final route 不包含 D017；
- Validation JSON 同时保留第一次 FAIL、第二次 PASS、`forbidden_asset_ids` 和 `repair_count`；
- `forbidden_asset_ids == ["D017"]`；
- `repair_count == 1`；
- BOM 三类长度可从 final route segments 复算；
- 日志没有跳步或把 Mock 当真实执行；
- 连续运行两次结果一致。

### 7.2 QGIS 目视验收

QGIS 仅在这里由 Quimer 人工使用：

1. 打开 `data/demo/sites.geojson`；
2. 打开 `data/demo/network.geojson`；
3. 打开 `outputs/first_route.geojson`；
4. 打开 `outputs/final_route.geojson`；
5. 确认两条路线都是 A 到 B 的连续 LineString；
6. 确认第一条经过 D017，第二条绕开 D017；
7. 截图保留第一次失败、第二次通过和 BOM。

“QGIS 能打开”必须来自实际打开和目视检查，不能由文件存在替代。

### 7.3 README 冷启动验收

最好新建虚拟环境并严格照 README 操作。任何 README 未写、仅因本机预装才成功的依赖，都视为失败。

### 7.4 H2 通过与合并

自动测试、CLI、输出核对、QGIS 目视和 README 冷启动全部通过后，Quimer 才合并 B 的 PR。

合并后在 main 再运行：

```powershell
python -m pytest -q
python run_demo.py
```

通过后标记 P0 冻结。

## 8. P0 默认砍掉的请求

```text
完整研究三个上游仓库
接入真实 LLM
改造 QGIS 插件
PYORPS 栅格化
FiberQ 全规则
真实 OSM/城市数据
Web UI
多候选路线
建筑 Repair Case
数据库、RAG、多 Agent
真实造价和 CAD
```

H2 通过前不得交换优先级。

## 9. GitHub 与合并责任

下列动作由 Quimer 完成或明确授权：

- 创建仓库、邀请协作者、设置分支保护；
- 选择公开/私有；
- 创建和合并 PR、处理冲突；
- 打 tag/release、删除远程分支；
- 发布仓库或演示材料。

每次合并前检查：

```text
范围符合角色所有权
测试真实运行
依赖与实际一致
无密钥和本机路径
未夸大功能或上游集成
保留失败证据和限制
```

Codex 可在自己的分支形成本地 commit，但不得自行合入 main。

## 10. 开源与数据合规

P0 每个第三方包都在 README 记录：

```text
项目名、官方仓库、实际版本、许可证、本项目如何使用
```

P1 候选：

```text
GeoAgent  https://github.com/iamtekson/GeoAgent
PYORPS    https://github.com/marhofmann/pyorps
FiberQ    https://github.com/vukovicvl/fiberq
```

Quimer 必须注意：

- 不把“参考过”写成“已集成”；
- 不删除作者和许可证；
- 复制 FiberQ 代码前先评估 GPL-3.0-or-later 分发义务；
- 使用真实地图前记录来源、许可证、下载日期和归属；
- Demo 相对成本和 10% 光缆余量不是现实工程标准。

## 11. API Key、QGIS 和外部服务

P0 不需要 API Key。P1 若接入模型：

- Quimer 选择服务商和费用上限；
- Key 只在本机安全位置配置；
- Key 不进入代码、日志、截图、提交或任务书；
- Codex 只有获得当次明确授权后才能调用外部模型；
- 无 Key 时 CLI 核心仍必须运行。

QGIS 安装、插件启用、GUI 和视觉验收均由 Quimer 完成。Codex 只能生成待查看文件和步骤，不能把“应该能打开”说成“已在 QGIS 验收”。

## 12. H3：P0 后的决定

P0 通过后先冻结可回退版本，再一次只选一个 P1：

1. GeoAgent/LLM 入口；
2. PYORPS 独立 smoke test；
3. 真实小区域 GIS 数据；
4. 建筑避让 Case；
5. FiberQ 规则参考扩展；
6. QGIS 插件内展示。

每项只问：

```text
是否让演示更可信？
是否能独立失败而不破坏 P0？
是否有明确验收证据？
是否引入账号、许可证、费用或环境风险？
```

没有明显收益就不做。

## 13. 最终人工验收清单

```text
[ ] main 是唯一正式集成分支
[ ] 四份文档是唯一有效任务依据
[ ] 全量 pytest 返回 0
[ ] python run_demo.py 返回 0
[ ] first route 包含 D017
[ ] 第一次校核 FAIL/R_CAPACITY/D017
[ ] Repair 禁用 D017 且只执行 1 次
[ ] final route 不包含 D017
[ ] 第二次校核 PASS
[ ] BOM 可从 final route 复算
[ ] 五个输出内容互相一致
[ ] QGIS 已实际打开并目视检查 final route
[ ] README 已在干净环境复现
[ ] 无 API Key、绝对路径和无关大文件
[ ] 依赖、许可证和数据来源已说明
[ ] 未宣称不存在的 GeoAgent/PYORPS/FiberQ 集成
[ ] Demo 假设没有被描述成真实工程标准
```

全部勾选后，Quimer 才能宣布 P0 完成。
