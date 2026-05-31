# 占用率预测模型系统化调参记录

本文档记录 OccuEVRoute 充电站占用率预测模型的一次系统化 XGBoost 超参数调参过程。文档面向项目组成员，重点说明本次为什么调参、如何切分数据、如何搜索参数、最终得到哪组参数，以及调参前后的指标变化。

## 1. 调参目的

当前占用率预测模型使用 `XGBRegressor` 预测未来多个时间点的充电站占用率：

```text
target_occupancy_rate = occupancy_rate(t + prediction_horizon_min)
```

调参前，主模型使用一组手工设置的经验参数：

```text
n_estimators = 500
max_depth = 5
learning_rate = 0.04
subsample = 0.85
colsample_bytree = 0.85
```

这组参数可以作为基础模型运行，但它不是通过系统化验证集搜索得到的。本次调参的目的，是在不改变特征工程的前提下，通过时间验证集选择更合适的 XGBoost 参数，并确认新参数在独立测试集上也优于基础参数。

## 2. 模型与特征范围

本次调参只针对当前主模型的 XGBoost 超参数，不改变模型输入特征。

使用的特征集为：

```text
horizon_context_lag_no_station_id
```

该特征集包含 52 个特征，覆盖：

- 预测 horizon 特征，例如 `prediction_horizon_min`、`horizon_sqrt`
- 当前时刻与目标时刻的时间特征
- 天气特征
- 站点静态属性
- 价格特征
- POI 周边环境特征
- 站点历史画像特征
- 邻近站点画像特征
- 占用率滞后与滚动统计特征

本次没有加入 `station_id` 作为模型特征，避免模型主要依赖站点编号记忆训练数据。

## 3. 数据切分与防泄漏设计

占用率预测具有时间序列属性，因此本次调参没有使用随机 K 折交叉验证，而是使用按时间顺序的三段式切分：

```text
train:      time < 2023-01-01T00:00:00
validation: 2023-01-01T00:00:00 <= time < 2023-01-23T19:05:00
test:       time >= 2023-01-23T19:05:00
```

实际样本量为：

```text
train rows:      485605
validation rows: 90631
test rows:       143764
```

参数选择只使用 validation 指标。test 数据没有参与任何参数选择，只用于最后比较基础参数和最佳参数的泛化效果。

本次调参沿用了主训练脚本中的防泄漏设计：

- 滞后特征和滚动统计特征只使用当前时刻之前的占用率。
- 站点历史画像、同小时画像和邻居画像只在训练段拟合，再应用到 validation 或 test。
- 目标值只来自 `time + prediction_horizon_min`。
- test 段不参与搜索空间调整、参数选择或阈值调整。

## 4. 调参方法

本次使用两阶段随机搜索，不引入 Optuna 等额外依赖。

第一阶段是宽范围随机搜索：

```text
stage1 trials = 80
```

第一阶段从完整参数空间中随机抽取 80 组候选参数，用 validation MAE 排序，找到表现较好的参数区域。

第二阶段是局部随机搜索：

```text
stage2 trials = 40
```

第二阶段围绕第一阶段 validation MAE 最好的前 5 组参数做邻域搜索，进一步寻找更优组合。

本次一共评估：

```text
baseline = 1
stage1 = 80
stage2 = 40
total = 121
```

主选择指标为：

```text
validation MAE
```

辅助观察指标为：

```text
validation R2
test MAE
test R2
by-horizon MAE
by-horizon R2
```

## 5. 搜索参数空间

第一阶段搜索空间如下：

```text
n_estimators:      300, 500, 800, 1200
max_depth:         3, 4, 5, 6, 8
learning_rate:     0.01, 0.02, 0.04, 0.06, 0.08
subsample:         0.70, 0.85, 1.00
colsample_bytree:  0.70, 0.85, 1.00
min_child_weight:  1, 3, 5, 10
reg_alpha:         0, 0.01, 0.1, 1.0
reg_lambda:        1, 3, 5, 10
```

第二阶段围绕第一阶段前 5 组参数生成局部候选，继续调整：

```text
n_estimators
max_depth
learning_rate
subsample
colsample_bytree
min_child_weight
reg_alpha
reg_lambda
```

## 6. 运行命令与输出文件

调参脚本为：

```text
src/waiting_prediction/tune_horizon_xgboost.py
```

正式运行命令为：

```text
python src/waiting_prediction/tune_horizon_xgboost.py --max-stations 0 --base-rows-per-station 1000 --max-rows-per-horizon 80000 --stage1-trials 80 --stage2-trials 40
```

本次调参输出文件为：

```text
docs/figures/occupancy_horizon_tuning_results.csv
docs/figures/occupancy_horizon_tuning_by_horizon.csv
docs/figures/occupancy_horizon_tuning_comparison.csv
models/occupancy_horizon_best_params.json
```

各文件含义：

- `occupancy_horizon_tuning_results.csv` 记录 baseline、stage1、stage2 每组参数的整体验证指标。
- `occupancy_horizon_tuning_by_horizon.csv` 记录不同 horizon 下的 MAE、relative MAE 和 R2。
- `occupancy_horizon_tuning_comparison.csv` 记录基础参数和最佳参数在 validation/test 上的对比。
- `occupancy_horizon_best_params.json` 保存本次选出的最佳参数和核心指标。

## 7. 最佳参数

本次最佳参数来自：

```text
stage = stage2
trial = 23
selection_metric = validation_mae
```

最佳参数为：

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

与基础参数相比，新参数使用了更深的树、更低的学习率、更强的叶子约束和更强的正则化。这个组合在 validation 上降低了 MAE，并在独立 test 上继续保持提升。

## 8. 结果对比

整体指标对比如下：

| 模型 | 数据段 | MAE | R2 |
| --- | --- | ---: | ---: |
| 基础参数 | validation | 0.030214 | 0.928110 |
| 最佳参数 | validation | 0.028780 | 0.930691 |
| 基础参数 | test | 0.024764 | 0.949001 |
| 最佳参数 | test | 0.023630 | 0.950328 |

指标变化：

```text
validation MAE: 0.030214 -> 0.028780
validation R2:  0.928110 -> 0.930691

test MAE:       0.024764 -> 0.023630
test R2:        0.949001 -> 0.950328
```

本次调参不是只在 validation 上变好；在没有参与参数选择的 test 数据上，MAE 和 R2 也同时改善。

## 9. 分 horizon 结果

test 集上的分 horizon 结果如下：

| Horizon 分钟 | 基础参数 MAE | 最佳参数 MAE | 基础参数 R2 | 最佳参数 R2 |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 0.013906 | 0.012120 | 0.979367 | 0.979899 |
| 10 | 0.015858 | 0.014011 | 0.973298 | 0.974463 |
| 15 | 0.016955 | 0.015285 | 0.970884 | 0.972057 |
| 20 | 0.018582 | 0.017188 | 0.965304 | 0.965748 |
| 30 | 0.021291 | 0.020154 | 0.960783 | 0.962081 |
| 45 | 0.024497 | 0.023855 | 0.954620 | 0.955161 |
| 60 | 0.029656 | 0.028933 | 0.937923 | 0.939031 |
| 90 | 0.038500 | 0.037842 | 0.910375 | 0.911768 |
| 120 | 0.043434 | 0.043075 | 0.889414 | 0.893680 |

从 5 分钟到 120 分钟，最佳参数在每个 horizon 上的 test MAE 都低于基础参数。长期 horizon 的误差没有因为调参而恶化，120 分钟预测的 R2 也从 `0.889414` 提升到 `0.893680`。

完整分 horizon 结果保存在：

```text
docs/figures/occupancy_horizon_tuning_by_horizon.csv
```

## 10. 结论

本次系统化调参有效。相比基础经验参数，最佳参数在 validation 和 test 上都降低了 MAE，同时提高了 R2；分 horizon 检查也显示短期和长期预测没有出现局部恶化。

最终选出的参数为：

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

本次调参完成后，项目已经使用最佳参数重新训练并覆盖当前模型文件：

```text
models/occupancy_horizon_xgboost.pkl
```

最终训练读取了：

```text
models/occupancy_horizon_best_params.json
```

重新生成了 `occupancy_horizon_xgboost.pkl`、`occupancy_horizon_features.json`、整体指标、分 horizon 指标和 SHAP 图。当前前端推荐流程通过后端加载模型时，会使用这次调参后的模型制品。
