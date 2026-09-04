# TelecomGeoAgent MVP 总设计文档

> 状态：P0 唯一最高约束  
> 适用角色：Codex A、Codex B、Quimer  
> 冲突规则：子文档、临时讨论或 Codex 自行判断与本文冲突时，以本文为准。只有 Quimer 可以批准修改本文。

## 1. 一句话目标

用户输入：

```text
从 A 机房到 B 基站规划一条 24 芯光缆，优先使用已有管道。
```

系统必须自动完成：

```text
自然语言解析
→ 第一次路由
→ 发现 D017 管道容量不足
→ 禁用 D017
→ 第二次路由
→ 校核通过
→ 输出 BOM、日志和可在 QGIS 打开的 GeoJSON
```

这一个 Case 真实跑通，就是 P0 成功。P0 不是完整通信设计平台，也不代表真实工程设计结果。

## 2. P0 必须交付

1. 支持一条固定中文句式及其轻微措辞变化，解析为 `TelecomTask`。
2. 读取仓库内固定、可复现的小型 GeoJSON Demo 网络。
3. 使用 NetworkX Dijkstra，按照相对成本生成路线。
4. 第一次路线必须因为成本较低而经过 `D017`。
5. Validator 必须独立发现 `D017` 剩余芯数不足。
6. Workflow 把 `D017` 加入 `forbidden_asset_ids` 后重新规划。
7. 第二次路线不得再经过 `D017`，且必须校核通过。
8. 根据最终路线确定性计算简化 BOM。
9. 一条命令生成第一次路线、最终路线、两次校核、BOM 和执行日志。
10. 自动测试必须证明以上事实，而不只是证明文件存在。

## 3. P0 明确不做

任何 Codex 不得自行加入：

- GeoAgent/QGIS 插件改造；
- PYORPS 正式集成或栅格 Cost Surface；
- 直接复制或嵌入 FiberQ 源码；
- 云端 LLM、API Key、Ollama 或在线服务；
- Streamlit、Web UI、复杂 QGIS UI；
- 真实城市级数据、在线 OSM 下载、PostGIS；
- 多 Agent、RAG、知识图谱、长期记忆；
- 多候选路线比较、建筑阻挡 Repair Case；
- 真实造价、CAD、施工图、完整 FTTH/GPON 设计；
- 性能优化、生产部署。

完成 P0 并由 Quimer 验收后，才可以选择第 14 节的一个 P1 项目。

## 4. P0 固定技术选择

```text
Python 3.11
NetworkX：图路由
Python 标准库：JSON、日志、文件输出
pytest：自动测试
GeoJSON：输入和地图输出
QGIS：只用于人工打开结果，不参与程序运行
```

P0 不依赖 GeoPandas、Rasterio、PyQGIS、LangChain 或模型服务。若本机 Python 版本需要调整，由 Quimer 决定，Codex 不得擅自升级整个环境。

## 5. 最小架构与责任

```text
run_demo.py
    ↓
parse_request()                 # Codex B
    ↓
TelecomTask
    ↓
load_demo_network()             # Codex A
    ↓
plan_route()                    # Codex A
    ↓
validate_route()                # Codex A
    ↓
passed?
  ├─ yes → calculate_bom()      # Codex A
  └─ no  → apply repair hint    # Codex B Workflow
              ↓
          plan_route(forbidden_asset_ids)
              ↓
          validate_route()
              ↓
          calculate_bom()
    ↓
write_outputs()                 # Codex B
```

- 解析和 Workflow 决定下一步调用什么。
- 路由、容量、长度、BOM、GeoJSON 均由确定性程序计算。
- Workflow 负责重试次数和结束条件。
- 不允许模型猜坐标、长度、容量、管道 ID 或校核结果。

## 6. 唯一 P0 Demo 数据

固定输入：

```text
data/demo/network.geojson
data/demo/sites.geojson
```

坐标使用 WGS84，顺序固定为 `[longitude, latitude]`。

### 6.1 站点字段

```text
site_id       唯一 ID，例如 A、B
name          人类可读名称
site_type     telecom_room 或 base_station
node_id       绑定的网络节点
status        available
geometry      GeoJSON Point
```

### 6.2 网络边字段

```text
edge_id             唯一 ID，例如 D017、N002
from_node            起点节点 ID
to_node              终点节点 ID
asset_type           existing_duct 或 new_build
length_m             正数
cost_multiplier      正数；仅表示相对选线代价
capacity_cores       非负整数
used_cores           非负整数
status               available 或 unavailable
geometry             GeoJSON LineString
```

固定不变量：

- P0 网络边均按双向可通行处理；反向经过边时必须反转该段坐标顺序。
- 图中至少有两条 A 到 B 的路径。
- `D017` 属于第一次最低成本路径。
- `D017.capacity_cores - D017.used_cores < 24`。
- 不经过 D017 的替代路径成本更高，但容量满足且状态可用。
- 固定数据提交进仓库；生成脚本使用固定 seed，重复运行内容一致。

## 7. P0 冻结接口

字段名、类型和语义在 P0 期间冻结。A、B 均不得自行改名。

### 7.1 TelecomTask

```python
{
    "task_type": "fiber_route",
    "start_site_id": "A",
    "end_site_id": "B",
    "fiber_cores": 24,
    "prefer_existing_duct": True
}
```

### 7.2 RouteSegment

```python
{
    "edge_id": "D017",
    "from_node": "N1",
    "to_node": "N2",
    "asset_type": "existing_duct",
    "length_m": 120.0,
    "relative_cost": 120.0,
    "geometry": {"type": "LineString", "coordinates": []}
}
```

### 7.3 RouteResult

```python
{
    "success": True,
    "route_id": "R001",
    "start_site_id": "A",
    "end_site_id": "B",
    "segments": [],
    "edge_ids": ["D001", "D017", "D003"],
    "geometry": {"type": "LineString", "coordinates": []},
    "total_length_m": 2350.0,
    "relative_cost": 128.3,
    "forbidden_asset_ids_applied": []
}
```

`edge_ids` 和 `segments` 是 Validator 与 BOM 的事实依据，不能只返回一条无资产绑定的几何线。

### 7.4 ValidationResult

```python
{
    "passed": False,
    "violations": [
        {
            "rule_id": "R_CAPACITY",
            "type": "duct_capacity",
            "asset_id": "D017",
            "severity": "error",
            "message": "D017 剩余容量不足以承载 24 芯光缆",
            "repair_hint": "forbid_asset"
        }
    ]
}
```

P0 只要求三条错误规则：

1. `R_ENDPOINT`：路线必须从任务起点到达任务终点；
2. `R_ASSET_STATUS`：不得使用 `unavailable` 资源；
3. `R_CAPACITY`：仅对 `existing_duct` 检查，剩余容量必须大于等于任务芯数；`new_build` 不套用已有管道容量字段。

几何、字段和长度的健康检查由数据加载阶段负责，不扩展成完整规则库。

### 7.5 BOMResult

```python
{
    "total_length_m": 2350.0,
    "existing_duct_length_m": 1890.0,
    "new_build_length_m": 460.0,
    "recommended_cable_length_m": 2585.0,
    "slack_ratio": 0.10,
    "used_edge_ids": ["D001", "N002", "D003"]
}
```

固定公式：

```text
recommended_cable_length_m = total_length_m × 1.10
```

这是 Demo 假设，不是现实工程统一标准。所有长度输出保留两位小数。

## 8. 路由、校核和 Repair 的固定语义

第一次路由权重：

```text
edge_weight = length_m × cost_multiplier
```

核心调用固定为：

```python
plan_route(task, network, forbidden_asset_ids, route_id) -> RouteResult
```

第一次传入 `route_id="R001"`，Repair 后第二次传入 `route_id="R002"`。

Planner 排除：

```text
status == unavailable
或 edge_id ∈ forbidden_asset_ids
```

第一次路由故意不检查容量。容量属于独立 Validator，因此第一次可以选中成本较低但容量不足的 D017。

Repair 固定规则：

```text
当 severity == error 且 repair_hint == forbid_asset：
把 asset_id 去重加入 forbidden_asset_ids，然后重新规划。
```

P0 最大重新规划 1 次。第二次仍失败时，程序必须以非零退出码结束并写出原因，不得伪造 PASS。

## 9. 一键运行与输出

```powershell
python -m pytest -q
python run_demo.py
```

Demo 最终生成：

```text
outputs/first_route.geojson
outputs/final_route.geojson
outputs/validation_report.json
outputs/bom.json
outputs/agent_log.md
```

日志至少记录：任务解析、第一次 edge IDs、D017 容量失败、禁用 D017、第二次 edge IDs、最终 PASS 和 BOM 生成。

`validation_report.json` 必须同时保存 `validation_history`、`forbidden_asset_ids` 和 `repair_count`，便于人工交叉核对，不能只保存最终 PASS。

## 10. 仓库边界与所有权

```text
telecom-geo-agent/
├── telecom_core/               # Codex A
├── agent/                      # Codex B
├── data/demo/                  # Codex A
├── scripts/                    # Codex A
├── tests/unit/                 # Codex A
├── tests/e2e/                  # Codex B
├── outputs/                    # Codex B 生成
├── run_demo.py                 # Codex B
├── requirements.txt            # A 创建，B 只添加实际必需依赖
├── README.md                   # Codex B
└── docs/                       # 本文与三份子文档
```

- A 不修改 `agent/`、`run_demo.py`、`tests/e2e/`、`README.md`。
- B 不修改 `telecom_core/`、`data/demo/`、`scripts/`、`tests/unit/`。
- 公共接口有问题时必须交给 Quimer，禁止静默改名或维护两套接口。
- Quimer 负责 GitHub、分支、PR、合并、人工环境和最终验收。

## 11. 开发顺序与人工 Gate

```text
H0：Quimer 建仓、建立 main 和两个隔离工作区
    ↓
Codex A：数据、路由、校核、BOM、单元测试
    ↓
H1：Quimer 复验 A 并合并
    ↓
Codex B：解析、Workflow、Repair、CLI、E2E、README
    ↓
H2：Quimer 全量验收、QGIS 目视检查并合并
```

Codex B 可以提前阅读任务书，但正式集成必须基于已经通过 H1 的核心代码。

## 12. P0 完成定义

必须同时成立：

- `python -m pytest -q` 返回 0；
- `python run_demo.py` 返回 0；
- 第一次路线真实包含 D017；
- 第一次校核真实返回 `passed=false`、`R_CAPACITY`、`asset_id=D017`；
- 最终路线真实不包含 D017；
- 最终校核真实返回 `passed=true`；
- BOM 能由最终 segments 复算；
- 连续两次运行得到相同核心 JSON；
- QGIS 实际打开 final route，并显示 A 到 B 的连续路线；
- README 在干净环境可复现；
- 没有 API Key、绝对本机路径或未说明的数据来源。

文件存在、测试数量、Codex 自述、截图或 Mock PASS 都不能单独作为验收证据。

## 13. 失败和停止规则

出现以下情况必须明确失败并停止扩展：

- A/B 站点不存在；
- GeoJSON、字段、坐标或节点引用无效；
- A 到 B 无路径；
- Repair 后仍不通过；
- BOM 与最终路线段不一致；
- 测试依赖网络、API Key、QGIS Python 环境或本机绝对路径；
- 必须修改冻结接口才能继续。

Codex 必须报告实际命令、退出码、错误文本和影响范围，不得用假数据替换失败后宣称完成。

## 14. P1 候选项

P0 经 Quimer 验收后，每次只可选择一个：

1. 接入指定并锁定 commit 的 GeoAgent，增加真正的模型解析入口；
2. 对 PYORPS 做独立 smoke test，再决定是否补充/替换 NetworkX；
3. 加入真实小范围道路、建筑数据及来源/许可证说明；
4. 加入建筑避让 Case；
5. 参考 FiberQ 扩充规则和 BOM，但不直接复制源码；
6. 增加 QGIS 插件内展示。

真实数据到位后，使用独立待办任务书：

```text
docs/p1/P1_真实数据接入与现实场景升级.md
```

该文档在 P0 冻结和数据接收卡填写完成前不得执行。

候选上游：

```text
GeoAgent  https://github.com/iamtekson/GeoAgent
PYORPS    https://github.com/marhofmann/pyorps
FiberQ    https://github.com/vukovicvl/fiberq
```

采用前由 Quimer 锁定 URL、版本/commit、许可证、复用方式和验证命令。“研究过”不算集成完成。

## 15. 最高优先级

```text
P0-1：一条命令真实运行
P0-2：容量失败与自动重规划真实发生
P0-3：结果可确定性复算
P0-4：QGIS 可查看
P0-5：代码和说明可复现
P1：再考虑模型、PYORPS、真实 GIS 和 UI
```

> 能运行、能复算、能验收，比框架多、页面漂亮或概念先进更重要。
