# 数据资产血缘与新鲜度 SLO

## 设计范围

资产目录描述订单事件从 Kafka Topic、Flink 指标流、ClickHouse 指标表、FastAPI 到经营看板的依赖关系。目录用于运行诊断和影响分析，不替代 Kafka、Flink 或 ClickHouse 自身的元数据系统。

## 资产契约

`config/data-assets.json` 为每个资产保存稳定 ID、名称、类型、责任团队和上游列表。需要时效约束的资产额外声明 `freshness_slo_seconds`。加载器拒绝重复 ID、缺失上游、自依赖和循环血缘，避免返回不完整的影响范围。

当前链路为：

```text
kafka.order-events
  -> flink.minute-metrics
  -> clickhouse.minute-metrics
  -> api.metrics
  -> dashboard.operations
```

## 新鲜度判定

`clickhouse.minute-metrics` 的观测时间来自分钟指标查询中的最新处理时间。接口使用评估时间减去观测时间计算延迟：

- 延迟小于或等于 120 秒时为 `fresh`；
- 延迟超过 120 秒时为 `stale`；
- 没有可用处理时间时为 `no_data`。

接口同时沿有向无环图向下游遍历，返回可能受影响的 API 和看板。未来时间被收敛为零秒延迟，避免时钟偏差生成负值。

## 查询接口

```http
GET /api/v1/operations/assets/clickhouse.minute-metrics/freshness
```

可选的 `evaluated_at` 参数用于固定评估时间并复现告警结果。未知资产或未声明 SLO 的资产返回稳定的 `asset_not_found` 错误；分析存储不可用时沿用查询服务的统一 `503` 错误。

## 功能边界

当前版本对分钟指标表执行新鲜度检查，并通过静态配置维护血缘。生产环境可将同一模型接入 OpenLineage、DataHub 或独立元数据服务，但不应在没有采集证据时推断运行级血缘。
