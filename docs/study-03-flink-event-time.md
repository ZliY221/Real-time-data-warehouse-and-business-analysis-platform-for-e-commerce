# 学习单元 03 Flink 事件时间 去重与分钟窗口

## 本单元目标

完成本单元后，应能够解释：

1. 为什么经营指标使用事件时间而不是处理时间。
2. Watermark、乱序容忍时间和空闲分区的关系。
3. 为什么 Kafka 的至少一次投递会导致下游需要去重。
4. Flink Keyed State 和 State TTL 在去重中的作用。
5. 增量聚合为什么比把窗口内全部事件保存在内存中更节省资源。

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

## 为什么先脱离 Kafka 测试

窗口、去重和聚合属于计算逻辑，不应该只能通过完整中间件环境验证。测试使用有界内存数据源运行真实 Flink DataStream：

- 注入一条重复事件，验证只计算一次。
- 注入一条进入时间早于事件时间的非法事件，验证被过滤。
- 注入两个地区和渠道，验证维度隔离。
- 使用 `10.10 + 20.20`，验证 `BigDecimal` 结果为 `30.30`。
- 验证一分钟窗口的起止时间。

这样即使 Docker 或 Kafka 暂不可用，核心计算仍然有可重复证据。

## 本地测试

系统默认 Java 8 不满足当前项目要求，脚本只在当前进程临时使用已经安装的 JDK 17，不修改系统配置：

```powershell
./scripts/test-flink.ps1
```

## 当前边界

- 还没有把 NDJSON 字符串解析为 `OrderEvent`，下一阶段接入 JSON 解析并处理坏消息侧输出。
- 还没有连接 Kafka Source 和 Sink。
- State TTL 基于处理时间清理，适合当前去重实验；生产策略需要结合最大重放周期和状态体积确定。
- 当前非法事件被过滤，下一阶段应输出到质量侧流，而不是静默丢弃。
- 尚未实现 allowed lateness 和迟到数据侧输出。

## 面试自测

1. Watermark 为 `T - 10 秒` 时，一条晚到 15 秒的事件会怎样？
2. 为什么空闲 Kafka 分区可能阻塞窗口触发？
3. 去重状态 TTL 太短或太长分别有什么风险？
4. `AggregateFunction` 与 `ProcessWindowFunction` 为什么组合使用？
5. 过滤非法事件与写入侧输出相比有什么缺点？

