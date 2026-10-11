# 批流指标一致性核对

## 设计范围

该模块使用独立离线基准核对流式结果，覆盖契约校验、事件去重、迟到处理、窗口边界和金额精度。对账报告按缺失键、额外键、订单量差异和 GMV 差异分类，便于直接定位口径偏差。

## 对账数据流

```text
同一批 order_created NDJSON
          │
          ├─► Kafka → Flink → ClickHouse minute_metrics_latest ─┐
          │                                                     ├─► 逐键精确比较
          └─► Python 校验 → 去重 → 剔除迟到 → 分钟聚合 ────────┘
```

固定输入同时进入实时链路和独立的 Python 基准引擎。基准不是复制 ClickHouse 查询结果，而是从原始事件重新计算。只有两个实现对同一业务键得到完全相同的订单量与 GMV，才能形成较强的正确性证据。

## 口径顺序

离线基准按以下顺序处理：

1. 解析每行 JSON；
2. 执行 `order_created` v1 业务契约校验；
3. 按 `event_id` 保留第一次出现；
4. 剔除 ClickHouse 迟到事件表中出现的 `event_id`；
5. 将 UTC `event_time` 向下取整到一分钟；
6. 按窗口、地区、渠道累加订单量和 `Decimal` 金额。

这个顺序与 Flink 当前拓扑一致。若先去重再校验，非法事件可能错误占用合法事件的去重键；若不剔除迟到事件，离线结果会包含实时主窗口明确路由到侧流的数据。

## 差异分类

| 状态 | 含义 | 常见原因 |
| --- | --- | --- |
| `missing_actual` | 离线有、实时没有 | 消费缺失、窗口未触发、Sink 失败 |
| `unexpected_actual` | 实时有、离线没有 | 时间范围混入其他批次、旧数据未隔离 |
| `order_count_mismatch` | 订单量不同 | 去重或过滤口径不一致 |
| `gmv_mismatch` | GMV 不同 | 金额精度或字段映射错误 |
| `order_count_and_gmv_mismatch` | 两项都不同 | 数据缺失、重复或聚合逻辑错误 |

报告只包含聚合键和值，不保存原始事件或用户标识。匹配成功返回退出码 `0`，存在业务差异返回 `1`，输入格式或运行配置错误返回 `2`。

## 本地构建离线基准

```powershell
$env:PYTHONPATH = "src"
python -m reconciliation.cli baseline `
  --events data/sample/order_events.ndjson `
  --output build/reconciliation/expected_metrics.ndjson
```

当前 20 条参考事件得到 10 个 `(window_start, region, channel)` 指标键。

## 真实链路对账步骤

运行隔离验收脚本：

```powershell
./scripts/e2e-acceptance.ps1
```

脚本会创建单分区临时 Topic 和独立 ClickHouse 数据库，提交 Flink 作业，发送业务事件及 Watermark 推进事件，等待第一分钟 10 个指标键落库，执行对账并定向清理本次资源。详细原理见 `docs/end-to-end-acceptance.md`。

若需要人工分步排查，在固定事件已经通过 Kafka 和 Flink 写入 ClickHouse 后，导出同一事件时间范围的最终指标与迟到事件：

```powershell
./scripts/clickhouse-export-reconciliation.ps1 `
  -Start "2026-10-02T10:00:00Z" `
  -End "2026-10-02T10:01:00Z"
```

导出查询使用 ClickHouse `{name:DateTime64(3, 'UTC')}` 参数和 `--param_name` 绑定值，时间范围最多 7 天。随后运行：

```powershell
./scripts/reconcile-metrics.ps1
```

结果写入：

- `build/reconciliation/report.json`：CI 或程序读取；
- `build/reconciliation/report.md`：人工审阅；
- 控制台与退出码：作为验收门禁。

## 自动化证据

测试覆盖：

- 固定样例的总订单量与精确 GMV；
- 非法 JSON、契约失败、重复和迟到事件的处理顺序；
- UTC、一分钟窗口、地区渠道枚举、整数订单量和两位小数金额校验；
- 重复实际键拒绝；
- 五种匹配或差异路径；
- CLI 基准生成以及通过、失败退出码；
- 报告不包含 `user_id` 或原始事件。

统一验证：

```powershell
./scripts/test-all.ps1
```

## 实现说明

固定订单批次由 Python 离线重算，处理顺序与 Flink 拓扑保持一致，再与 ClickHouse `FINAL` 结果按窗口、地区、渠道逐键比较。金额使用 `Decimal` 精确核对。GitHub Actions 的单节点链路已完成 10 个指标键对账，结果为 10 matched、0 mismatched。

## 当前边界

- 本机没有 Docker CLI 和本地 Flink 集群；真实流式结果由临时远程 CI 生成，运行日志和摘要可核验，但 `build/` 文件不会跨 Runner 保留。
- 20 条参考事件本身不足以让 10 秒乱序 Watermark 越过第一分钟窗口；真实验收必须发送下一分钟推进事件，不能靠固定等待时间假设窗口会关闭。
- 当前核对针对一个有界输入批次，未模拟长时间运行后的状态 TTL 过期。
- 迟到事件以 ClickHouse 审计表导出的 `event_id` 为准，前提是实时作业与指标写入来自同一次受控实验。
- 远程 CI 的五个 Job 均已通过，整链路批流对账已完成；本机复现和生产规模验证不在当前范围内。
