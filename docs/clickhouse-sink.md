# ClickHouse 指标存储与重放安全

## 设计范围

分钟指标和异常审计数据写入 ClickHouse。存储层使用稳定业务键、版本列和 `ReplacingMergeTree` 处理重复写入，并通过 `FINAL` 视图提供确定的最新结果。该设计覆盖 JDBC 批量、重试与 checkpoint 的一致性边界，但不提供跨 Kafka、Flink 和 ClickHouse 的分布式事务。

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

异常侧流使用同样的版本替换思路：

- `rejected_order_events` 以原始载荷的 SHA-256 指纹作为稳定键，只保存错误类型、载荷字节数、检测时间和版本。
- `late_order_events` 以契约中的唯一 `event_id` 作为稳定键，保存合成订单标识、事件时间、进入时间、地区、渠道和精确金额。
- `event_anomaly_summary` 视图按分钟、异常类型和原因汇总 `FINAL` 后的不同异常记录。

拒绝表不保存 `raw_payload` 和解析器原因，控制台对象也只显示错误类型与载荷大小。

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
./scripts/clickhouse-query-anomalies.ps1 -Limit 20
```

若 Flink 运行在 Compose 网络内，使用：

```text
--clickhouse-url jdbc:clickhouse://clickhouse:8123/ecommerce
```

## 冒烟测试范围

`clickhouse-smoke-test.ps1` 为分钟指标、拒绝事件和迟到事件分别创建临时表，向同一个稳定键写入版本 1 和版本 2，再用 `FINAL` 查询。验收条件是三张表都只返回最新一行，且版本与更新字段来自版本 2。

该测试验证表引擎和查询语义。完整链路 Job 另行验证 Flink 在单节点受控批次中连接 Kafka 和 ClickHouse 并完成对账，但不覆盖：

- 长时间运行没有连接泄漏或积压；
- 高并发写入下的吞吐量满足生产要求；
- 系统具备端到端 exactly-once。

## 安全边界

Compose 中 ClickHouse 的 8123 和 9000 端口只绑定 `127.0.0.1`。为了让项目可一键启动，本地容器跳过用户初始化；这一设置不能用于公网或生产环境。启用认证时，密码必须通过环境变量或密钥管理系统提供，不得提交到仓库。

## 设计约束

- JDBC 重试可能重复写入，因此结果表不能依赖追加后求和来吸收重放。
- `SummingMergeTree` 会重复累计完整窗口结果，不适合作为当前写入模型。
- `ReplacingMergeTree` 在后台异步合并，读取最新结果时必须使用 `FINAL` 或等价查询。
- `FINAL` 提供确定结果，同时增加查询开销；当前数据规模和查询范围受控。
- 若后续支持窗口迟到更新，`version` 必须保持单调递增，使新窗口结果覆盖旧版本。
