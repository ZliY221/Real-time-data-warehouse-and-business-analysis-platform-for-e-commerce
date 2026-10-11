# Flink KafkaSource 与消费恢复

## 设计范围

作业使用 `KafkaSource` 消费原始 JSON，支持 committed、earliest 和 latest 三种起始位置。业务时间在 JSON 解析后提取并分配 Watermark；checkpoint 维护 Source 与 Flink 状态的一致恢复，但不扩展为 JDBC Sink 的端到端 exactly-once。

## 版本锁定

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Apache Flink | 1.20.1 | DataStream 运行时与 API |
| Flink Kafka Connector | 3.3.0-1.20 | 面向 Flink 1.20 的 Kafka Source 连接器 |
| Kafka broker 镜像 | 3.9.1 | 本地 KRaft 单节点环境 |
| Java 编译目标 | 11 | 在 JDK 17 上编译，兼容 Java 11 字节码 |

Jackson 使用 BOM 统一依赖族版本，避免 Kafka 连接器的传递依赖与项目 JSON 解析器发生二进制冲突。`flink-connector-base` 由 Flink 运行环境提供，因此在 Maven 中使用 `provided` scope；Kafka 连接器和其客户端依赖进入 shaded 作业 JAR。

## Source 与事件时间的职责边界

Kafka 中保存的是原始 JSON 字符串。只有经过 `OrderEventJsonParser` 后，程序才能安全取得业务字段 `event_time`。因此链路是：

```text
KafkaSource<String>
  -> JSON 解析与坏消息侧流
  -> 从 event_time 分配时间戳和 Watermark
  -> event_id 状态去重
  -> 一分钟事件时间窗口
```

在 `environment.fromSource(...)` 上使用 `WatermarkStrategy.noWatermarks()` 并不是放弃事件时间，而是避免在尚未解析的字符串上伪造时间戳。真正的 bounded out-of-orderness Watermark 在解析后的 `OrderEvent` 流上分配。

## 起始消费位置

作业支持三种 `--starting-offsets`：

- `committed`：默认值。优先使用 Consumer Group 已提交的位置；新 Group 没有提交位置时回退到 earliest。
- `earliest`：从 Topic 可用的最早位置读取，适合固定样例回放和验收。
- `latest`：从作业启动后的新消息开始，适合只关注实时新增数据的场景。

Flink 在 checkpoint 中保存 Source 进度。恢复作业时，以 Flink checkpoint/savepoint 中的状态为准；提交到 Kafka 的 Consumer Group offset 主要用于外部观察消费进度以及没有 Flink 状态时的启动策略。

## Checkpoint 与一致性边界

作业每 10 秒开启一次 `CheckpointingMode.EXACTLY_ONCE` checkpoint，并限制同一时刻只进行一个 checkpoint。它可以保证 Kafka Source 和 Flink 状态在故障恢复时保持一致。

早期实现的三个输出使用控制台 Sink；当前版本已将分钟指标、拒绝事件和迟到事件接入 ClickHouse 至少一次 JDBC Sink，并用稳定键与版本替换吸收重试。普通 JDBC Sink 没有跨系统事务提交协议，因此系统不提供端到端 exactly-once。

## 构建与提交

构建可部署 JAR：

```powershell
$env:JAVA_HOME = "<JDK 17 安装路径>"
mvn -f flink-job/pom.xml --batch-mode --no-transfer-progress clean package
```

启动 Kafka、生成样例数据并提交 Flink 作业：

```powershell
./scripts/kafka-up.ps1
./scripts/kafka-produce-sample.ps1
./scripts/submit-flink-job.ps1 -StartingOffsets earliest
```

连接 Docker 网络中的 Kafka 时，应显式指定容器内地址：

```powershell
./scripts/submit-flink-job.ps1 -BootstrapServers kafka:29092 -StartingOffsets earliest
```

## 验证状态

已经具备：

- KafkaSource 及三种起始位置的构建测试。
- 参数默认值、覆盖值和错误边界测试。
- 包含 Source、三类输出和 checkpoint 的 Flink 作业图测试。
- 可部署 shaded JAR 的本地构建记录。

远程单节点验收已具备：真实 Kafka broker、Flink 1.20.1 作业提交、ClickHouse JDBC 写入和 10 个指标键一致性结果。

仍然缺少：

- 作业 checkpoint 成功截图或 REST API 证据。
- Kafka offset、坏消息侧流和迟到侧流的运行观测结果。
- 长时间运行、故障恢复和多分区压力下的行为证据。

## 设计约束

- 原始字符串尚未提取 `event_time`，Source 层不生成业务 Watermark。
- `committed` 用于常规续跑，`earliest` 用于完整回放，`latest` 用于仅处理新增数据。
- 从 checkpoint/savepoint 恢复时以 Flink Source 状态为准，Kafka committed offset 只作为无状态启动位置和外部观测数据。
- 空闲 Partition 通过 idleness 策略退出整体 Watermark 最小值计算。
- JDBC Sink 不参与跨系统事务，因此作业不声明端到端 exactly-once。
