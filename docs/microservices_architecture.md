# OccuEVRoute 微服务架构图

下图展示 OccuEVRoute 的逻辑微服务架构。当前默认部署为本地 FastAPI 后端加 Vite 前端预览服务，后端内部再按领域拆分为 API 编排、路线规划、占用率预测、地理数据与离线数据/模型制品服务边界。

<div style="width: 1200px; box-sizing: border-box; position: relative; background: #fafbfc; padding: 20px; border-radius: 6px; border: 1px solid #e5e7eb;">
  <style scoped>
    .arch-wrapper { display: flex; gap: 12px; }.arch-sidebar { width: 178px; flex-shrink: 0; }.arch-main { flex: 1; min-width: 0; }.arch-title { text-align: center; font-size: 22px; font-weight: bold; color: #1f2937; margin-bottom: 16px; }.arch-subtitle { text-align: center; font-size: 12px; color: #6b7280; margin-top: -10px; margin-bottom: 14px; }
    .arch-layer { margin: 8px 0; padding: 14px; border-radius: 6px; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04); }.arch-layer-title { font-size: 13px; font-weight: bold; margin-bottom: 10px; text-align: center; }
    .arch-grid { display: grid; gap: 8px; }.arch-grid-2 { grid-template-columns: repeat(2, 1fr); }.arch-grid-3 { grid-template-columns: repeat(3, 1fr); }.arch-grid-4 { grid-template-columns: repeat(4, 1fr); }.arch-grid-5 { grid-template-columns: repeat(5, 1fr); }.arch-grid-6 { grid-template-columns: repeat(6, 1fr); }
    .arch-box { border-radius: 4px; padding: 8px; text-align: center; font-size: 11px; font-weight: 600; line-height: 1.35; color: #1f2937; background: #ffffff; border: 1px solid #e5e7eb; }.arch-box.highlight { background: #f3f4f6; border: 2px solid #6b7280; }.arch-box.tech { font-size: 10px; color: #4b5563; background: #f9fafb; }.arch-box.external { border-style: dashed; }
    .arch-layer.external { background: linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%); border: 1px dashed #d1d5db; }.arch-layer.external .arch-layer-title { color: #6b7280; }.arch-layer.user { background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%); border: 2px solid #3b82f6; }.arch-layer.user .arch-layer-title { color: #1d4ed8; }.arch-layer.application { background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%); border: 2px solid #d97706; }.arch-layer.application .arch-layer-title { color: #92400e; }.arch-layer.ai { background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); border: 2px solid #16a34a; }.arch-layer.ai .arch-layer-title { color: #15803d; }.arch-layer.data { background: linear-gradient(135deg, #fdf2f8 0%, #fce7f3 100%); border: 2px solid #db2777; }.arch-layer.data .arch-layer-title { color: #9d174d; }.arch-layer.infra { background: linear-gradient(135deg, #f3f4f6 0%, #e5e7eb 100%); border: 2px solid #6b7280; }.arch-layer.infra .arch-layer-title { color: #374151; }
    .arch-sidebar-panel { border-radius: 6px; padding: 10px; background: linear-gradient(135deg, #f3f4f6 0%, #e5e7eb 100%); border: 1px solid #d1d5db; margin-bottom: 8px; }.arch-sidebar-title { font-size: 12px; font-weight: bold; text-align: center; color: #1f2937; margin-bottom: 6px; }.arch-sidebar-item { font-size: 10px; text-align: center; color: #374151; background: #ffffff; padding: 5px; border-radius: 3px; margin: 3px 0; border: 1px solid #e5e7eb; }.arch-sidebar-item.metric { background: #f3f4f6; border: 1px solid #9ca3af; color: #1f2937; font-weight: 600; }
    .arch-subgroup { display: flex; gap: 8px; margin-top: 8px; }.arch-subgroup-box { flex: 1; border-radius: 6px; padding: 8px; background: rgba(255, 255, 255, 0.55); border: 1px solid rgba(0, 0, 0, 0.08); }.arch-subgroup-title { font-size: 10px; font-weight: bold; color: #374151; text-align: center; margin-bottom: 6px; }.arch-flow { text-align: center; font-size: 11px; color: #4b5563; margin: 6px 0; }.arch-user-types { display: flex; gap: 4px; justify-content: center; margin-top: 6px; }.arch-user-tag { font-size: 9px; padding: 2px 6px; border-radius: 10px; background: rgba(59, 130, 246, 0.15); color: #1d4ed8; }
  </style>
  <div class="arch-title">OccuEVRoute 逻辑微服务架构</div>
  <div class="arch-subtitle">面向深圳的课程演示型电动车充电路线规划：地图工作流、搜索算法、充电可达性、占用率预测、POI 上下文与诊断信息</div>
  <div class="arch-wrapper">
    <div class="arch-sidebar">
      <div class="arch-sidebar-panel"><div class="arch-sidebar-title">演示运维</div><div class="arch-sidebar-item">Vite preview</div><div class="arch-sidebar-item">前端 9090</div><div class="arch-sidebar-item">后端 9000</div><div class="arch-sidebar-item">健康检查 API</div></div>
      <div class="arch-sidebar-panel"><div class="arch-sidebar-title">诊断信息</div><div class="arch-sidebar-item">搜索轨迹</div><div class="arch-sidebar-item">扩展节点数</div><div class="arch-sidebar-item">运行耗时</div><div class="arch-sidebar-item">拒绝原因</div></div>
      <div class="arch-sidebar-panel"><div class="arch-sidebar-title">质量检查</div><div class="arch-sidebar-item">路线数据检查</div><div class="arch-sidebar-item">API 冒烟测试</div><div class="arch-sidebar-item">前端构建</div><div class="arch-sidebar-item">重点测试</div></div>
    </div>
    <div class="arch-main">
      <div class="arch-layer user">
        <div class="arch-layer-title">客户端工作区</div>
        <div class="arch-grid arch-grid-4"><div class="arch-box highlight">React 规划界面<br><small>Vite + TypeScript</small></div><div class="arch-box">Leaflet 路线地图<br><small>路线、站点、边界图层</small></div><div class="arch-box">规划控制面板<br><small>车辆、搜索、算法参数</small></div><div class="arch-box">诊断展示面板<br><small>排序、轨迹、路线详情</small></div></div>
        <div class="arch-user-types"><span class="arch-user-tag">汇报者</span><span class="arch-user-tag">评审者</span><span class="arch-user-tag">课程演示</span></div>
      </div>
      <div class="arch-flow">HTTP JSON：/api/boundary、/api/recommendations、/api/health</div>
      <div class="arch-layer application">
        <div class="arch-layer-title">后端 API 与领域服务边界</div>
        <div class="arch-grid arch-grid-3"><div class="arch-box highlight">FastAPI 网关<br><small>Schema、CORS、校验、响应整形</small></div><div class="arch-box">推荐编排服务<br><small>请求转为领域工作流</small></div><div class="arch-box">地理数据服务<br><small>深圳边界与 POI 查询</small></div></div>
        <div class="arch-subgroup">
          <div class="arch-subgroup-box"><div class="arch-subgroup-title">API 契约</div><div class="arch-grid arch-grid-2"><div class="arch-box tech">RecommendationRequest<br><small>位置、车辆、算法、排序</small></div><div class="arch-box tech">RecommendationResponse<br><small>推荐项与多指标排序</small></div></div></div>
          <div class="arch-subgroup-box"><div class="arch-subgroup-title">服务策略</div><div class="arch-grid arch-grid-3"><div class="arch-box tech">缓存预热<br><small>路网、站点、预测器</small></div><div class="arch-box tech">边界保护<br><small>仅支持深圳区域规划</small></div><div class="arch-box tech">排序合并<br><small>路线 + POI + 占用率</small></div></div></div>
        </div>
      </div>
      <div class="arch-layer ai">
        <div class="arch-layer-title">路线规划与占用率预测服务</div>
        <div class="arch-grid arch-grid-4"><div class="arch-box highlight">路线规划服务<br><small>BFS、UCS、A*、CH 双向 Dijkstra</small></div><div class="arch-box">候选站筛选服务<br><small>半径、充电桩数、道路接入</small></div><div class="arch-box">约束判断引擎<br><small>电池、到达 SOC、行驶时间</small></div><div class="arch-box">占用率预测服务<br><small>XGBoost 多时域模型</small></div></div>
        <div class="arch-subgroup">
          <div class="arch-subgroup-box"><div class="arch-subgroup-title">搜索加速</div><div class="arch-grid arch-grid-3"><div class="arch-box tech">ALT 地标表<br><small>有向正向/反向距离表</small></div><div class="arch-box tech">CH 索引<br><small>收缩层级预处理制品</small></div><div class="arch-box tech">道路吸附服务<br><small>最近道路边与起点节点</small></div></div></div>
          <div class="arch-subgroup-box"><div class="arch-subgroup-title">预测特征</div><div class="arch-grid arch-grid-3"><div class="arch-box tech">历史站点状态<br><small>忙闲车位、价格、时长</small></div><div class="arch-box tech">天气上下文<br><small>温度、湿度、降雨</small></div><div class="arch-box tech">邻近站点画像<br><small>周边站点历史规律</small></div></div></div>
        </div>
      </div>
      <div class="arch-layer data">
        <div class="arch-layer-title">数据与模型制品</div>
        <div class="arch-grid arch-grid-5"><div class="arch-box tech">道路图<br><small>shenzhen_drive_with_station_access.graphml</small></div><div class="arch-box tech">站点接入表<br><small>station_road_access.csv</small></div><div class="arch-box tech">POI 特征表<br><small>station_poi_features.csv</small></div><div class="arch-box tech">搜索索引<br><small>landmarks npz + ch_index.pkl</small></div><div class="arch-box tech">占用率模型<br><small>pkl + 特征元数据</small></div></div>
        <div class="arch-subgroup">
          <div class="arch-subgroup-box"><div class="arch-subgroup-title">原始输入</div><div class="arch-grid arch-grid-3"><div class="arch-box tech external">UrbanEV 数据集<br><small>站点历史记录</small></div><div class="arch-box tech external">UrbanEV 补充数据<br><small>天气与行政边界</small></div><div class="arch-box tech external">OSM 道路网络<br><small>下载后的可通行道路</small></div></div></div>
          <div class="arch-subgroup-box"><div class="arch-subgroup-title">生成输出</div><div class="arch-grid arch-grid-3"><div class="arch-box tech">data/processed<br><small>路线与 POI 制品</small></div><div class="arch-box tech">models/<br><small>训练后的预测模型制品</small></div><div class="arch-box tech">docs/figures<br><small>指标与 SHAP 图</small></div></div></div>
        </div>
      </div>
      <div class="arch-layer infra">
        <div class="arch-layer-title">运行时与部署</div>
        <div class="arch-grid arch-grid-4"><div class="arch-box highlight">Vite 前端预览<br><small>构建产物 + /api 代理</small></div><div class="arch-box highlight">FastAPI 后端<br><small>Python 领域模块</small></div><div class="arch-box">本地数据制品<br><small>data、models、ML/Data</small></div><div class="arch-box">开发运行时<br><small>uvicorn 9000 + Vite 5173</small></div></div>
      </div>
      <div class="arch-layer external">
        <div class="arch-layer-title">离线数据流水线服务</div>
        <div class="arch-grid arch-grid-6"><div class="arch-box tech">边界生成服务<br><small>GeoJSON 服务范围</small></div><div class="arch-box tech">道路下载服务<br><small>OSM 瓦片与裁剪</small></div><div class="arch-box tech">站点路网构建<br><small>道路接入关系合并</small></div><div class="arch-box tech">POI 特征构建<br><small>周边上下文聚合</small></div><div class="arch-box tech">地标表构建<br><small>ALT 启发式距离表</small></div><div class="arch-box tech">模型训练服务<br><small>占用率时域 XGBoost</small></div></div>
      </div>
    </div>
    <div class="arch-sidebar">
      <div class="arch-sidebar-panel"><div class="arch-sidebar-title">领域归属</div><div class="arch-sidebar-item">frontend 负责 UI 状态</div><div class="arch-sidebar-item">backend 负责 API 形状</div><div class="arch-sidebar-item">route_planning 负责搜索</div><div class="arch-sidebar-item">waiting_prediction 负责 ML</div></div>
      <div class="arch-sidebar-panel"><div class="arch-sidebar-title">数据契约</div><div class="arch-sidebar-item">类型化 Schema</div><div class="arch-sidebar-item">受约束算法选项</div><div class="arch-sidebar-item">站点 ID</div><div class="arch-sidebar-item">WGS84 坐标</div></div>
      <div class="arch-sidebar-panel"><div class="arch-sidebar-title">演示指标</div><div class="arch-sidebar-item metric">距离</div><div class="arch-sidebar-item metric">行驶时间</div><div class="arch-sidebar-item metric">到达 SOC</div><div class="arch-sidebar-item metric">占用率风险</div></div>
    </div>
  </div>
</div>

## 阅读说明

- 运行时微服务：Vite 前端负责地图与交互，FastAPI 后端负责 API 与领域编排。
- 逻辑服务边界：后端内部按路线规划、候选站筛选、约束判断、POI 合并、占用率预测和排序诊断拆分。
- 数据服务边界：大体量路网、站点、POI、索引和模型以制品形式挂载，避免运行时重新生成。
- 离线流水线：`src/data_processing/` 与 `src/waiting_prediction/` 负责生成可复现的数据、索引、模型和报告图表。
