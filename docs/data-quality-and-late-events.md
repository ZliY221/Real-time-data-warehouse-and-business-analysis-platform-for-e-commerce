# JSON 解析、质量侧流与迟到数据

## 设计范围

解析链路区分 JSON 结构错误、业务规则错误、可接受乱序和窗口迟到。合法事件进入主流，拒绝事件与迟到事件进入独立侧流；金额始终从十进制字符串解析为 `BigDecimal`。

## 处理链路

```text
原始 NDJSON
  -> Jackson Tree Model 解析
  -> 字段与业务规则校验
     -> 合法事件主流
     -> RejectedEvent 质量侧流
  -> 事件时间与 Watermark
  -> 状态去重
  -> 一分钟窗口 + allowed lateness
     -> MinuteMetric 主流
     -> OrderEvent 迟到侧流
```

## 质量侧流

解析器不会把异常吞掉，而是输出 `RejectedEvent`：

- `malformed_json`：无法解析的 JSON。
- `invalid_json_shape`：根节点不是对象。
- `invalid_field`：字段缺失、类型错误、时间或金额格式错误。
- `business_validation_failed`：结构可解析，但违反地区、渠道、金额或时间顺序规则。

侧流对象在 Flink 内存中保留原始载荷、错误类型和原因，便于当前处理步骤判断和测试；对外持久化时只写入载荷 SHA-256 指纹、错误类型和 UTF-8 字节数，不写原始载荷或解析器原因。`toString()` 同样不输出原始 JSON，避免控制台日志意外泄露。

## 迟到数据

乱序表示事件到达顺序与事件发生顺序不同；只要它仍在 Watermark 允许范围内，就可以正常进入窗口。迟到表示 Watermark 已经越过该事件所属窗口及允许迟到时间。

窗口通过 `sideOutputLateData` 把过晚事件发送到独立流，避免静默丢失。测试使用自定义数据源主动发送 Watermark，再发送属于已关闭窗口的旧事件，验证它确实进入迟到侧流。

## 金额解析

事件契约要求 `total_amount` 是两位小数字符串。Java 解析器直接使用 `new BigDecimal(text)`，不经过 `double`，并拒绝数字节点与只有一位小数的字符串，确保跨语言契约一致。

## 当前边界

- JSON 解析只提取实时指标所需字段，商品明细的跨字段金额校验仍由上游 Python 契约校验器完成；后续可共享生成的 Schema 校验逻辑。
- 质量侧流和迟到侧流已经通过至少一次 JDBC Sink 接入 ClickHouse，并用稳定键和 `ReplacingMergeTree(version)` 吸收重试或重放；这不是事务型 upsert。
- 相同原始坏消息会映射为同一指纹，因此质量表统计的是“不同拒绝载荷签名”，不是包含重复消息在内的精确发生次数；若需要精确次数，应把 Kafka topic、partition、offset 保留到解析侧流。
- Kafka Source 已接入作业图；当前机器没有 Docker 和本地 Flink 集群，但真实 broker 到 ClickHouse 的单节点端到端运行已由远程 CI 验收。
- `allowedLateness` 的最终数值需要根据模拟延迟分布实验确定。

## 设计约束

- 解析失败必须进入可观测的侧流，不能通过 `null` 静默丢弃。
- 原始载荷只在 Flink 处理过程中短暂存在，持久化记录采用最小披露字段。
- Watermark 的 10 秒乱序范围控制窗口首次触发；30 秒 `allowedLateness` 控制窗口关闭后的可更新范围。
- 允许迟到范围内的事件会更新已触发窗口；超过范围的事件进入迟到侧流。
- 坏消息率和迟到率由异常汇总表持续统计，阈值告警不在当前实现范围内。

