# 学习单元 07 ClickHouse 指标存储与重放安全

## 本单元目标

完成本单元后，应能够解释：

1. 为什么分钟级经营指标适合写入列式分析数据库。
2. Flink JDBC Sink 的批量、重试和 checkpoint 分别能证明什么。
3. 为什么不能使用 `SummingMergeTree` 吸收作业重放。
4. `ReplacingMergeTree(version)` 为什么仍然需要 `FINAL` 查询。
5. 当前设计为什么不等于端到端 exactly-once。

## 版本与组件

| 组件 | 版本 | 作用 |
| --- | --- | --- |
| ClickHouse Server | 25.8.33.6 | 本地分析存储 |
| Flink JDBC Connector | 3.4.0-1.20 | 将分钟指标批量写入 JDBC |
| ClickHouse JDBC | 0.10.0 | ClickHouse Java 驱动 |

容器镜像、Maven 连接器和驱动均固定版本，避免 `latest` 或动态版本导致不可复现构建。

## 表键与替换语义

一分钟指标的业务唯一键是：

```text
(window_start, region, channel)
```

Flink 失败恢复或 JDBC 重试可能再次写入同一个窗口结果。如果使用 `SummingMergeTree`，重复行会再次累加，使订单量和 GMV 翻倍。因此表使用：

```sql
ENGINE = ReplacingMergeTree(version)
ORDER BY (window_start, region, channel)
```

Sink 为每次输出生成单调递增的 `version`。同一个业务键出现新版本时，后台合并最终保留最高版本。由于后台合并时间不确定，查询层必须使用 `FINAL` 或等价的显式最新版本逻辑。

项目创建 `ecommerce.minute_metrics_latest` 视图，将 `FINAL` 约束集中在一个位置，并计算客单价，避免 API 层忘记去重。

## JDBC Sink 一致性边界

当前 Sink 参数：

- batch size：100；
- batch interval：1000 ms；
- max retries：3；
- 密码：仅从 `CLICKHOUSE_PASSWORD` 环境变量读取。

批量提高吞吐量，重试提高短暂故障下的成功率，但也会产生重复写入可能。`ReplacingMergeTree` 让相同业务键的重放结果最终收敛；这是一种面向分析结果的幂等设计，不是跨 Kafka、Flink 和 ClickHouse 的分布式事务。

## 本地运行

启动并验证 ClickHouse：

```powershell
./scripts/clickhouse-up.ps1
./scripts/clickhouse-smoke-test.ps1
```

启动 Kafka 并提交 Flink 作业：

```powershell
./scripts/kafka-up.ps1
./scripts/kafka-produce-sample.ps1
./scripts/submit-flink-job.ps1 -StartingOffsets earliest
```

查看最新结果：

```powershell
./scripts/clickhouse-query.ps1 -Limit 20
```

若 Flink 运行在 Compose 网络内，使用：

```text
--clickhouse-url jdbc:clickhouse://clickhouse:8123/ecommerce
```

## 冒烟测试证明什么

`clickhouse-smoke-test.ps1` 创建临时表，向同一个业务键写入版本 1 和版本 2，再用 `FINAL` 查询。验收条件是只返回一行，并且订单量、GMV 和版本均等于版本 2 的值。

它能证明表引擎和查询语义正确，但不能证明：

- Flink 已经连接真实 Kafka 和 ClickHouse 运行；
- 长时间运行没有连接泄漏或积压；
- 高并发写入下的吞吐量满足生产要求；
- 系统具备端到端 exactly-once。

## 安全边界

Compose 中 ClickHouse 的 8123 和 9000 端口只绑定 `127.0.0.1`。为了让作品集可一键启动，本地容器跳过用户初始化；这一设置不能用于公网或生产环境。启用认证时，密码必须通过环境变量或密钥管理系统提供，不得提交到仓库。

## 面试自测

1. 为什么 JDBC 重试可能造成重复写入？
2. 为什么 `SummingMergeTree` 不适合直接处理重放后的完整窗口结果？
3. `ReplacingMergeTree` 为什么不能提供同步 upsert？
4. `FINAL` 的正确性收益和性能代价是什么？
5. 如果未来允许窗口迟到更新，`version` 应如何保证新结果胜出？
