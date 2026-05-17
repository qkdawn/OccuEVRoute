# src

核心代码放这里。

```text
src/
├── data_processing/      # 数据读取、清洗、特征整理
├── route_planning/       # 路线规划算法和电量约束
├── waiting_prediction/   # 等待时间预测模型
└── utils/                # 通用函数
```

建议先从 `route_planning` 开始，因为 BFS / UCS / A* 是这个项目最核心、也最容易先展示出来的部分。
