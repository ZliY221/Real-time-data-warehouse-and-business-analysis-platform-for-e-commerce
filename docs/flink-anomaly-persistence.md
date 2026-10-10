# Flink 异常侧流持久化

## 项目目标

完成本单元后，你应该能解释：

1. Flink 主流、拒绝侧流和迟到侧流分别承载什么语义。
2. 为什么异常不能只打印日志，也不能不加选择地保存完整坏消息。
3. 如何用稳定键和 `ReplacingMergeTree(version)` 吸收 JDBC 至少一次写入产生的重放。
4. 为什么当前拒绝事件统计是“不同载荷签名数”，而不是精确消息次数。
5. 如何验证作业图、字段绑定、隐私边界和 ClickHouse 替换语义。

## 三路输出

```text
Kafka order-events
       │
       ▼
JSON 解析与业务校验
       ├─ 合法事件 ─► 去重与事件时间窗口 ─► minute_metrics
       └─ 拒绝侧流 ─────────────────────► rejected_order_events
                         窗口过晚事件 ────► late_order_events
```

Flink 1.20.1 使用带具体类型的 `OutputTag` 发出和获取侧输出。项目已经在测试中验证错误 JSON 进入拒绝侧流、Watermark 越过窗口后的事件进入迟到侧流；本阶段把两条侧流接入独立 JDBC Sink。

## 为什么拒绝事件不保存原始载荷

坏消息可能包含上游意外带入的姓名、邮箱、地址或令牌。即使当前生成器只产生脱敏数据，把完整载荷写入长期数据库也会形成不必要的泄露面。

持久化记录只包含：

- `rejection_id`：原始载荷的 SHA-256 指纹；
- `error_type`：有限的解析或业务错误分类；
- `payload_size_bytes`：UTF-8 字节数；
- `detected_at` 与 `version`。

解析器的 `reason` 可能包含第三方库诊断文本，因此也不写入数据库。`RejectedEvent.toString()` 不再输出原始 JSON，防止调试日志旁路泄露。

指纹是单向摘要，不代表加密保存原文；低熵内容仍可能被枚举，因此 API 和看板也不应默认公开它。它的用途是判断同一坏载荷是否再次出现，并作为重放稳定键。`null` 与普通文本使用不同的域前缀，避免空值占位符与真实字符串产生同一摘要输入。

## 迟到事件保存什么

迟到事件已经通过事件契约和业务校验，因此可以保存项目生成的：

- `event_id`、`order_id`；
- `event_time`、`ingest_time`；
- 地区、渠道和 `Decimal(18, 2)` 金额；
- Sink 检测时间与版本。

`event_id` 是契约中的唯一标识，可作为重放稳定键。当前数据全部是项目生成的合成数据，不包含真实用户标识。

## 至少一次与版本替换

三个 JDBC Sink 都配置 batch size、batch interval 和 max retries，并使用 `buildAtLeastOnce`。Checkpoint 的 exactly-once 模式只描述 Flink Source 与状态一致性，不能把普通 JDBC Sink 变成跨系统事务。

异常量相对经营指标较小，两个异常 Sink 显式使用并行度 1，使各自 Statement Builder 的版本生成在单一实例内保持严格单调。扩容前需要把版本生成改为跨分区仍可比较的方案。

因此 ClickHouse 使用：

```sql
ENGINE = ReplacingMergeTree(version)
ORDER BY <stable_key>
```

| 数据 | 稳定键 |
| --- | --- |
| 分钟指标 | `(window_start, region, channel)` |
| 拒绝事件 | `rejection_id` |
| 迟到事件 | `event_id` |

查询通过 `FINAL` 获取每个稳定键的最新版本。这是最终替换语义，不是同步 upsert，也不是端到端 exactly-once。

## 相同坏消息为什么会合并

当前 Kafka Source 只向下游传递字符串，没有保留 topic、partition 和 offset。两个字节完全相同的坏消息会得到同一个指纹，`FINAL` 后只保留最新一条。

所以 `event_anomaly_summary` 中的拒绝数量表示“不同坏载荷签名数”。若业务要求精确发生次数，下一版应把 Kafka topic、partition、offset 包装进源记录，以 `(topic, partition, offset)` 作为每次发生的稳定身份；不能把当前数量误写为生产坏消息总量。

## 配置与运行

默认同时把三路输出写入 ClickHouse：

```powershell
./scripts/submit-flink-job.ps1 -StartingOffsets earliest
```

只进行脱敏控制台调试：

```powershell
./scripts/submit-flink-job.ps1 `
  -MetricsSink print `
  -AnomalySink print
```

同时写 ClickHouse 和打印：

```powershell
./scripts/submit-flink-job.ps1 -AnomalySink both
```

查询异常账本：

```powershell
./scripts/clickhouse-query-anomalies.ps1 -Limit 20
```

## 自动化证据

- 作业图测试确认默认存在三个 ClickHouse Sink，控制台模式不会意外连接数据库。
- Statement 测试确认迟到金额使用 `BigDecimal`，时间、维度和稳定键绑定到正确列。
- 隐私测试确认拒绝事件只绑定 64 位十六进制指纹、错误类型和字节数，原始载荷与原因都不进入 SQL 参数或 `toString()`。
- ClickHouse 冒烟脚本为三张表分别写入同键的两个版本，并要求 `FINAL` 只保留版本 2。
- 启动脚本在容器健康后重新执行幂等 DDL，因此已有数据卷也能补建新表和视图。

统一运行：

```powershell
./scripts/test-all.ps1
```

## 设计说明

> 我没有把 Flink 侧流只打印到日志。合法指标、拒绝事件和迟到事件分别进入三个至少一次 JDBC Sink。ClickHouse 用稳定业务键和版本替换吸收重试；拒绝事件只保存 SHA-256 指纹、错误类型和大小，避免原始坏消息进入长期存储。我也明确记录了限制：相同坏载荷会合并，当前统计是不同签名数；精确发生次数需要保留 Kafka partition 和 offset。

## 当前边界

- 本机没有 Docker CLI 和本地 Flink 集群；真实 Kafka → Flink → ClickHouse 已在远程单节点 CI 验收，但尚无本机复现或生产集群证据。
- `ReplacingMergeTree` 只提供最终替换，不提供事务型同步去重。
- 异常账本尚未接入 FastAPI 与看板，也没有持续告警。
- 还没有长期运行、故障恢复和吞吐压测证据。
