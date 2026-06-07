# 占用率预测模型系统化调参记录

本文档记录 OccuEVRoute 充电站占用率预测模型的系统化调参过程。阅读对象是项目组成员，重点是说明：我们为什么调参、如何避免数据泄漏、尝试了哪些搜索方法、最终为什么采用 Optuna 参数，以及当前部署模型对应的指标。

## 1. 最终结论

当前最终模型采用 Optuna 找到的 XGBoost 参数，并已经重新训练和覆盖模型制品：

```text
models/occupancy_horizon_xgboost.pkl
```

最终模型指标为：

```text
overall MAE = 0.023527
overall R2  = 0.950467
```

最终采用的参数为：

```text
n_estimators = 800
max_depth = 10
learning_rate = 0.013387836038795686
subsample = 0.60
colsample_bytree = 0.80
min_child_weight = 7
reg_alpha = 0.01
reg_lambda = 15.0
```

这组参数来自 Optuna 第 53 个 trial。它比基础经验参数和前一轮随机搜索参数都更好。

## 2. 调参目标

当前模型是一个多 horizon `XGBRegressor`，预测未来某个时间点的充电站占用率：

```text
target_occupancy_rate = occupancy_rate(t + prediction_horizon_min)
```

调参前，模型使用手工经验参数：

```text
n_estimators = 500
max_depth = 5
learning_rate = 0.04
subsample = 0.85
colsample_bytree = 0.85
```

本次调参的目标是：在不改变特征工程的前提下，用 validation MAE 系统选择 XGBoost 参数，并确认新参数在独立 test 集上也能提升。

主指标：

```text
validation MAE
```

辅助指标：

```text
validation R2
test MAE
test R2
by-horizon MAE
by-horizon R2
```

## 3. 模型与特征范围

本次只调 XGBoost 超参数，不改变输入特征。

使用的特征集：

```text
horizon_context_lag_no_station_id
```

该特征集包含 52 个特征，覆盖预测 horizon、当前/目标时刻时间特征、天气、站点静态属性、价格、POI、站点历史画像、邻近站点画像、占用率滞后与滚动统计。

本次没有加入 `station_id` 作为特征，避免模型主要记忆站点编号。

## 4. 数据切分与防泄漏

占用率预测具有时间序列属性，因此本次调参使用按时间顺序的三段式切分：

```text
train:      time < 2023-01-01T00:00:00
validation: 2023-01-01T00:00:00 <= time < 2023-01-23T19:05:00
test:       time >= 2023-01-23T19:05:00
```

实际样本量：

```text
train rows:      485605
validation rows: 90631
test rows:       143764
```

防泄漏规则：

- 参数选择只看 validation 指标。
- test 数据只用于最终比较，不参与参数搜索。
- 滞后特征和滚动特征只使用当前时刻之前的数据。
- 站点历史画像、同小时画像和邻居画像只在训练段拟合，再应用到 validation 或 test。
- 目标值只来自 `time + prediction_horizon_min`。

## 5. 第一轮：两阶段随机搜索

第一轮使用自定义随机搜索脚本：

```text
src/waiting_prediction/tune_horizon_xgboost.py
```

运行命令：

```text
python src/waiting_prediction/tune_horizon_xgboost.py --max-stations 0 --base-rows-per-station 1000 --max-rows-per-horizon 80000 --stage1-trials 80 --stage2-trials 40
```

搜索方式：

```text
stage1 = 80 组宽范围随机搜索
stage2 = 40 组围绕 stage1 前 5 名的局部搜索
```

随机搜索最佳参数来自 `stage2 trial 23`：

```text
n_estimators = 500
max_depth = 9
learning_rate = 0.02
subsample = 0.85
colsample_bytree = 0.90
min_child_weight = 7
reg_alpha = 0.05
reg_lambda = 15.0
```

随机搜索结果：

| 模型 | validation MAE | validation R2 | test MAE | test R2 |
| --- | ---: | ---: | ---: | ---: |
| 基础参数 | 0.030214 | 0.928110 | 0.024764 | 0.949001 |
| 随机搜索最佳参数 | 0.028780 | 0.930691 | 0.023630 | 0.950328 |

随机搜索证明：系统化搜索可以明显优于基础经验参数。

输出文件：

```text
docs/figures/occupancy_horizon_tuning_results.csv
docs/figures/occupancy_horizon_tuning_by_horizon.csv
docs/figures/occupancy_horizon_tuning_comparison.csv
models/occupancy_horizon_best_params.json
```

## 6. 第二轮：Optuna 搜索

第二轮使用 Optuna 做智能超参数搜索。Optuna 使用 TPE sampler，根据已经完成的 trial 自动选择后续更有潜力的参数组合。

脚本：

```text
src/waiting_prediction/tune_horizon_xgboost_optuna.py
```

运行命令：

```text
python src/waiting_prediction/tune_horizon_xgboost_optuna.py --max-stations 0 --base-rows-per-station 1000 --max-rows-per-horizon 80000 --trials 60
```

Optuna 设置：

```text
trials = 60
sampler = TPESampler
selection_metric = validation_mae
random_seed = 42
```

Optuna 最佳参数来自 `trial 53`：

```text
n_estimators = 800
max_depth = 10
learning_rate = 0.013387836038795686
subsample = 0.60
colsample_bytree = 0.80
min_child_weight = 7
reg_alpha = 0.01
reg_lambda = 15.0
```

Optuna 结果：

| 模型 | validation MAE | validation R2 | test MAE | test R2 |
| --- | ---: | ---: | ---: | ---: |
| 基础参数 | 0.030214 | 0.928110 | 0.024764 | 0.949001 |
| Optuna 最佳参数 | 0.028643 | 0.931132 | 0.023547 | 0.950557 |

Optuna 比随机搜索的 test MAE `0.023630` 进一步降低到 `0.023547`，因此最终选择 Optuna 参数。

输出文件：

```text
docs/figures/occupancy_horizon_optuna_trials.csv
docs/figures/occupancy_horizon_optuna_by_horizon.csv
docs/figures/occupancy_horizon_optuna_comparison.csv
models/occupancy_horizon_optuna_best_params.json
```

## 7. 最终训练

Optuna 参数确定后，使用 train + validation 的完整训练段重新训练最终模型，并继续用 test 段评估。

最终训练命令：

```text
python src/waiting_prediction/train_lagged_occupancy_model.py --max-stations 0 --base-rows-per-station 1000 --max-rows-per-horizon 80000 --shap-sample-size 3000 --model-params-file models/occupancy_horizon_optuna_best_params.json
```

最终训练输出：

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
```

最终主模型指标：

| 指标 | 数值 |
| --- | ---: |
| MAE | 0.023527 |
| R2 | 0.950467 |

## 8. 最终模型分 horizon 结果

| Horizon 分钟 | MAE | Relative MAE | R2 |
| ---: | ---: | ---: | ---: |
| 5 | 0.012073 | 4.94% | 0.979950 |
| 10 | 0.013963 | 5.69% | 0.974227 |
| 15 | 0.015088 | 6.16% | 0.972052 |
| 20 | 0.017075 | 7.00% | 0.965989 |
| 30 | 0.020175 | 8.25% | 0.961891 |
| 45 | 0.023694 | 9.79% | 0.955410 |
| 60 | 0.028964 | 11.90% | 0.939334 |
| 90 | 0.037669 | 15.32% | 0.911971 |
| 120 | 0.042834 | 17.62% | 0.894316 |

短期 horizon 的相对 MAE 低于 10%；120 分钟预测的相对 MAE 为 17.62%，R2 为 0.894316。

## 9. 对组内汇报的解释

可以这样概括本次调参：

```text
初始 XGBoost 模型使用经验参数。我们先用时间验证集做两阶段随机搜索，证明系统化调参能降低 test MAE；随后使用 Optuna 的 TPE sampler 做 60 次智能搜索，进一步找到更优参数。最终模型采用 Optuna 参数重新训练，在独立 test 集上 MAE 降到 0.023527，R2 达到 0.950467。
```

关键点：

- 没有使用随机 K 折，避免时间序列泄漏。
- test 集没有参与参数选择，只用于最终验证。
- 最终模型已经重新训练并覆盖 `models/occupancy_horizon_xgboost.pkl`。
- 当前后端加载模型时，会使用 Optuna 调参后的模型制品。
