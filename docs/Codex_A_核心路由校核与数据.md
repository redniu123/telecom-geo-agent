# Codex A 执行指令：核心路由、校核、BOM 与 Demo 数据

> 本文可直接作为 Codex A 的完整任务指令。  
> 最高约束：`docs/000通信工程Agent-MVP总设计文档.md`。  
> 目标：交付不依赖模型、QGIS Python 环境或网络的确定性核心。  
> 完成后由 Quimer 验收并合并；你不得合并 `main`。

## 1. 立即执行的目标

在当前仓库实现并验证：

```text
固定 GeoJSON Demo 数据
→ 最低相对成本路线
→ 第一次路线经过 D017
→ Validator 报告 D017 容量不足
→ 接受 forbidden_asset_ids 后生成替代路线
→ 替代路线不经过 D017 且校核通过
→ 计算简化 BOM
```

你只负责核心库、数据、生成脚本和单元测试，不负责自然语言解析、Agent Workflow、一键 Demo、README、QGIS 操作或 GitHub 合并。

## 2. 开始前检查

先执行只读检查：

```powershell
git rev-parse --show-toplevel
git branch --show-current
git status --short
```

然后：

- 确认位于 Quimer 指定的 Codex A 功能分支或 worktree；
- 完整阅读总设计；
- 保留用户已有文件和无关改动；
- 不读取、索要或写入 API Key；
- 不下载 GeoAgent、PYORPS、FiberQ 或在线 GIS 数据。

若分支/工作目录不明确、总设计不存在或其他角色正在修改你的目录，停止写入并把证据交给 Quimer。

## 3. 文件所有权

可以创建或修改：

```text
telecom_core/
data/demo/
scripts/generate_demo_data.py
tests/unit/
requirements.txt
.gitignore
```

不得修改：

```text
agent/
tests/e2e/
run_demo.py
README.md
docs/ 下四份设计/角色文档
```

接口无法实现时，不能静默改文档或另造字段，必须向 Quimer 报告。

## 4. 固定依赖

P0 仅允许：

```text
Python 3.11
networkx
pytest
Python 标准库
```

不要加入 GeoPandas、Shapely、Rasterio、PyQGIS、LangChain、Pydantic 或数据库。GeoJSON 读写使用标准库。

`requirements.txt` 使用合理版本范围，不要把本机完整 `pip freeze` 倾倒进去。

## 5. 必须创建

```text
telecom_core/__init__.py
telecom_core/models.py
telecom_core/data_loader.py
telecom_core/routing.py
telecom_core/validation.py
telecom_core/bom.py
scripts/generate_demo_data.py
data/demo/network.geojson
data/demo/sites.geojson
tests/unit/test_data_loader.py
tests/unit/test_routing.py
tests/unit/test_validation.py
tests/unit/test_bom.py
```

可以增加少量内部辅助文件，但不要扩大架构。

## 6. 冻结接口

可以用 `dataclass`、`TypedDict` 或简单对象实现，但对外序列化必须保持以下字段。

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

### 6.2 RouteSegment

```python
{
    "edge_id": str,
    "from_node": str,
    "to_node": str,
    "asset_type": "existing_duct" | "new_build",
    "length_m": float,
    "relative_cost": float,
    "geometry": {"type": "LineString", "coordinates": list}
}
```

### 6.3 RouteResult

```python
{
    "success": bool,
    "route_id": str,
    "start_site_id": str,
    "end_site_id": str,
    "segments": list,
    "edge_ids": list[str],
    "geometry": {"type": "LineString", "coordinates": list},
    "total_length_m": float,
    "relative_cost": float,
    "forbidden_asset_ids_applied": list[str]
}
```

### 6.4 ValidationResult

```python
{
    "passed": bool,
    "violations": [
        {
            "rule_id": str,
            "type": str,
            "asset_id": str | None,
            "severity": "error",
            "message": str,
            "repair_hint": "forbid_asset" | None
        }
    ]
}
```

### 6.5 BOMResult

```python
{
    "total_length_m": float,
    "existing_duct_length_m": float,
    "new_build_length_m": float,
    "recommended_cable_length_m": float,
    "slack_ratio": 0.10,
    "used_edge_ids": list[str]
}
```

所有浮点输出保留两位小数。不要向调用方返回 Shapely 或 NetworkX 对象。

## 7. Demo 数据

`scripts/generate_demo_data.py` 使用固定 seed，并以稳定顺序写出 UTF-8 文件：

```text
data/demo/sites.geojson
data/demo/network.geojson
```

坐标固定为 WGS84 `[longitude, latitude]`。

数据必须满足：

- A 为 `telecom_room`，B 为 `base_station`，均绑定网络节点；
- 至少有两条 A 到 B 的路径；
- 第一次最低成本路径包含 D017；
- D017 的 `capacity_cores - used_cores < 24`；
- 替代路径不含 D017，成本更高但容量满足；
- 所有节点引用存在；
- `length_m > 0`、`cost_multiplier > 0`；
- LineString 至少两个坐标点；
- 连续运行生成器两次，文件内容一致。

不要为追求“真实”调用在线地图，也不要加入建筑、水域等非主 Case 图层。

## 8. 数据加载与健康检查

实现清晰的加载 API，例如：

```python
load_sites(path) -> mapping
load_network(path) -> graph_and_edge_records
```

加载阶段必须 fail closed，至少检查：

- GeoJSON 根类型为 `FeatureCollection`；
- Feature/edge ID 唯一；
- 必填字段存在且类型合理；
- `0 <= used_cores <= capacity_cores`；
- `from_node`、`to_node` 均存在；
- 坐标是有限数值并按 `[longitude, latitude]`；
- 起终点站点能绑定图节点；
- 不允许无提示跳过坏 Feature。

错误消息必须指出文件、Feature/edge ID 和失败字段。

## 9. 路由

对外函数：

```python
plan_route(task, network, forbidden_asset_ids, route_id) -> RouteResult
```

第一次调用使用 `route_id="R001"`，第二次使用 `route_id="R002"`；函数不得自行生成随机 ID。

权重固定为：

```text
relative_cost = length_m × cost_multiplier
```

建图时排除：

- `status == unavailable`；
- `edge_id` 在 `forbidden_asset_ids` 中。

第一次规划不得读取容量来排除 D017；容量由 Validator 独立检查。必须使用 NetworkX Dijkstra。同成本时使用稳定 tie-break，保证重复运行一致。P0 网络边均按双向可通行处理；反向经过一条边时，RouteSegment 中的坐标必须反转，保证整条 LineString 连续。

无路径时抛出带起终点和禁用资源列表的明确业务异常，不得返回假路线。

合并段坐标时去除相邻重复点，确保 LineString 从 A 连续到 B。每个 RouteSegment 必须保留真实 edge ID。

## 10. Validator

对外函数：

```python
validate_route(route, task, edge_records) -> ValidationResult
```

P0 只实现：

```text
R_ENDPOINT
R_ASSET_STATUS
R_CAPACITY
```

容量规则只应用于 `asset_type == "existing_duct"`；`new_build` 不使用已有管道容量字段。公式：

```text
capacity_cores - used_cores >= task.fiber_cores 才通过
```

D017 容量不足时必须返回：

```python
{
    "rule_id": "R_CAPACITY",
    "type": "duct_capacity",
    "asset_id": "D017",
    "severity": "error",
    "repair_hint": "forbid_asset"
}
```

Validator 不得自动重规划，只报告确定性事实。

## 11. BOM

对外函数：

```python
calculate_bom(route) -> BOMResult
```

固定计算：

```text
total_length_m = 所有 segment.length_m 之和
existing_duct_length_m = existing_duct 段长度之和
new_build_length_m = new_build 段长度之和
recommended_cable_length_m = total_length_m × 1.10
```

必须验证：

```text
existing_duct_length_m + new_build_length_m == total_length_m
```

允许两位小数舍入误差，不能吞掉实际不一致。

## 12. 单元测试必须证明

1. 固定数据可加载且 ID 唯一；
2. 坐标顺序和 LineString 基本结构有效；
3. 缺字段、坏节点引用、负长度明确失败；
4. `plan_route(..., [], "R001")` 的 edge IDs 包含 D017；
5. 第一次校核 FAIL，且指向 D017/R_CAPACITY；
6. `plan_route(..., ["D017"], "R002")` 不包含 D017；
7. 替代路线校核 PASS；
8. BOM 可从替代路线各段复算；
9. 禁用资源导致无路径时明确失败；
10. 生成脚本重复运行结果一致。

测试必须运行真实数据加载、NetworkX 路由和计算逻辑，不得 Mock 主链。

## 13. 实际验证

完成后执行：

```powershell
python scripts/generate_demo_data.py
python -m pytest tests/unit -q
python -m pytest -q
git diff --check
git status --short
```

再用真实调用或测试输出证明：

```text
first edge_ids 包含 D017
first validation passed=false
second edge_ids 不包含 D017
second validation passed=true
BOM 数值
```

不得把“文件已创建”或“测试已写”报告成运行成功。

## 14. 完成条件

只有以下条件全部满足才可报告完成：

- 允许范围内的代码和数据均已实现；
- 所有真实测试返回 0；
- 没有修改 Codex B 或文档所有权范围；
- 没有网络调用、API Key、本机绝对路径或 QGIS 运行依赖；
- 接口与总设计一致；
- `git diff --check` 无错误；
- `git status --short` 中的改动都能解释。

## 15. 给 Quimer 的交付报告

最终回复必须包含：

```text
1. 实际完成内容
2. 修改/新增文件清单
3. 实际执行命令及退出码
4. 第一次和第二次路线 edge_ids
5. 两次 ValidationResult 摘要
6. BOM 摘要
7. 测试通过数量
8. 未完成项或限制
9. Quimer 复验步骤
```

不要 push、合并 main、安装 QGIS、创建 GitHub 仓库或启动 P1；这些属于 Quimer。
