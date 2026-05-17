# OccuEVRoute

智能电动车充电路线规划课程项目。

这个项目要做的是：给定起点、终点、车辆电量和用户偏好，系统综合考虑距离、电量、等待时间、电价和充电站约束，推荐一条更合适的充电路线。

## 目录结构

```text
OccuEVRoute/
├── app/              # 最后展示用的 Streamlit 界面
├── data/             # 小数据、样例数据、处理后的数据
├── docs/             # proposal、报告、PPT
├── ML/               # 已下载的 UrbanEV 原始大数据
├── models/           # 训练好的 XGBoost 模型
└── src/              # 核心代码
```

## src 里面怎么放

```text
src/
├── data_processing/      # 读数据、清洗数据、做特征
├── route_planning/       # BFS / UCS / A*、电量约束、路线规划
├── waiting_prediction/   # XGBoost 等待时间预测
└── utils/                # 通用小工具
```

## 推荐开发顺序

1. 先在 `src/route_planning/` 做一个 toy graph，把 BFS / UCS / A* 跑通。
2. 再在 `src/data_processing/` 读取 UrbanEV 站点数据，整理出 10-20 个候选站点。
3. 然后在 `src/waiting_prediction/` 训练 XGBoost，预测等待时间。
4. 最后在 `app/` 做 Streamlit 页面，把路线、站点、等待时间和算法对比展示出来。

大型数据暂时继续放在 `ML/Data/`，不用移动。
