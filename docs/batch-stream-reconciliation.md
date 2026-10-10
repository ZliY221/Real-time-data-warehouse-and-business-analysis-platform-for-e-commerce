# 批流指标一致性核对

## 项目目标

完成本单元后，你应该能解释：

1. 为什么“Flink 作业没有报错”不能证明业务指标正确。
2. 离线基准为什么必须复刻校验、去重、迟到处理和窗口边界。
3. 为什么金额对账使用 `Decimal` 精确比较，而不是设置浮点容差。
4. 如何定位缺失键、额外键、订单量差异和 GMV 差异。
5. 当前本地证据与真实端到端证据之间还差什么。

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

推荐直接运行隔离的一键验收：

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

## 设计说明

> 我没有用“任务运行成功”代替指标正确性。我为固定订单批次实现了独立的 Python 离线重算，复刻校验、首次事件去重、迟到事件剔除和 UTC 分钟窗口口径，再与 ClickHouse `FINAL` 结果按窗口、地区、渠道逐键精确比较。差异报告可以区分缺失键、额外键、订单量和 GMV 问题，金额使用 Decimal，不靠容差掩盖错误。该门禁已在 GitHub Actions 单节点真实链路中完成 10 个指标键的精确核对，结果为 10 matched、0 mismatched。

## 当前边界

- 本机没有 Docker CLI 和本地 Flink 集群；真实流式结果由临时远程 CI 生成，运行日志和摘要可核验，但 `build/` 文件不会跨 Runner 保留。
- 20 条参考事件本身不足以让 10 秒乱序 Watermark 越过第一分钟窗口；真实验收必须发送下一分钟推进事件，不能靠固定等待时间假设窗口会关闭。
- 当前核对针对一个有界输入批次，未模拟长时间运行后的状态 TTL 过期。
- 迟到事件以 ClickHouse 审计表导出的 `event_id` 为准，前提是实时作业与指标写入来自同一次受控实验。
- 已生成五个 Job 全部成功的远程 CI 运行记录，整链路批流对账已完成；本机复现、演示视频和生产规模验证仍待完成。
