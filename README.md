# 电商实时数据仓库与经营分析平台

[![CI](https://github.com/ZliY221/Real-time-data-warehouse-and-business-analysis-platform-for-e-commerce/actions/workflows/ci.yml/badge.svg)](https://github.com/ZliY221/Real-time-data-warehouse-and-business-analysis-platform-for-e-commerce/actions/workflows/ci.yml)

这是一个面向数据开发和大数据开发实习岗位的作品集项目。项目通过模拟订单事件，逐步实现从事件生成、Kafka 采集、Flink 实时计算、分析存储到经营看板的完整数据链路。

当前版本已经完成事件契约、可复现数据生成、可配置数据质量门禁与 SQLite 历史趋势、Kafka 本地环境、Flink 计算核心、Kafka Source 作业入口、ClickHouse 分钟指标及异常审计表和 JDBC Sink、批流指标对账、DuckDB 离线维度数仓、只读 FastAPI 指标查询服务，以及响应式 ECharts 经营看板。中间件接入始终建立在可验证的数据语义上，避免出现“服务都启动了，但指标口径无法证明正确”的情况。

## 当前进度

- [x] 明确项目范围与验收标准
- [x] 定义订单创建事件 v1
- [x] 实现无第三方依赖的数据生成器
- [x] 为确定性、金额一致性和事件唯一性编写测试
- [x] 提供脱敏示例数据
- [x] 提供 Kafka KRaft Compose 配置和生产、消费、冒烟测试脚本
- [x] 实现可脱离 Kafka 测试的 Flink 事件时间、去重与一分钟窗口聚合核心
- [x] 实现可配置的 Flink KafkaSource、消费位置策略和 checkpoint 作业入口
- [x] 在 GitHub Actions 单节点隔离环境完成真实 Kafka broker 上的 Flink 端到端运行验收
- [x] 使用 Flink 完成事件时间窗口聚合
- [x] 处理重复事件、乱序事件和迟到事件，并输出质量与迟到侧流
- [x] 将拒绝事件指纹与迟到事件写入 ClickHouse，并提供重放安全的异常汇总查询
- [x] 实现独立的 Python 离线重算与逐键批流对账，区分缺失、额外、订单量和 GMV 差异
- [x] 实现 DuckDB ODS/DIM/DWD/DWS/ADS 分层、增量幂等装载、事务回滚和窗口函数品类排名
- [x] 提供隔离 Topic、数据库、Watermark 推进、轮询、对账和定向清理的一键端到端验收脚本
- [x] 配置 Python/API、Java/Flink、Kafka、ClickHouse 与完整链路五层持续集成工作流
- [x] 实现 ClickHouse `ReplacingMergeTree` 指标表、最新版本视图和 Flink JDBC Sink
- [x] 在 GitHub Actions 完成 Kafka、Flink、ClickHouse 端到端运行和 10 个指标键批流对账
- [x] 提供带参数校验、错误状态和 OpenAPI 文档的 FastAPI 查询接口
- [x] 提供带筛选、KPI、趋势、地区渠道分析和明细表的 ECharts 经营看板
- [x] 加入契约、完整性、唯一性、范围、及时性和分布漂移数据质量门禁
- [x] 使用 SQLite 保存质量运行与规则明细，并支持幂等写入、历史筛选和单规则趋势导出
- [x] 通过 FastAPI 与 ECharts 展示质量运行、异常计数和规则阈值趋势，并支持存储独立降级
- [ ] 加入运行监控与压力测试

## 业务问题

平台最终回答以下问题：

1. 当前每分钟的成交额和订单量是多少？
2. 不同地区、渠道和商品的销售表现如何？
3. 重复事件、乱序事件和迟到事件如何影响指标？
4. 批处理结果和流处理结果是否一致？
5. 当数据质量下降或计算延迟升高时，如何定位问题？

## 计划架构

```mermaid
flowchart LR
    A[Python 事件生成器] --> B[Kafka order-events]
    B --> C[Flink 清洗与去重]
    C --> D[Flink 事件时间窗口]
    D --> E[ClickHouse ReplacingMergeTree]
    E --> F[FastAPI 查询服务]
    F --> G[ECharts 经营看板]
    C --> H[拒绝与迟到侧流]
    H --> E
    A --> I[Python 离线指标基准]
    E --> J[批流逐键对账]
    I --> J
    A --> K[DuckDB 离线维度数仓]
    K --> L[DWS 日指标与 ADS 品类排名]
```

设计要点：

- 使用事件时间计算业务指标，避免运行速度影响结果。
- 第一版 Watermark 采用固定乱序容忍时间，并为 Kafka 空闲分区设置 idleness，防止整体 Watermark 停滞。
- 每条事件包含全局唯一的 `event_id`，Flink 阶段以此实现幂等去重。
- 金额使用十进制字符串传输，避免浮点误差。
- 压测数字只有在仓库中存在环境说明、脚本和原始结果时才写入简历。
- JDBC Sink 采用批量重试；ClickHouse 用稳定业务键和版本替换吸收重放，查询通过 `FINAL` 视图读取确定的最新结果。
- 拒绝事件只持久化 SHA-256 指纹、错误类型和载荷大小，不把原始坏消息或解析器原因写入数据库；迟到事件按 `event_id` 替换。
- 离线基准复刻实时校验、首次事件去重、迟到剔除和 UTC 分钟窗口口径，以 `Decimal` 精确核对 ClickHouse 最终指标。

## 目录结构

```text
ecommerce-realtime-warehouse/
├─ .github/workflows/             GitHub Actions 持续集成
├─ config/                       数据质量规则配置
├─ data/quality/                 可触发全部失败路径的脱敏测试数据
├─ data/sample/                  脱敏示例事件
├─ dashboard/                    ECharts 看板、样式与 JavaScript 测试
├─ design-system/                看板设计令牌与页面级设计决策
├─ docs/                         需求、架构和数据字典
├─ flink-job/                    Java/Flink 实时计算作业
├─ infra/clickhouse/init/        ClickHouse 初始化 DDL
├─ schemas/                      JSON Schema 事件契约
├─ scripts/                      测试、Kafka 与作业提交脚本
├─ src/event_generator/          事件生成器源码
├─ src/data_quality/             数据质量规则引擎、报告与 CLI
├─ src/reconciliation/           批流指标基准、差异报告与 CLI
├─ src/offline_warehouse/        DuckDB 分层模型、增量 ETL 与验收报告
├─ src/metrics_api/              FastAPI 查询服务与 ClickHouse HTTP 仓库
├─ tests/                        自动化测试
├─ .gitignore
├─ pyproject.toml
└─ README.md
```

## 本地运行

要求 Python 3.11 或更高版本。

生成 20 条示例事件：

```powershell
$env:PYTHONPATH = "src"
python -m event_generator.cli --count 20 --seed 2027 --output data/sample/order_events.ndjson
```

安装查询 API 和测试依赖：

```powershell
python -m pip install -e ".[api,test]"
```

运行全部 Python 测试：

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

事件生成器本身只使用 Python 标准库。相同 `seed`、`count` 和 `start-time` 会生成完全一致的事件，便于重放和测试；FastAPI 查询服务的依赖在 `pyproject.toml` 中单独锁定。

## 文档

- [需求与验收标准](docs/requirements.md)
- [架构设计](docs/architecture.md)
- [事件数据字典](docs/data-dictionary.md)
- [学习单元 01 事件契约与可复现数据](docs/study-01-event-contract.md)
- [学习单元 02 Kafka 本地消息链路](docs/study-02-kafka.md)
- [学习单元 03 Flink 事件时间 去重与分钟窗口](docs/study-03-flink-event-time.md)
- [学习单元 04 JSON 解析 质量侧流与迟到数据](docs/study-04-quality-and-late-data.md)
- [学习单元 05 持续集成与可验证交付](docs/study-05-continuous-integration.md)
- [学习单元 06 Flink KafkaSource 与消费恢复](docs/study-06-flink-kafka-source.md)
- [学习单元 07 ClickHouse 指标存储与重放安全](docs/study-07-clickhouse-sink.md)
- [学习单元 08 FastAPI 参数化查询与接口边界](docs/study-08-fastapi-query-service.md)
- [学习单元 09 ECharts 经营看板与可信演示](docs/study-09-echarts-dashboard.md)
- [学习单元 10 可配置数据质量门禁](docs/study-10-data-quality-gates.md)
- [学习单元 11 SQLite 质量历史与趋势](docs/study-11-quality-history.md)
- [学习单元 12 质量诊断 API 与看板](docs/study-12-quality-diagnostics-dashboard.md)
- [学习单元 13 Flink 异常侧流持久化](docs/study-13-flink-anomaly-persistence.md)
- [学习单元 14 批流指标一致性核对](docs/study-14-batch-stream-reconciliation.md)
- [学习单元 15 真实链路验收与 Watermark 推进](docs/study-15-end-to-end-acceptance.md)
- [学习单元 16 离线维度数仓与增量 ETL](docs/study-16-offline-dimensional-warehouse.md)
- [项目面试讲解与证据指南](docs/interview-guide.md)
- [远程仓库发布与验收清单](docs/publishing-checklist.md)

## 自动化验证

本地统一运行 Python/API/离线数仓测试、参考数据质量门禁、离线数仓构建、JavaScript 看板和 Java/Flink 测试：

```powershell
./scripts/test-all.ps1
```

GitHub Actions 工作流位于 `.github/workflows/ci.yml`，会先并行运行 Python 与 Flink 测试，再执行 Kafka 生产消费、ClickHouse 版本替换冒烟测试，以及隔离的 Kafka → Flink → ClickHouse → 批流对账验收。远程状态以 README 顶部徽章和 Actions 运行记录为准；只有目标提交的五个 Job 全部成功时，才对外表述“远程 CI 已通过”。

## Flink 核心测试

要求 JDK 17 或更高版本。以下脚本会优先使用 `JAVA_HOME`，并在 Windows 常见安装目录中自动寻找 JDK 17；环境切换只对测试进程生效，不会修改系统设置。脚本运行 Maven `verify`，同时验证测试和可部署 JAR 构建：

```powershell
./scripts/test-flink.ps1
```

Flink 核心已经实现 JSON 解析、质量侧流、事件校验、Watermark、基于 `event_id` 的状态去重、按地区和渠道统计的一分钟订单量与 GMV，以及迟到数据侧流。KafkaSource、分钟指标 Sink、拒绝事件 Sink 和迟到事件 Sink 已接入作业图；提交 `963be45` 已在 GitHub Actions 单节点隔离环境完成真实中间件端到端运行与批流对账。

当前验证基线：93 项 Python/API/数据质量/批流对账/离线数仓测试、8 项 JavaScript 看板测试和 28 项 Java/Flink 测试全部通过，共 129 项。

构建包含 Kafka 连接器和 JSON 依赖的可部署 JAR：

```powershell
$env:JAVA_HOME = "你的 JDK 17 路径"
mvn -f flink-job/pom.xml --batch-mode --no-transfer-progress clean package
```

在本地 Flink 集群和 Kafka 已启动后提交作业：

```powershell
./scripts/submit-flink-job.ps1 -StartingOffsets earliest
```

默认配置使用 `localhost:9092`、`order-events` Topic、`ecommerce-order-metrics` Consumer Group、10 秒乱序容忍、60 秒空闲分区检测、10 秒 checkpoint，并将分钟指标批量写入 `jdbc:clickhouse://localhost:8123/ecommerce`。完整参数与设计理由见学习单元 06 和 07。

## 数据质量门禁

对参考数据执行六项可配置规则，在 `build/data-quality/` 生成机器可读 JSON、面试展示用 Markdown 报告，并把运行摘要写入 SQLite：

```powershell
./scripts/data-quality-check.ps1
```

规则配置位于 `config/data-quality-rules.json`，覆盖订单 v1 契约、核心字段完整性、事件 ID 唯一性、订单金额范围、进入延迟和渠道分布漂移。CLI 使用退出码作为质量门禁：全部通过返回 `0`，规则失败返回 `1`，配置或输入错误返回 `2`。

仓库还包含 `data/quality/order_events_with_quality_issues.ndjson`，它会同时触发六类失败路径，用于演示规则定位能力。报告只保存行号、规则和必要的异常值，不复制整条事件或用户标识。

依次运行正常批次、预期失败批次并导出历史与单规则趋势：

```powershell
./scripts/data-quality-check.ps1
./scripts/data-quality-demo.ps1
./scripts/data-quality-history.ps1 -RuleId channel-share-drift
```

历史库为 `build/data-quality/history.db`，导出结果为 `history.json` 和 `history.md`。相同报告使用内容哈希生成同一个 `run_id`，重复写入不会产生重复运行；数据库只保存运行汇总、规则指标和必要样例，不保存完整事件负载。问题演示脚本把质量失败退出码 `1` 视为预期结果，但其他退出码仍会使脚本失败。

## Kafka 本地环境

安装 Docker Desktop 后运行：

```powershell
./scripts/kafka-up.ps1
./scripts/kafka-produce-sample.ps1
./scripts/kafka-consume.ps1 -FromBeginning -Count 20
./scripts/kafka-smoke-test.ps1 -Count 20
```

当前开发机没有 Docker CLI，也没有正在运行的 Flink 集群，因此不能在本机复现容器链路。GitHub Actions 已实际完成 Kafka 容器生产/消费、ClickHouse 替换语义，以及 Kafka → Flink → ClickHouse 组合链路与批流对账；这是单节点 CI 验收，不代表生产部署、长期稳定性或吞吐能力。

## ClickHouse 本地环境

ClickHouse 使用已锁定的官方镜像 `25.8.33.6`，端口只绑定到本机回环地址。启动并检查初始化表：

```powershell
./scripts/clickhouse-up.ps1
./scripts/clickhouse-smoke-test.ps1
```

运行 Flink 作业后查询最新的分钟指标：

```powershell
./scripts/clickhouse-query.ps1 -Limit 20
```

本地 Compose 使用 `CLICKHOUSE_SKIP_USER_SETUP=1`，仅适合单机演示环境，不可直接用于公网或生产部署。若外部 ClickHouse 启用了认证，只通过 `CLICKHOUSE_PASSWORD` 环境变量提供密码；脚本、命令行参数和仓库均不保存密码。

普通 JDBC Sink 具有批量与重试语义，不能据此宣称端到端 exactly-once。`minute_metrics` 使用 `(window_start, region, channel)` 作为稳定键，拒绝事件使用载荷 SHA-256 指纹，迟到事件使用 `event_id`；三类数据都以单调 `version` 进行替换，查询通过 `FINAL` 返回当前最新版本。拒绝事件表不保存原始载荷和解析器原因。ClickHouse 容器替换语义及 Flink JDBC 组合写入均已在 GitHub Actions 验收，但仍只属于单节点、受控批次证据。

查询异常分钟汇总和最近的不同异常记录：

```powershell
./scripts/clickhouse-query-anomalies.ps1 -Limit 20
```

## 批流指标一致性核对

从固定事件独立重算离线分钟基准：

```powershell
$env:PYTHONPATH = "src"
python -m reconciliation.cli baseline `
  --events data/sample/order_events.ndjson `
  --output build/reconciliation/expected_metrics.ndjson
```

真实 Kafka、Flink 和 ClickHouse 链路运行后，按同一事件时间范围导出最终指标及迟到事件，再执行对账：

```powershell
./scripts/clickhouse-export-reconciliation.ps1 `
  -Start "2026-10-02T10:00:00Z" `
  -End "2026-10-02T10:01:00Z"
./scripts/reconcile-metrics.ps1
```

对账使用 `(window_start, region, channel)` 作为键，对订单量和两位小数 GMV 进行精确比较；退出码 `0` 表示完全一致，`1` 表示存在业务差异，`2` 表示输入或运行错误。提交 `963be45` 的远程验收实际生成并匹配 10 个指标键，结果为 `10 matched, 0 mismatched`；本机仍因没有 Docker/Flink 环境而无法直接复现。

## 离线维度数仓

安装并构建本地分析数仓：

```powershell
python -m pip install -e ".[warehouse]"
./scripts/offline-warehouse-build.ps1
```

脚本把固定 NDJSON 批次装载到 `build/offline-warehouse/ecommerce.duckdb`，并导出 JSON 与 Markdown 验收报告。当前模型包括：

- `ods.order_events`：通过 v1 契约校验的订单事件粒度数据；
- `dim.dim_date`、`dim_region`、`dim_channel`、`dim_product`：一致性维度；
- `dwd.fact_order_items`：一行一个订单商品明细；
- `dws.daily_sales_by_region_channel`：地区、渠道日订单量、客户数、GMV 和客单价；
- `ads.daily_category_sales_rank`：使用 `DENSE_RANK` 计算每日品类销售排名；
- `meta.etl_runs` 与 `rejected_records`：批次审计及坏数据最小披露。

文件 SHA-256 形成稳定 `run_id`，同一文件重跑不会重复入库；跨批次相同事件计为重复，复用同一 `event_id` 却改变业务负载会使整个批次事务回滚。参考数据的实际本机结果为 20 条 ODS 事件、41 条 DWD 明细、6 个商品维度，聚合 GMV 与原始订单金额精确相等。DuckDB 用于无需外部服务即可验证维度建模和 SQL 语义，当前没有把它冒充 Hive/Spark 生产数仓经验。

装载器先在 Python 中完成契约校验和批内冲突判断，再把合法事件写入自动删除的临时 NDJSON，由 DuckDB 使用集合式 `INSERT ... SELECT`、连接和 `UNNEST` 完成维度及事实装载。该路径取代逐事件、逐商品 SQL 往返，同时保留文件幂等、跨批次冲突和事务回滚语义。

运行可复现本机性能基线：

```powershell
./scripts/benchmark-offline-warehouse.ps1 -Events 50000 -Trials 5
```

当前 Windows 11、Python 3.14.6、DuckDB 1.5.6、16 逻辑 CPU 环境下，5 万条合成订单和 100323 条商品明细的五次独立冷数据库装载中位数为 5.105932 秒，约 9792.53 条订单事件/秒；每轮提交后都会重新核对行数和精确 GMV。相同 1000 条输入相对 `af54c57` 的逐行实现从 27.393944 秒降至 0.206895 秒，中位数提升 132.41 倍。完整逐轮数据、方法和限制见[性能证据](docs/evidence/offline-warehouse-performance.md)。这些数字只代表记录环境下的本地批量装载，不是生产 SLA。

仅发送 20 条参考事件不足以关闭第一分钟窗口：最后一个事件时间为 `10:00:57`，减去 10 秒乱序容忍后，Watermark 仍早于 `10:01:00`。因此真实验收应使用一键脚本；它创建独立的单分区 Topic 和 ClickHouse 数据库，在业务批次之后发送 3 条下一分钟事件推进 Watermark，然后轮询 10 个指标键并执行精确对账：

```powershell
./scripts/e2e-acceptance.ps1
```

脚本要求 Docker、正在运行的本地 Flink 1.20.1 集群、JDK 17、Maven 和 Python 3.11。证据写入 `build/e2e/<run-id>/`；Flink 作业始终尝试取消，Topic 与测试数据库默认定向删除，Compose 基础服务不会被脚本停止。当前开发机不具备 Docker，但 GitHub Actions 已下载并校验官方 Flink 1.20.1、启动单节点集群并真实运行脚本；[证据运行 37189195478](https://github.com/ZliY221/Real-time-data-warehouse-and-business-analysis-platform-for-e-commerce/actions/runs/37189195478) 的五个 Job 全部通过。该运行保存 90 天的脱敏 Artifact，只包含预期/实际聚合指标、对账报告和 manifest，不包含原始事件或迟到事件标识；下载审计确认其中 5 个文件、10 个指标键全部匹配，SHA-256 为 `b58e134b7ddf5ca32e79632103f73fc8b37b4675708f693e14d713b32aa5901a`。

## FastAPI 查询服务

先启动 ClickHouse，然后在另一个 PowerShell 窗口启动只监听本机回环地址的 API：

```powershell
./scripts/clickhouse-up.ps1
./scripts/api-up.ps1
```

可用接口：

- `GET /health`：同时检查 API 与 ClickHouse 连通性；数据库不可用时返回 `503` 和稳定错误码。
- `GET /api/v1/metrics/minutes`：查询分钟明细，支持 `start`、`end`、`region`、`channel`、`limit`。
- `GET /api/v1/metrics/summary`：按相同时间和维度条件汇总订单量、GMV、客单价和最新处理时间。
- `GET /api/v1/metrics/timeseries`：按时间桶汇总趋势；`auto` 会依据范围选择 `1m`、`5m`、`15m` 或 `1h`。
- `GET /api/v1/metrics/breakdown`：按白名单中的 `region` 或 `channel` 维度汇总排行。
- `GET /api/v1/quality/runs`：读取最近质量门禁摘要，支持 `limit` 和可选的 `passed` 过滤。
- `GET /api/v1/quality/trend`：按必填的 `rule_id` 读取观测值、阈值和通过状态趋势。
- `GET /docs`：FastAPI 自动生成的交互式 OpenAPI 文档。

未提供时间参数时默认查询最近 24 小时；单次范围最多 31 天，明细和质量历史最多返回 500 行。地区、渠道、时间和条数都通过 ClickHouse 命名参数绑定，不直接拼接用户输入；质量查询同样使用 SQLite 参数绑定。金额在 JSON 中以十进制字符串返回，避免浏览器端二进制浮点误差。质量 API 只返回摘要和绘图必需的指标，并把输入路径缩减为文件名；SQLite 不可用时返回稳定错误码，不泄露内部异常。

API 默认读取 `CLICKHOUSE_HTTP_URL=http://localhost:8123`、`CLICKHOUSE_USER=default`、`CLICKHOUSE_DATABASE=ecommerce`，密码只从 `CLICKHOUSE_PASSWORD` 环境变量读取。由于本机没有 Docker，API 到真实 ClickHouse 的联调仍属于待验收项。

## ECharts 经营看板

真实数据模式下启动 ClickHouse 和 API，然后访问 `http://127.0.0.1:8000/dashboard`：

```powershell
./scripts/clickhouse-up.ps1
./scripts/api-up.ps1
```

本机暂时没有 Docker 时，可以使用明确标注的内存预览模式检查界面和交互：

```powershell
./scripts/dashboard-preview.ps1
```

预览页面会显示“演示数据 · 非实时”和说明横幅；这些数据只用于界面展示，不能作为 Kafka、Flink 或 ClickHouse 已经真实运行的证据。

看板功能包括：

- 近 1、6、24 小时快捷范围，以及自定义开始和结束时间。
- 地区、渠道筛选和手动刷新。
- GMV、有效订单量、客单价、数据新鲜度四项 KPI。
- 成交额与订单量趋势、地区排行、渠道构成和最近分钟明细。
- 最近质量门禁状态、通过率、失败规则数、异常计数和渠道分布漂移阈值趋势。
- 空数据、参数错误、分析存储不可用和加载中状态。
- 经营指标与质量历史独立降级：一侧不可用时，另一侧仍可展示。
- 图表 ARIA 描述、纹理辅助、数据表替代视图、键盘焦点、深色模式和减少动画。

ECharts 锁定为 6.1.0，通过带 SHA-384 完整性校验的 jsDelivr 地址加载；页面 CSP 只允许本站资源和该固定脚本来源。首次加载看板需要访问该 CDN。浏览器验收覆盖 375、768、1024、1440 像素宽度，均无横向溢出，并验证了深色模式、减少动画和筛选刷新。

## 简历表述原则

简历可以写“在 GitHub Actions 单节点隔离环境完成 Kafka → Flink → ClickHouse 链路及 10 个指标键批流一致性验收”，并附运行链接。仍不能写生产级、端到端 exactly-once、真实业务 TPS/SLA、长期稳定运行或本机 Docker 部署经验。

