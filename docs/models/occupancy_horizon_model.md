# 任意未来时间点占用率预测模型说明

本文档说明当前项目中的充电站占用率预测模型。模型用于回答：

> 给定某个充电站在当前时刻的状态，以及一个未来时间差，例如 5 分钟、19 分钟或 120 分钟后，预测该站点在目标时刻的占用率。

## 1. 模型目标

当前模型预测的目标是：

```text
target_occupancy_rate = occupancy_rate(t + prediction_horizon_min)
```

其中：

- `t` 是当前时刻。
- `prediction_horizon_min` 是未来时间差，单位为分钟。
- `occupancy_rate = busy / (busy + idle)`。

模型第一版只预测站点占用率，不同时预测 `volume`、`duration` 或等待时间。

## 2. 模型形式

当前使用的是 XGBoost 回归模型：

```text
XGBRegressor
```

它不是为每个未来时间单独训练一个模型，而是训练一个单一的多 horizon 模型。也就是说，`prediction_horizon_min` 本身被作为输入特征之一。

因此模型学习的是：

```text
future_occupancy = f(current_state, station_context, target_time, prediction_horizon_min)
```

这种方式可以支持训练范围内的任意未来时间点预测。例如：

- 5 分钟后
- 7 分钟后
- 19 分钟后
- 120 分钟后

需要注意：原始数据是 5 分钟粒度，所以非 5 分钟整数倍的预测，例如 3.5 分钟或 19 分钟，是模型在训练范围内的连续估计，不是原始数据中直接观测到的标签。

## 3. 训练数据与时间切分

模型使用 UrbanEV 站点历史数据：

```text
ML/Data/UrbanEVDataset/UrbanEVDataset/20220901-20230228_station-processed/
```

当前全站点版本覆盖：

```text
站点数: 1423
horizon: 5, 10, 15, 20, 30, 45, 60, 90, 120 分钟
总样本数: 720000
训练样本: 576236
测试样本: 143764
```

时间切分如下：

```text
训练集: 2022-09-01 01:00:00 到 2023-01-23 18:25:00
测试集: 2023-01-23 22:45:00 到 2023-02-28 19:30:00
```

说明：全站点完整 5 分钟粒度展开会产生非常大的训练表。当前全站点版本采用“全站覆盖 + 时间均匀采样”的方式：

```text
每个站点按时间均匀采样 1000 个当前时刻
每个 horizon 最多保留 80000 行样本
```

这样既覆盖所有站点，又避免把训练表扩展到几千万行。

## 4. 使用的特征

当前主模型名称是：

```text
horizon_context_lag_no_station_id
```

它不使用 `station_id` 作为特征，避免模型主要记住站点编号。

### 4.1 Horizon 特征

```text
prediction_horizon_min
horizon_sqrt
```

### 4.2 当前时刻时间特征

```text
current_weekday
current_hour_sin
current_hour_cos
current_is_holiday
current_is_morning_peak
current_is_evening_peak
```

### 4.3 目标时刻时间特征

```text
target_weekday
target_hour_sin
target_hour_cos
target_is_holiday
target_is_morning_peak
target_is_evening_peak
```

### 4.4 天气特征

```text
temperature
humidity
rain
```

### 4.5 站点静态特征

```text
longitude
latitude
charge_count
TAZID
```

### 4.6 价格特征

```text
s_price
e_price
```

### 4.7 POI 周边特征

```text
poi_total_count
poi_lifestyle_services_count
poi_business_residential_count
poi_food_beverage_count
poi_lifestyle_ratio
poi_business_residential_ratio
poi_food_beverage_ratio
```

### 4.8 历史画像特征

```text
station_avg_occupancy
station_peak_avg_occupancy
station_avg_duration
station_same_hour_occupancy
global_same_hour_occupancy
```

这些特征只用训练集统计，再应用到测试集，避免使用未来信息。

### 4.9 邻居站点画像特征

```text
neighbor_count
neighbor_avg_distance_m
neighbor_avg_station_occupancy
neighbor_max_station_occupancy
neighbor_avg_peak_occupancy
neighbor_avg_duration
neighbor_avg_charge_count
neighbor_avg_same_hour_occupancy
neighbor_avg_same_weekday_hour_occupancy
```

### 4.10 短期动态特征

```text
occupancy_lag_1
occupancy_lag_3
occupancy_lag_6
occupancy_lag_12
occupancy_rolling_mean_6
occupancy_rolling_mean_12
occupancy_rolling_std_12
occupancy_trend_12
```

这些特征全部只使用当前时刻 `t` 之前的数据。

## 5. 无数据泄漏设计

模型避免数据泄漏的关键规则如下：

1. 标签使用未来值：

```text
target_occupancy_rate = occupancy_rate(t + horizon)
```

2. 输入特征中的 lag 和 rolling 只使用 `t` 及之前的数据。

3. 历史画像和邻居画像只在训练集上统计，再映射到测试集。

4. 不把目标时刻 `t + horizon` 附近的真实占用状态作为输入。

因此，模型在测试集预测时只能看到当前时刻及历史信息，而不能看到未来真实占用率。

## 6. 当前训练结果

全站点版本整体结果：

```text
overall R2  = 0.950467
overall MAE = 0.023527
```

按 horizon 的结果：

| Horizon | MAE | Relative MAE | R2 |
|---:|---:|---:|---:|
| 5 min | 0.0121 | 4.94% | 0.9800 |
| 10 min | 0.0140 | 5.69% | 0.9742 |
| 15 min | 0.0151 | 6.16% | 0.9721 |
| 20 min | 0.0171 | 7.00% | 0.9660 |
| 30 min | 0.0202 | 8.25% | 0.9619 |
| 45 min | 0.0237 | 9.79% | 0.9554 |
| 60 min | 0.0290 | 11.90% | 0.9393 |
| 90 min | 0.0377 | 15.32% | 0.9120 |
| 120 min | 0.0428 | 17.62% | 0.8943 |

其中：

```text
Relative MAE = MAE / target_mean
```

短期预测相对误差低于 10%，长期预测相对误差低于 30%，说明当前模型在课程项目和演示场景中表现较好。

## 7. 特征交互分析

本次对最终 Optuna 模型做了 SHAP interaction 分析。分析使用测试集样本计算特征两两交互强度，数值越大表示这两个特征组合对预测的额外贡献越明显。

最强的交互主要集中在短期历史占用率特征之间：

| 排名 | 特征 A | 特征 B | Mean absolute interaction |
|---:|---|---|---:|
| 1 | `occupancy_lag_1` | `occupancy_rolling_mean_6` | 0.020095 |
| 2 | `occupancy_lag_1` | `occupancy_rolling_mean_12` | 0.006272 |
| 3 | `occupancy_lag_1` | `occupancy_lag_3` | 0.004074 |
| 4 | `station_same_hour_occupancy` | `occupancy_lag_1` | 0.002996 |
| 5 | `occupancy_rolling_mean_6` | `occupancy_rolling_mean_12` | 0.002574 |

这说明模型最主要学习的是“当前/短期历史占用率状态如何共同决定未来占用率”。同时，`prediction_horizon_min x occupancy_lag_1` 也进入前 10，说明模型会根据预测时间距离调整当前占用率对未来的影响。

特征交互分析结果输出在：

```text
docs/figures/occupancy_horizon_shap_interactions.csv
docs/figures/occupancy_horizon_top_interactions.png
docs/figures/occupancy_horizon_interaction_pdp_lag_horizon.csv
docs/figures/occupancy_horizon_interaction_pdp_lag_horizon.png
```

其中 `occupancy_horizon_interaction_pdp_lag_horizon.png` 展示了 `occupancy_lag_1` 与 `prediction_horizon_min` 的二维 partial dependence，用于观察当前占用率和预测 horizon 如何共同影响未来占用率。

## 8. 结果文件

模型和评估结果输出在：

```text
models/occupancy_horizon_xgboost.pkl
models/occupancy_horizon_features.json
docs/figures/occupancy_horizon_model_metrics.csv
docs/figures/occupancy_horizon_by_horizon_metrics.csv
docs/figures/occupancy_horizon_feature_set_metrics.csv
docs/figures/occupancy_horizon_feature_importance.csv
docs/figures/occupancy_horizon_shap_importance.csv
docs/figures/occupancy_horizon_shap_bar.png
docs/figures/occupancy_horizon_shap_summary.png
docs/figures/occupancy_horizon_shap_interactions.csv
docs/figures/occupancy_horizon_top_interactions.png
docs/figures/occupancy_horizon_interaction_pdp_lag_horizon.csv
docs/figures/occupancy_horizon_interaction_pdp_lag_horizon.png
```

## 9. 运行方式

默认训练 100 个站点：

```powershell
python src/waiting_prediction/train_lagged_occupancy_model.py
```

训练全站点采样版：

```powershell
python src/waiting_prediction/train_lagged_occupancy_model.py --max-stations 0 --base-rows-per-station 1000 --max-rows-per-horizon 80000 --shap-sample-size 3000 --model-params-file models/occupancy_horizon_optuna_best_params.json
```

其中：

- `--max-stations 0` 表示不限制站点数，即使用全部站点。
- `--base-rows-per-station 1000` 表示每个站点按时间均匀采样 1000 个当前时刻。
- `--max-rows-per-horizon 80000` 表示每个 horizon 最多保留 80000 行。
- `--model-params-file models/occupancy_horizon_optuna_best_params.json` 表示使用 Optuna 调参得到的最佳 XGBoost 参数。

运行特征交互分析：

```powershell
python src/waiting_prediction/analyze_horizon_feature_interactions.py --max-stations 0 --base-rows-per-station 1000 --max-rows-per-horizon 80000 --shap-sample-size 500 --pdp-sample-size 3000 --top-n 50
```

## 10. 局限性

1. 原始数据是 5 分钟粒度，非 5 分钟整数倍预测属于模型连续估计。

2. 120 分钟以外的预测没有作为当前模型的训练目标，不建议直接用于推荐决策。

3. 当前第一版只预测占用率，还没有同时预测流量、等待时间或快慢充分别占用率。

4. 模型虽然可以预测未来占用率，但线上推荐系统是否接入该模型，需要另行在 backend 中加载模型并构造实时特征。

## 11. 一句话总结

当前模型是一个支持任意未来时间点输入的多 horizon XGBoost 占用率预测模型。它使用当前状态、短期历史、站点环境、时间、天气、价格、POI 和邻居站点画像来预测 `0-120` 分钟内的未来占用率；在全站点采样测试中，整体 `R2` 约为 `0.950`，短期相对误差低于 `10%`，120 分钟相对误差约为 `17.6%`。
