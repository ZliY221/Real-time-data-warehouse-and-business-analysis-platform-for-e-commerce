# 学习单元 15：真实链路验收与 Watermark 推进

## 学习目标

完成本单元后，你应该能解释：

1. 为什么 Kafka 中已经有 20 条事件，Flink 第一分钟窗口仍可能没有输出。
2. 为什么端到端验收使用单分区隔离 Topic，而不是复用三分区业务 Topic。
3. 如何隔离 ClickHouse 数据，避免历史演示结果污染本次对账。
4. 自动验收脚本如何提交、观察、取消作业并清理精确资源。
5. “脚本已实现”和“真实环境已通过”为什么是两种不同证据。

## 被发现的窗口触发问题

参考生成器每 3 秒产生一条事件。20 条事件的时间范围是：

```text
第一条事件：10:00:00
最后一条事件：10:00:57
乱序容忍：  10 秒
近似 Watermark：10:00:47
窗口终点：  10:01:00
```

Kafka Source 是无界流，不会因为“当前暂时没有更多消息”自动发出最大 Watermark。`withIdleness` 解决的是空闲分区阻塞其他活跃分区，不会凭空把业务时间推进到窗口之后。因此只发送这 20 条数据再等待，第一分钟窗口可能永远不输出。

验收脚本额外生成 3 条从 `10:01:15` 开始的合法事件。最后一条为 `10:01:21`，减去 10 秒乱序容忍后仍晚于 `10:01:00`，可以确定触发第一分钟窗口。

## 为什么使用单分区 Topic

多分区 Source 的整体 Watermark 受最慢的非空闲分区限制。如果推进事件只进入其中一个分区，其他分区在 idleness 超时前仍可能阻塞窗口，验收时间会依赖分区器和等待时长。

`e2e-acceptance.ps1` 为每次运行创建：

- 唯一 Topic：`order-events-e2e-<run-id>`；
- 固定一个分区，消除跨分区 Watermark 不确定性；
- 唯一 Consumer Group；
- 唯一 ClickHouse 数据库：`ecommerce_acceptance_<run-id>`。

这不是生产 Topic 的推荐分区数，而是受控验收夹具。生产三分区配置仍用于演示分区并行和 idleness 策略。

## 前置条件

- Docker Desktop 和 Docker Compose v2；
- Python 3.11 或更高版本；
- JDK 17 与 Maven；
- Apache Flink 1.20.1，`flink` 命令在 PATH 中；
- 本地 Flink 集群已经启动，`flink list` 能成功连接。

脚本不会安装软件、启动 Flink 集群或修改系统环境变量。

## 一键运行

```powershell
./scripts/e2e-acceptance.ps1
```

默认流程：

1. 验证本地 Flink 集群；
2. 执行 Java/Flink 测试并构建 shaded JAR；
3. 启动 Kafka 和 ClickHouse；
4. 创建隔离 Topic 与隔离数据库；
5. 生成 20 条业务事件、3 条 Watermark 推进事件和离线基准；
6. 以 `earliest` 策略提交 Flink 作业，并从 CLI 输出捕获 JobID；
7. 依次生产业务事件和推进事件；
8. 最多轮询 90 秒，等待第一分钟 10 个最终指标键；
9. 导出 `FINAL` 指标及迟到事件，执行批流精确对账；
10. 保存证据、取消 Flink 作业，并定向删除本次 Topic 与数据库。

已有最新 JAR 时可以跳过构建：

```powershell
./scripts/e2e-acceptance.ps1 -SkipBuild
```

需要在运行后人工检查测试数据库和 Topic 时：

```powershell
./scripts/e2e-acceptance.ps1 -KeepDataResources
```

即使保留数据资源，脚本仍会尝试取消 Flink 作业，避免后台持续消费。检查完成后必须手工删除输出中列出的精确数据库和 Topic。

## 证据目录

每次运行写入 `build/e2e/<run-id>/`：

| 文件 | 用途 |
| --- | --- |
| `business_events.ndjson` | 本次对账的 20 条固定业务事件 |
| `watermark_events.ndjson` | 只负责推进窗口的 3 条后续事件 |
| `expected_metrics.ndjson` | Python 离线基准 |
| `actual_metrics.ndjson` | ClickHouse `FINAL` 实际结果 |
| `late_events.ndjson` | 本次时间范围的迟到事件 ID |
| `report.json` | 机器可读对账报告 |
| `report.md` | 面试展示用对账结论 |
| `manifest.json` | Topic、数据库、JobID、时间范围和键数量 |

`build/` 被 Git 忽略。首次真实通过后，应挑选不含凭据和隐私的报告、终端截图及环境版本，整理为发布附件或作品集证明，而不是把运行数据库提交到仓库。

## 常见失败定位

| 现象 | 优先检查 |
| --- | --- |
| `flink list` 失败 | 本地集群是否启动、Flink 版本及 PATH |
| 无法捕获 JobID | Flink CLI 输出、JAR 主类、集群提交日志 |
| 指标键一直为 0 | Kafka 地址、Source offset、作业状态、ClickHouse JDBC URL |
| 指标不足 10 个 | 推进事件是否消费、Watermark、窗口异常日志 |
| 指标多于 10 个 | 是否错误复用了数据库或时间范围 |
| 对账订单量不同 | `event_id` 去重、无效事件过滤和迟到侧流 |
| 只差 GMV | Decimal 映射、JDBC 字段顺序和金额口径 |
| 清理警告 | 按日志中的精确 JobID、Topic、数据库手工处理 |

## 安全与清理

- 数据库和 Topic 名称由固定安全前缀与 UTC 数字时间组成，使用前再次校验字符集。
- 脚本不删除共享 `order-events` Topic，也不清空 `ecommerce` 数据库。
- 默认只删除本次创建的隔离 Topic 和数据库。
- Kafka、ClickHouse 基础容器及共享卷不会自动停止或删除。
- 如需删除整个本地演示环境，应在确认无保留数据后显式运行 `./scripts/kafka-down.ps1 -RemoveData`。

## 面试讲法

> 我在准备端到端验收时发现，20 条样例的最大事件时间只有 10:00:57，在 10 秒乱序容忍下 Watermark 还没越过 10:01:00，所以单纯等待不会关闭窗口。我没有把“没数据”误判成 Sink 故障，而是为验收创建单分区隔离 Topic，并发送下一分钟的合法推进事件。脚本使用独立数据库、捕获 JobID、轮询最终指标、执行批流对账并定向清理资源。该流程已在 GitHub Actions 的 Flink 1.20.1 单节点集群真实通过，10 个指标键全部匹配。

## 当前证据边界

- Watermark 时间关系、脚本语法、隔离资源约束和对账逻辑已有本地自动化测试。
- 当前开发机没有 Docker CLI 和本地 Flink 集群，但远程 CI 已真实启动 Kafka、ClickHouse 与 Flink 1.20.1 并运行验收脚本。
- 首次完整链路成功证据为运行 [37188134524](https://github.com/ZliY221/Real-time-data-warehouse-and-business-analysis-platform-for-e-commerce/actions/runs/37188134524)：JobID `7eaef8f77086847befded3990b9e1df1`，20 条业务事件、3 条推进事件、10 个指标键全部匹配。
- 运行 [37189195478](https://github.com/ZliY221/Real-time-data-warehouse-and-business-analysis-platform-for-e-commerce/actions/runs/37189195478) 进一步上传了保留 90 天的脱敏 Artifact；下载审计确认只有 5 个聚合与报告文件、无原始事件文件，SHA-256 为 `b58e134b7ddf5ca32e79632103f73fc8b37b4675708f693e14d713b32aa5901a`。
- 该证据只覆盖单节点受控批次，不证明生产高可用、端到端 exactly-once、长期状态 TTL 边界或性能 SLA。
