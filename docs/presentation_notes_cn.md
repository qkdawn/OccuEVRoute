# OccuEVRoute 项目 PPT 讲解稿（中文）

> 本文档对应 PPT 的六个模块：Introduction、Problem Definition、Dataset、Search Strategy、Machine Learning、Performance。  
> 每节均包含：原理说明、关键代码路径、可直接引用的代码片段，适合作为演讲备注或幻灯片正文。

---

## 一、Introduction（项目简介）

### 1.1 项目是什么

OccuEVRoute 是一个**智能电动汽车充电路线规划系统**。它的核心功能是：给定用户当前位置、车辆电量状态（SOC）和行驶约束，系统自动推荐最合适的充电站及前往路线。

系统将三个子问题合为一体：

| 子问题 | 解决方法 |
|--------|----------|
| 从哪条路走最快？ | 路网图搜索（BFS / UCS / A*） |
| 电量够不够跑到那里？ | 约束可行性检查（CSP） |
| 到了还能充上电吗？ | XGBoost 占用率预测 |

### 1.2 系统整体流程

```
用户输入（位置 + 电量 + 约束）
        ↓
候选站点筛选（半径内的充电站）
        ↓
前置约束过滤（pre_csp_check）：去掉明显不可行的站点
        ↓
路网搜索（BFS / UCS / A*）：找出到每个候选站点的最短时间路径
        ↓
后置约束验证（post_csp_check）：检查电量、时间、到达 SOC
        ↓
XGBoost 预测占用率：为可行站点附加预测等待信息
        ↓
返回前 K 个推荐结果（按行驶时间排序）
```

### 1.3 代码入口

```
src/route_planning/recommender.py   ← 系统总入口
backend/main.py                      ← FastAPI 后端 API
frontend/                            ← React + Leaflet 前端地图
```

主函数调用链：
```python
# src/route_planning/recommender.py（第 17-103 行）
def recommend_charging_stations(user_latitude, user_longitude, algorithm="astar", ...):
    candidates = select_nearby_stations(...)        # 1. 候选筛选
    for station in candidates:
        pre_ok, pre_reason = pre_csp_check(...)    # 2. 前置过滤
        search = run_search(...)                    # 3. 路网搜索
        post_ok, post_reason, arrival_soc = post_csp_check(...)  # 4. 后置验证
    return feasible  # 5. 后端合并 ML 占用率后按用户选择的 ranking metric 排序
```

---

## 二、Problem Definition（问题定义）

### 2.1 问题背景

电动汽车（EV）充电规划面临多重挑战：
- **路网复杂**：城市路网有成千上万个节点，不能逐一枚举
- **电量有限**：必须保证到达充电站时 SOC 不低于安全下限
- **时间敏感**：充电站可能已满员，找到一个"能用的"站点比找到最近的更重要
- **多目标权衡**：同时优化行驶时间、行驶距离、到达电量、充电桩占用率

### 2.2 约束定义

系统将可行性约束分为两类，对应代码中的两个函数：

**前置约束（搜索前）**——`src/route_planning/constraints.py`：
```python
def pre_csp_check(station, constraints):
    # 1. 站点直线距离是否超出搜索半径
    if float(station["straight_line_distance_km"]) > constraints.max_search_radius_km:
        return False, "outside_search_radius"
    # 2. 充电桩数量是否足够
    if int(station["charge_count"]) < constraints.min_charge_count:
        return False, "too_few_chargers"
    # 3. 站点到道路的投影距离是否太远
    if float(station["road_snap_distance_m"]) > constraints.max_road_snap_distance_m:
        return False, "road_snap_distance_too_far"
    return True, ""
```

**后置约束（搜索后）**——同文件：
```python
def post_csp_check(path_found, distance_km, drive_time_min, constraints):
    if not path_found:
        return False, "path_not_found", None
    if drive_time_min > constraints.max_drive_time_min:
        return False, "drive_time_exceeds_limit", None
    energy_needed_kwh = distance_km * constraints.consumption_kwh_per_km
    if energy_needed_kwh > available_energy_kwh:
        return False, "insufficient_energy", None
    arrival_soc = (available_energy_kwh - energy_needed_kwh) / battery_capacity_kwh
    if arrival_soc < constraints.min_arrival_soc:
        return False, "arrival_soc_below_safety_threshold", arrival_soc
    return True, "", arrival_soc
```

### 2.3 设计思路

- **两阶段过滤**：先用静态属性快速剪枝（不跑搜索），再用路网结果精确验证，节省大量计算。
- **成本函数**：搜索主代价是**行驶时间（分钟）**，而不是距离或金钱，因为用户最关心"多久能充上电"。
- **最终排序**：后端先合并 ML occupancy prediction，再对通过 post-check 的可行站点做多字段排序。默认 balanced score 是 `drive_time_min / max_drive_time_min + predicted_occupancy_rate`，分数越低越靠前；其中 drive time 先按用户设置的最大行驶时间归一化，occupancy 只作为拥挤风险信号，不表示等待时间。也可以切换为最短行驶时间、最短距离、最低预测占用率或最高到达 SOC。代码实现调用 pandas `sort_values`。

---

## 三、Dataset（数据集）

### 3.1 数据来源

项目使用的数据分为两大类：

| 数据类型 | 来源 | 存放位置 |
|----------|------|----------|
| 充电站历史占用率（时序） | UrbanEV 深圳公开数据集 | `ML/Data/UrbanEVDataset/` |
| 天气数据（温度/湿度/降雨） | UrbanEV 配套天气文件 | `ML/Data/UrbanEVSupplemental/` |
| 路网图（深圳可行驶路网） | OSMnx 下载 + 处理 | `data/processed/*.graphml` |
| 兴趣点（POI）特征 | 深圳 POI 数据聚合 | `data/processed/station_poi_features.csv` |
| Landmark 距离表（A* 启发） | 离线预计算 16 个 Landmark | `data/processed/landmark_distances.npz` |

### 3.2 数据规模

- **时间跨度**：2022-09-01 至 2023-02-28（约 6 个月）
- **充电站数量**：1,423 个深圳充电站
- **样本行数**：约 355,750 条（每站每 5 分钟一条记录）
- **天气粒度**：5 分钟级，与充电站记录对齐合并

### 3.3 占用率特征生成

每一行样本 = 某站点某时刻的状态，包含：

**静态特征**（来自站点基本信息）：
```python
# src/waiting_prediction/run_occupancy_poi_experiment.py（第 30-55 行）
BASE_FEATURES = [
    "station_id",           # 站点编号（分类编码）
    "weekday", "hour",      # 时间特征
    "is_holiday",           # 是否节假日
    "temperature", "humidity", "rain",  # 天气
    "charge_count",         # 充电桩总数
    "s_price", "e_price",   # 服务费 / 电费
    "station_avg_occupancy",  # 站点历史平均占用率（静态画像）
    "station_avg_duration",   # 平均充电时长
]
POI_COUNT_FEATURES = [
    "poi_total_count",                    # 周边总 POI 数量
    "poi_lifestyle_services_count",        # 生活服务类 POI
    "poi_business_residential_count",      # 商业/住宅类 POI
    "poi_food_beverage_count",             # 餐饮类 POI
]
```

**动态 Lag 特征**（来自历史时序，仅使用 `shift(1)` 保证无泄露）：
```python
# src/waiting_prediction/train_lagged_occupancy_model.py（第 52-61 行）
LAG_FEATURES = [
    "occupancy_lag_1",           # 上一时刻（5 分钟前）占用率
    "occupancy_lag_3",           # 15 分钟前
    "occupancy_lag_6",           # 30 分钟前
    "occupancy_lag_12",          # 1 小时前
    "occupancy_rolling_mean_6",  # 过去 30 分钟滑动均值
    "occupancy_rolling_mean_12", # 过去 1 小时滑动均值
    "occupancy_rolling_std_12",  # 过去 1 小时滑动标准差
    "occupancy_trend_12",        # 趋势：lag_1 - lag_12
]
```

### 3.4 数据如何传入 XGBoost

不是时序张量，而是**展开成二维表格**：
- 每行 = 一个站点一个时刻的样本
- 每列 = 一个特征
- 标签 = `occupancy_rate`（= 忙碌桩数 / 总桩数）

```python
# 训练调用示例（train_lagged_occupancy_model.py 第 193 行）
model.fit(train_df[features], train_df["occupancy_rate"])
```

### 3.5 路网数据处理

```
python src/data_processing/download_road_network_tiles.py   # OSMnx 下载深圳路网
python src/data_processing/build_station_graph.py           # 将充电站投影到最近道路边
python src/data_processing/build_station_poi_features.py    # 计算各站点周边 POI 特征
python src/data_processing/build_landmark_distances.py      # 预计算 16 个 Landmark 到所有节点的距离
```

---

## 四、Search Strategy（搜索策略）

### 4.1 三种算法概述

系统在深圳路网图上实现了三种搜索算法，统一定义于 `src/route_planning/search_algorithms.py`。

#### BFS（广度优先搜索）
- **原理**：像水波一样逐层扩展，先找跳数最少的路径。
- **特点**：不考虑边的权重（时间/距离），在无权图中保证找到跳数最少的路径，但**不保证时间最短**。
- **代码**（第 152-172 行）：
```python
def bfs_search(graph, start, goal):
    queue = deque([start])          # 用队列（FIFO）扩展
    visited = {start}
    while queue:
        node = queue.popleft()
        if node == goal:
            return _success("bfs", graph, _reconstruct_path(parent, goal), ...)
        for neighbor in graph.successors(node):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
```

#### UCS（均匀代价搜索）
- **原理**：用优先队列按**累计代价**扩展，总是先处理当前已知最便宜的节点。
- **特点**：代价 = 累计行驶时间（分钟），**保证找到时间最短路径**，但不使用启发式，扩展节点较多。
- **代码**（第 175-199 行）：
```python
def ucs_search(graph, start, goal):
    heap = [(0.0, start)]           # 最小堆，(累计时间, 节点)
    best_cost = {start: 0.0}
    while heap:
        cost, node = heapq.heappop(heap)
        if node == goal:
            return _success(...)
        for neighbor in graph.successors(node):
            _, travel_time_s = _edge_metrics(graph, node, neighbor)
            new_cost = cost + travel_time_s / 60   # 代价单位：分钟
            if new_cost < best_cost.get(neighbor, float("inf")):
                best_cost[neighbor] = new_cost
                heapq.heappush(heap, (new_cost, neighbor))
```

#### A*（启发式搜索）
- **原理**：在 UCS 基础上加入**启发函数 h(n)**，即当前节点到目标的预估剩余代价。优先队列排序键为 `f(n) = g(n) + h(n)`，其中 `g(n)` 是已知代价，`h(n)` 是预估值。
- **特点**：只要启发函数不高估实际代价（admissible），就**保证找到最优解**，且扩展节点数远少于 UCS。
- **启发函数**：优先使用 ALT（Landmark 三角不等式）；若 Landmark 表缺失则回退到直线距离启发。
- **代码**（第 202-232 行）：
```python
def astar_search(graph, start, goal, landmark_heuristic=None):
    heap = [(_heuristic_minutes(graph, start, goal, landmark_heuristic), 0.0, start)]
    while heap:
        _, cost, node = heapq.heappop(heap)
        if node == goal:
            return _success(...)
        for neighbor in graph.successors(node):
            _, travel_time_s = _edge_metrics(graph, node, neighbor)
            new_cost = cost + travel_time_s / 60
            if new_cost < best_cost.get(neighbor, float("inf")):
                priority = new_cost + _heuristic_minutes(graph, neighbor, goal, ...)
                heapq.heappush(heap, (priority, new_cost, neighbor))
```

### 4.2 ALT 启发函数（Landmark + Triangle Inequality）

A* 的关键优化：预先计算 **16 个 Landmark 节点**到全图所有节点的最短时间，存为 `landmark_distances.npz`。查询时用三角不等式得到下界估计：

```python
# src/route_planning/landmark_heuristic.py（第 45-70 行）
def estimate_minutes(self, node, goal):
    # 对每个 Landmark L：
    # h(node→goal) ≥ dist(L→goal) - dist(L→node)   [正向]
    # h(node→goal) ≥ dist(node→L) - dist(goal→L)   [反向]
    estimates = forward_goal[valid] - forward_node[valid]      # 正向估计
    estimates += reverse_node[valid] - reverse_goal[valid]     # 反向估计
    return max(0.0, float(np.max(np.concatenate(estimates))))  # 取最大下界
```

### 4.3 三算法对比

| 算法 | 最优性 | 扩展节点数 | 使用场景 |
|------|--------|------------|----------|
| BFS | 跳数最少 | 多（层层展开） | 对比基线 |
| UCS | 时间最短 ✓ | 较多 | 不需启发时的保底选择 |
| A* | 时间最短 ✓ | 少（ALT 启发大幅剪枝） | **默认推荐算法** |

### 4.4 路径代价计算

搜索完成后，`_path_metrics()` 沿路径累加每条边的实际属性值，得到最终输出：
```python
# search_algorithms.py（第 98-105 行）
def _path_metrics(graph, path):
    for u, v in zip(path, path[1:]):
        length_m, travel_time_s = _edge_metrics(graph, u, v)
        total_length_m += length_m
        total_time_s += travel_time_s
    return total_length_m / 1000, total_time_s / 60  # 返回 km 和 分钟
```

---

## 五、Machine Learning（机器学习）

### 5.1 XGBoost 是什么

**XGBoost**（Extreme Gradient Boosting，极端梯度提升）是一种基于**决策树集成**的机器学习算法。

**通俗解释**：
1. 先训练一棵简单的决策树（第 1 棵），它能大致预测占用率，但误差较大。
2. 第 2 棵树专门学习第 1 棵树的**残差（错误部分）**，补充修正。
3. 第 3、4、……棵树逐步修正前面所有树留下的误差。
4. 最终预测 = 所有树的输出之和（加权叠加）。

**为什么选 XGBoost**：
- 输入是表格特征，不需要时序神经网络的复杂架构
- 训练速度快、可解释性强（支持 SHAP 特征重要性分析）
- 对混合类型特征（数值 + 类别编码）效果好
- 已在工业界大量验证，超参数调节成熟

### 5.2 模型配置

```python
# src/waiting_prediction/train_lagged_occupancy_model.py（第 170-180 行）
def make_model(random_seed):
    return XGBRegressor(
        objective="reg:squarederror",  # 回归任务，最小化均方误差
        n_estimators=500,              # 树的棵数（500 轮迭代）
        max_depth=5,                   # 每棵树最大深度（控制复杂度）
        learning_rate=0.04,            # 学习率（步长，防止过拟合）
        subsample=0.85,                # 每轮随机采样 85% 的样本
        colsample_bytree=0.85,         # 每棵树随机采样 85% 的特征
        random_state=random_seed,
        n_jobs=-1,                     # 并行训练
    )
```

### 5.3 训练目标

**预测目标**：`occupancy_rate = busy_chargers / total_chargers`  
- 值域 [0, 1]，0 表示完全空闲，1 表示全部占用。
- 用于在推荐结果中告知用户"到站时预计有多少桩可用"。

### 5.4 特征工程核心：Lag 特征

Lag 特征是历史时序自回归的关键——用**过去状态预测未来状态**：

```python
# src/waiting_prediction/train_lagged_occupancy_model.py（第 132-145 行）
def add_lagged_features(df):
    grouped = df.groupby("station_id")["occupancy_rate"]
    df["occupancy_lag_1"]  = grouped.shift(1)   # 5 分钟前的占用率
    df["occupancy_lag_3"]  = grouped.shift(3)   # 15 分钟前
    df["occupancy_lag_6"]  = grouped.shift(6)   # 30 分钟前
    df["occupancy_lag_12"] = grouped.shift(12)  # 1 小时前
    df["occupancy_rolling_mean_6"]  = ...       # 过去 30 分钟均值
    df["occupancy_rolling_mean_12"] = ...       # 过去 1 小时均值
    df["occupancy_rolling_std_12"]  = ...       # 过去 1 小时波动
    df["occupancy_trend_12"] = df["occupancy_lag_1"] - df["occupancy_lag_12"]  # 趋势
    # 注：所有 lag 均使用 shift(1)，即每行只看"之前"的记录，无未来泄露
```

### 5.5 训练 / 测试拆分策略

使用**时间顺序拆分**（而不是随机拆分），确保模型不会用"未来数据"预测"过去"：

```python
# src/waiting_prediction/train_lagged_occupancy_model.py（第 162-167 行）
def time_split(df, cutoff_time):
    train_df = df[df["time"] < cutoff_time]   # 2022-09-01 ~ 2023-01-23 为训练集
    test_df  = df[df["time"] >= cutoff_time]  # 2023-01-23 之后为测试集
    return train_df, test_df
```

### 5.6 多组特征集消融实验

代码对多组特征组合进行了系统的消融实验，比较各组合的 MAE 和 R²：

```python
FEATURE_SETS = {
    "base":         BASE_FEATURES,            # 仅静态 + 时间 + 天气
    "lag_only":     LAG_FEATURES,             # 仅历史 lag 特征
    "base_lag":     [*BASE_FEATURES, *LAG_FEATURES],  # 全量特征
    "compact_lag":  [...精简版特征组合...],
    "history_core": [...核心历史特征...],
}
```

---

## 六、Performance（性能评估）

### 6.1 占用率预测模型性能

以下数据均来自代码实际运行输出文件（`docs/figures/`）。

#### 基线模型（静态特征 + 时间 + 天气 + 站点画像）
来源：`docs/figures/shap_model_metrics.csv`
| 指标 | 值 |
|------|----|
| MAE | **0.1217** |
| R² | **0.563** |
| 样本数 | 355,750 |
| 站点数 | 1,423 |

#### 加入 Lag 特征后（`lag_only` 特征组，100 站测试）
来源：`docs/figures/lagged_feature_test_100/occupancy_lagged_feature_set_metrics.csv`
| 特征组 | MAE | R² |
|--------|-----|----|
| `lag_only`（8 个历史 lag 特征） | **0.0101** | **0.986** |
| `history_core`（7 个核心历史特征） | 0.0118 | 0.985 |
| `base_lag`（静态 + lag 全量，24 特征） | 0.0121 | 0.984 |
| `compact_lag`（精简版，16 特征） | 0.0127 | 0.984 |
| `base`（仅静态，无 lag） | 0.1268 | 0.548 |

> **结论**：加入历史 Lag 特征后，R² 从约 0.55 跃升至 **0.986**，MAE 从 0.12 降至 **0.01**，说明过去 1 小时的时序状态是预测占用率的最关键信息。

#### POI 特征消融（时间拆分 80/20）
来源：`docs/figures/occupancy_poi_ablation_metrics.csv`
| 模型 | MAE | R² |
|------|-----|----|
| baseline（无 POI） | 0.1291 | 0.507 |
| baseline_poi_counts（加 POI 数量） | 0.1286 | 0.510 |
| baseline_poi_counts_ratios（加 POI 比例） | 0.1286 | 0.510 |
| weak（去掉站点历史画像） | 0.1828 | 0.194 |

> **结论**：POI 特征对时间拆分场景带来约 +0.3% R² 的小幅提升；站点历史画像（`station_avg_occupancy`）对模型影响最大，去掉后 R² 下降至 0.19。

#### 跨站泛化测试（Station Holdout 80/20）
| 模型 | MAE | R² |
|------|-----|----|
| baseline | 0.2127 | 0.013 |
| baseline_poi_counts_ratios | 0.2118 | 0.014 |

> **结论**：当测试站点为训练中从未见过的新站点时，R² 接近 0，说明模型高度依赖站点历史画像特征；对未知新站点的泛化能力仍待提升。

### 6.2 搜索算法性能对比

**定性对比**（基于代码逻辑分析）：

| 算法 | 扩展节点数 | 搜索质量 | 适用场景 |
|------|------------|----------|----------|
| BFS | 最多（层层展开，不剪枝） | 跳数最少，不保证时间最优 | 对比基线 |
| UCS | 较多（无启发，逐代价扩展） | 时间最短 ✓ | 无 Landmark 时的备用 |
| A* + ALT | 最少（启发剪枝大量节点） | 时间最短 ✓ | **默认，推荐使用** |

每次搜索的运行时间记录在 `SearchResult.runtime_seconds` 字段，可在前端可视化中查看展开节点轨迹（`expanded_trace_coordinates`）。

### 6.3 SHAP 特征重要性可视化

代码生成了 SHAP（Shapley Additive Explanations）图，存于 `docs/figures/shap_summary.png` 和 `shap_feature_importance.png`，直观展示每个特征对模型输出的贡献方向和大小。

最重要的特征（来自 `docs/figures/shap_feature_importance.csv`）通常为：
- `station_avg_occupancy`（站点历史均值）
- `occupancy_lag_1`（5 分钟前实时状态）
- `hour`（时段）
- `station_id`（站点编码）

---

## 附录：关键文件速查表

| 功能 | 文件路径 |
|------|----------|
| 路网搜索（BFS/UCS/A*） | `src/route_planning/search_algorithms.py` |
| 约束检查（CSP） | `src/route_planning/constraints.py` |
| 推荐主逻辑 | `src/route_planning/recommender.py` |
| ALT Landmark 启发 | `src/route_planning/landmark_heuristic.py` |
| 候选站点筛选 | `src/route_planning/candidate_selector.py` |
| 路网图加载 | `src/route_planning/graph_loader.py` |
| XGBoost 基础训练 | `src/waiting_prediction/plot_shap_occupancy.py` |
| Lag 特征训练 | `src/waiting_prediction/train_lagged_occupancy_model.py` |
| POI 消融实验 | `src/waiting_prediction/run_occupancy_poi_experiment.py` |
| 特征优化 | `src/waiting_prediction/optimize_occupancy_features.py` |
| 路网下载 | `src/data_processing/download_road_network_tiles.py` |
| 站点图构建 | `src/data_processing/build_station_graph.py` |
| POI 特征生成 | `src/data_processing/build_station_poi_features.py` |
| Landmark 距离预计算 | `src/data_processing/build_landmark_distances.py` |
| FastAPI 后端 | `backend/main.py` |
| React 前端 | `frontend/src/` |
