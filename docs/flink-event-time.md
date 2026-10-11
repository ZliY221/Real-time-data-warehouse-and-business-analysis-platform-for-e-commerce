# Flink 事件时间、去重与分钟窗口

## 设计范围

实时指标按事件时间进入一分钟滚动窗口。Watermark 处理有限乱序，Keyed State 按 `event_id` 去重，State TTL 限制状态保留时间，增量聚合避免缓存窗口内全部事件。

## 当前实现

Java 模块位于 `flink-job`，使用：

- Apache Flink 1.20.1
- JDK 17 运行，Java 11 编译目标
- DataStream API
- JUnit 5 与 Flink 本地执行环境

处理链路：

```text
OrderEvent
  -> 业务规则校验
  -> 分配事件时间与 Watermark
  -> 按 event_id 分区并用 Keyed State 去重
  -> 按 地区 + 渠道 分区
  -> 一分钟事件时间滚动窗口
  -> 增量计算订单量和 GMV
  -> MinuteMetric
```

## 计算逻辑隔离测试

窗口、去重和聚合属于计算逻辑，不应该只能通过完整中间件环境验证。测试使用有界内存数据源运行真实 Flink DataStream：

- 注入一条重复事件，验证只计算一次。
- 注入一条进入时间早于事件时间的非法事件，验证被过滤。
- 注入两个地区和渠道，验证维度隔离。
- 使用 `10.10 + 20.20`，验证 `BigDecimal` 结果为 `30.30`。
- 验证一分钟窗口的起止时间。

因此计算逻辑可在不启动 Docker 或 Kafka 的情况下重复验证。

## 本地测试

系统默认 Java 8 不满足当前项目要求，脚本只在当前进程临时使用已经安装的 JDK 17，不修改系统配置：

```powershell
./scripts/test-flink.ps1
```

## 历史阶段边界

以下内容记录阶段 03 当时的增量范围，JSON 解析、Kafka 接入和异常侧流已在后续技术文档补齐：

- 还没有把 NDJSON 字符串解析为 `OrderEvent`，下一阶段接入 JSON 解析并处理坏消息侧输出。
- 还没有连接 Kafka Source 和 Sink。
- State TTL 基于处理时间清理，适合当前去重实验；生产策略需要结合最大重放周期和状态体积确定。
- 当前非法事件被过滤，下一阶段应输出到质量侧流，而不是静默丢弃。
- 尚未实现 allowed lateness 和迟到数据侧输出。

## 设计约束

- 超出 Watermark 和允许迟到范围的事件进入迟到侧流。
- 空闲 Partition 必须标记 idleness，避免其 Watermark 阻塞整个算子。
- State TTL 过短会漏掉跨周期重放，过长会增加状态体积。
- `AggregateFunction` 负责增量计算，`ProcessWindowFunction` 补充窗口边界元数据。
- 非法事件进入质量侧流，不能静默过滤。

