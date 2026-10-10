# 项目面试讲解与证据指南

这份指南用于把项目讲清楚，不用于背诵技术名词。每个回答尽量遵循四步：业务问题、当前设计、仓库证据、真实边界。

## 30 秒项目介绍

> 这是一个面向数据开发岗位的电商数据平台。我先定义可复现的订单事件契约，再用 Kafka 和 Flink 完成解析、事件时间、状态去重、一分钟窗口及异常侧流，使用 ClickHouse 保存实时指标；同一事件批次还能装载到 DuckDB 的 ODS、DIM、DWD、DWS、ADS 离线模型。项目还包含质量门禁、历史趋势和独立批流对账。重点不是组件数量，而是每个粒度、口径和边界都有测试与证据。

## 3 分钟讲解顺序

### 1. 为什么做

课程项目通常只证明“代码能运行”，无法回答重复、乱序、迟到、金额精度、重放和指标正确性。这个项目把这些问题组织成一条可验证的数据工程链路，用于展示数据开发基本功。

### 2. 数据如何流动

```text
Python 固定事件
  → 数据质量门禁
  → Kafka
  → Flink 解析 / Watermark / event_id 去重 / 一分钟窗口
  → ClickHouse 最终指标 + 拒绝和迟到审计表
  → FastAPI
  → ECharts 看板

同一批原始事件
  → Python 离线重算
  → 与 ClickHouse 结果逐键对账

同一批原始事件
  → DuckDB 事务型增量 ETL
  → ODS / DIM / DWD / DWS / ADS
```

### 3. 三个重点设计

第一，金额从事件契约开始使用两位小数字符串，在 Python、Java、ClickHouse 和 API 中分别使用 `Decimal`、`BigDecimal`、`Decimal(18, 2)` 和字符串响应，避免浮点误差。

第二，Flink 用 `event_id` 状态去重和事件时间窗口处理乱序；拒绝、迟到和经营指标分别进入独立 Sink。普通 JDBC Sink 是至少一次，所以 ClickHouse 用稳定键与 `ReplacingMergeTree(version)` 吸收重放，查询通过 `FINAL` 读取最新版本。

第三，使用独立 Python 引擎复刻校验、去重、迟到剔除和分钟聚合，按 `(window_start, region, channel)` 精确核对流式结果。任务成功不等于指标正确，对账才是业务验收。

第四，离线数仓明确区分订单粒度和订单商品明细粒度，通过文件哈希批次键、事件幂等与冲突回滚支持可重跑；DWS 从订单粒度汇总 GMV，ADS 从商品事实用窗口函数生成品类排名，避免一对多连接重复计算订单总额。

### 4. 工程化证据

- Python/API/数据质量/对账/离线数仓、JavaScript、Java/Flink 分层测试，共 129 项。
- GitHub Actions 配置 Python、Flink、Kafka、ClickHouse 冒烟与完整链路五个 Job。
- 固定版本依赖、最小权限、超时、失败清理和可重复样例。
- 里程碑提交保留从事件契约到端到端验收脚本的演进。

### 5. 主动说明边界

> 当前 GitHub Actions 已通过 Python、Java/Flink、Kafka 生产消费、ClickHouse 替换语义和完整链路五个 Job。隔离验收真实提交了 Flink 作业，发送 20 条业务事件和 3 条 Watermark 推进事件，最终 10 个指标键全部匹配；但这是单节点受控批次，不能扩大成生产高可用、端到端 exactly-once 或性能 SLA。

主动说明边界不会削弱项目，反而能证明能够区分代码实现、自动化测试和真实环境证据。

## 五分钟演示

### 当前电脑可演示

1. 展示 README 架构图和进度边界。
2. 运行全部自动化测试：

   ```powershell
   ./scripts/test-all.ps1
   ```

3. 构建离线维度数仓并查看聚合验收报告：

   ```powershell
   ./scripts/offline-warehouse-build.ps1
   ```

4. 展示批流对账的离线基准：

   ```powershell
   $env:PYTHONPATH = "src"
   python -m reconciliation.cli baseline `
     --events data/sample/order_events.ndjson `
     --output build/reconciliation/expected_metrics.ndjson
   ```

5. 启动明确标注的看板预览：

   ```powershell
   ./scripts/dashboard-preview.ps1
   ```

6. 打开正常和问题质量报告，解释退出码与失败规则。

### 具备 Docker 和 Flink 后演示

```powershell
./scripts/e2e-acceptance.ps1
```

重点展示 `build/e2e/<run-id>/report.md`、`manifest.json`、实际指标和终端版本信息。不要只展示容器列表或一张看板截图。

## 高频技术问题

### 1. 为什么选择 Kafka、Flink 和 ClickHouse

Kafka 负责将事件生产与计算解耦，并提供可重放日志；Flink 适合有状态去重、事件时间和窗口计算；ClickHouse 适合分钟级聚合结果的分析查询。当前数据量并不需要这些组件，选择它们是为了完整演练目标岗位常见的数据语义和故障边界，而不是宣称个人电脑拥有生产规模。

证据：`compose.yaml`、`KafkaOrderMetricsJob.java`、`001_schema.sql`。

### 2. `event_time` 和 `ingest_time` 有什么区别

`event_time` 是业务发生时间，用于窗口归属；`ingest_time` 是模拟进入链路时间，用于评估及时性。若按处理时间聚合，相同事件在机器快慢或重放时可能进入不同窗口，结果不可重复。

证据：`schemas/order_created_v1.json`、`OrderMetricsPipeline.java`。

### 3. Watermark 的 10 秒是什么意思

Watermark 近似表示系统认为不会再看到早于某个事件时间的数据。固定 10 秒乱序容忍意味着最大已见事件时间减去约 10 秒后推进窗口；它是实验参数，不是生产最佳值，需要根据真实延迟分布权衡完整性与出数速度。

### 4. 为什么 20 条样例不能直接触发第一分钟窗口

最后一条事件是 `10:00:57`，减去 10 秒后 Watermark 仍早于 `10:01:00`。Kafka Source 又是无界流，不会因为暂时没消息就发出结束 Watermark。因此验收脚本再发送 `10:01:15` 起的事件推进 Watermark，而不是靠睡眠假设窗口已经关闭。

证据：`e2e-acceptance.ps1`、`test_acceptance_trigger_advances_watermark_past_the_business_window`。

### 5. `withIdleness` 能不能解决上面的问题

不能。Idleness 用于把长时间没有数据的分区排除出全局 Watermark 最小值，避免它阻塞其他活跃分区；它不会凭空产生更大的业务时间。端到端验收使用单分区 Topic，消除分区器与空闲超时造成的不确定性。

### 6. 如何处理重复事件

Flink 按 `event_id` 做 keyed state 去重，第一次出现后写入带 TTL 的状态。TTL 防止状态无限增长，但过短会让旧事件再次通过，过长会增加状态体积。当前 24 小时是可配置实验值，需要结合最大重放周期和状态规模重新确定。

证据：`DeduplicateByEventIdFunction.java`、`KafkaJobConfig.java`。

### 7. 如何处理迟到事件

超过窗口允许时间的事件进入 Flink `sideOutputLateData`，并写入 `late_order_events`，不静默丢失。当前默认 allowed lateness 为 0，迟到事件不回补主指标；离线对账读取其 `event_id` 并从基准中剔除，保持口径一致。

证据：`OrderMetricsPipeline.java`、`ClickHouseLateEventStatement.java`。

### 8. 开启 exactly-once checkpoint 后是不是端到端 exactly-once

不是。Checkpoint 保证 Kafka Source、算子状态和恢复点的一致性，但普通 JDBC Sink 使用 `buildAtLeastOnce`，没有与 ClickHouse 建立跨系统两阶段事务。项目只能说明至少一次写入加稳定键版本替换，不能宣传端到端 exactly-once。

### 9. 为什么使用 `ReplacingMergeTree(version)`

至少一次重试或作业重放可能对同一业务键产生多个版本。分钟指标用窗口、地区、渠道作为稳定键，异常数据用指纹或 `event_id`；`ReplacingMergeTree(version)` 最终保留较新版本，查询使用 `FINAL` 得到当前确定结果。它不是同步 upsert，后台物理合并前旧版本仍存在。

### 10. 版本为什么使用处理时间加单调递增

Statement Builder 以当前毫秒为基础，并保证单实例内后一个版本严格更大。异常 Sink 显式使用并行度 1，适合当前低量演示。扩展并行度前需要改用跨实例可比较的版本，例如来源 offset、集中序列或包含分区身份的复合版本。

### 11. 为什么拒绝事件不保存完整原文

坏消息可能意外包含姓名、邮箱、地址或令牌。数据库只保存带域前缀的 SHA-256 指纹、有限错误分类、字节数和时间版本；`toString()` 也不输出原文或解析器原因。这是数据最小化，不代表哈希值是加密后的原文，低熵内容仍可能被枚举。

### 12. 拒绝事件数量为什么不是精确发生次数

相同坏载荷产生同一指纹，`FINAL` 后只保留最新一条，所以当前汇总表示不同坏载荷签名数。若要精确计算每次发生，应从 Kafka Source 保留 topic、partition、offset，以它们作为每条投递的稳定身份。

### 13. 为什么金额不用 `double`

二进制浮点不能精确表示许多十进制金额。事件以两位小数字符串传输，Python 使用 `Decimal`，Java 使用 `BigDecimal`，ClickHouse 使用 `Decimal(18, 2)`，API 继续返回字符串。批流对账要求分币完全一致，不用容差掩盖错误。

### 14. 数据质量门禁检查什么

配置固定支持契约、完整性、唯一性、金额范围、进入及时性和分类分布漂移六类规则。正常样例通过，问题样例能同时触发六类失败；CLI 用 `0/1/2` 区分通过、业务质量失败和配置或运行错误。

### 15. 批次质量门禁和 Flink 侧流是否重复

不重复。批次门禁适合发布前、回放前和 CI，对整体完整率、重复率、分布等进行检查；Flink 侧流负责实时链路中的单条解析失败和窗口迟到。当前两者分别存储，尚未统一成生产监控与告警平台。

### 16. SQLite 历史如何避免重复运行记录

报告的稳定内容生成哈希 `run_id`，运行和规则明细在同一事务中幂等写入。Windows 测试还发现连接上下文不会自动关闭文件句柄，因此实现显式关闭连接，避免数据库文件被长期占用。

### 17. FastAPI 如何避免 SQL 注入

时间、地区、渠道和条数作为 ClickHouse 类型化命名参数传递；维度列名和时间桶只能从服务端固定白名单选择。用户输入不会直接拼接成 SQL 结构，查询范围、点数和返回条数也有上限。

证据：`src/metrics_api/repository.py`、`tests/test_metrics_repository.py`。

### 18. 为什么 API 返回金额字符串

JavaScript Number 仍然是二进制浮点。API 返回十进制字符串，让显示层只负责格式化，不在浏览器中重新计算或改变金额精度。

### 19. 看板预览数据能不能当成链路成果

不能。预览模式使用确定性内存仓库，并通过响应头和页面提示明确标注。它证明页面布局、交互、降级和可访问性，不证明 Kafka、Flink 或 ClickHouse 已经运行。

### 20. 批流对账如何定位错误

Python 基准和 ClickHouse 最终结果按相同业务键比较。报告区分离线有而实时没有、实时额外出现、订单量不同、GMV 不同以及两项都不同。这样可以把消费或窗口缺失、旧数据污染、去重错误和金额映射问题分开排查。

### 21. 为什么对账不是同一份代码自我证明

基准从原始 NDJSON 用 Python 独立重算，实时结果由 Java/Flink 和 ClickHouse 产生，两个实现语言和执行路径不同。当前本机的“基准对自身”只用于验证 CLI 和报告；只有真实导出的 ClickHouse 文件参与比较，才构成批流证据。

### 22. 测试分哪几层

Python 测试覆盖事件、质量、API、存储边界和对账；Java DataStream 测试覆盖解析、Watermark、去重、窗口和侧流；JavaScript 测试覆盖金额、查询参数、状态文案和质量计算；Kafka 与 ClickHouse 冒烟脚本验证真实容器行为。远程 CI 还会下载校验 Flink 1.20.1、启动单节点集群、提交真实作业并执行 10 个指标键批流对账。

### 23. 项目中真实发现过什么问题

最典型的是端到端验收时发现 20 条样例无法推进 Watermark 关闭窗口。如果只看代码或固定等待，很容易误判为 JDBC Sink 故障。我通过计算最大事件时间、乱序界限和窗口终点定位原因，再引入单分区隔离 Topic 与下一分钟推进事件，并为时间关系编写测试。

### 24. 如果数据量扩大，先改哪里

先依据监控和压测结果定位瓶颈，而不是提前堆组件。可能需要增加 Kafka 分区和 Flink 并行度、重新设计异常 Sink 的跨实例版本、评估状态 TTL 与 checkpoint 体积、避免高频 `FINAL` 查询、增加物化汇总或投影，并为 API 增加连接池和缓存。当前没有压测证据，不给出虚构吞吐数字。

### 25. 如果投入生产，还缺什么

至少缺少安全认证与密钥管理、Schema Registry 或兼容性治理、生产级 checkpoint/savepoint 存储、高可用部署、监控告警、数据保留与删除策略、容量和故障压测、回填流程、权限审计及真实 SLA。当前项目定位是可验证作品集，不是生产系统。

### 26. 离线数仓为什么选 DuckDB，能不能说会 Hive/Spark 数仓

选择 DuckDB 是因为评审者不需要 Docker 或集群就能复现分析型 SQL、事务、Decimal、窗口函数和分层模型。它证明我实际处理过粒度、维度键、增量幂等、坏数据隔离和一对多重复汇总风险，但不能直接证明分布式 Shuffle、容错、分区文件或小文件治理能力。因此简历写“使用 DuckDB 实现本地离线维度数仓”，不改写为 Hive/Spark 生产经验。

证据：`src/offline_warehouse/`、`tests/test_offline_warehouse.py`、`docs/study-16-offline-dimensional-warehouse.md`。

### 27. 离线装载为什么能提升 132 倍，这个数字可靠吗

第一版在 Python 循环里反复查询维度并逐行写订单和商品事实，主要成本是解释器与数据库之间的大量往返。优化后仍由 Python 做业务契约和冲突判断，但将合法事件一次暂存，由 DuckDB 使用连接、`INSERT ... SELECT` 和 `UNNEST` 做集合式处理。相同 1000 条固定输入、相同机器、三次独立冷数据库运行，中位数从 27.393944 秒降到 0.206895 秒，即 132.41 倍；旧版本在 `af54c57` 临时工作树中重跑。这个倍数只说明当前逐行实现被集合式 SQL 替代后的差异，不代表生产系统或任意数据量都提升 132 倍。

证据：`docs/evidence/offline-warehouse-performance.md`、`src/offline_warehouse/benchmark.py`。

### 28. 生成器配置每秒 1000 条，能否说明链路有 1000 TPS

不能。这个参数只控制合成事件的业务时间密度，用于把大量事件集中在可控的事件时间范围；它不控制 Kafka 实际发送节奏，也没有测量 Flink 或 ClickHouse 的完成时间。清单因此显式记录 `measured_publish_rate=false` 和 `measured_pipeline_throughput=false`。真实吞吐必须同时记录限速发布结果、Flink 输入输出速率与反压、Checkpoint、ClickHouse 最终结果和运行环境。

证据：`src/load_testing/`、`tests/test_load_testing.py`、`docs/study-17-flink-runtime-observability.md`。

## 三个 STAR 故事

### 故事一：Watermark 导致窗口没有输出

- **Situation：** 计划用固定 20 条事件做端到端验收。
- **Task：** 确保第一分钟指标能确定落库并与离线基准对账。
- **Action：** 计算最后事件时间与 Watermark，发现无法越过窗口终点；设计单分区隔离 Topic，添加下一分钟推进事件、轮询、JobID 取消和定向清理，并补测试。
- **Result：** 验收流程不再依赖盲目等待，能够明确区分窗口未触发与 Sink 故障；远程单节点真实运行得到 10 matched、0 mismatched。

### 故事二：质量历史文件在 Windows 被占用

- **Situation：** SQLite 测试结束后数据库文件仍可能被占用。
- **Task：** 保证测试可重复、临时文件可以删除。
- **Action：** 确认连接上下文只负责提交与回滚，不保证立即关闭；增加显式连接生命周期管理并覆盖失败路径。
- **Result：** 幂等历史测试稳定通过，也形成了资源生命周期而非只看业务结果的工程意识。

### 故事三：拒绝数据的隐私边界

- **Situation：** Flink 侧流最初包含原始坏消息和解析原因。
- **Task：** 在保留诊断能力的同时减少长期泄露面。
- **Action：** 数据库只保存域分离 SHA-256 指纹、错误类型和字节数，控制台字符串移除原文，增加字段绑定和不泄露测试。
- **Result：** 仍能判断坏载荷是否重复，同时不把完整未知数据写入审计表。

## 简历表述与证据

| 可以写的事实 | 主要证据 | 暂时不能写的扩大表述 |
| --- | --- | --- |
| 实现 Flink 事件时间、去重、窗口与异常侧流 | Java 源码、28 项 Java/Flink 测试 | 生产级实时平台 |
| 实现至少一次 JDBC Sink 与版本替换 | Sink、DDL、Statement 测试 | 端到端 exactly-once |
| 实现 FastAPI 与响应式 ECharts 看板 | API/前端源码、浏览器验收、测试 | 真实看板已连接完整链路 |
| 实现六类质量门禁与历史趋势 | 配置、正常/失败样例、SQLite、API | 生产级实时质量平台 |
| 在单节点 CI 完成独立批流对账和隔离验收 | Python 引擎、脚本、运行 `37189195478` 及脱敏 Artifact | 生产级、长期运行、性能 SLA |
| 实现五层离线维度数仓与增量 ETL | DuckDB 模型、装载脚本、聚合报告、事务测试 | Hive/Spark 生产数仓经验 |
| 配置五个 Job 的 GitHub Actions | `.github/workflows/ci.yml`、成功运行记录 | 团队级发布流水线经验 |

## 里程碑证据索引

| 提交 | 内容 |
| --- | --- |
| `4926369` | 事件契约、生成器与业务校验 |
| `0bfddbc` | Kafka 本地工作流 |
| `5f101f7` | Flink 事件时间与窗口核心 |
| `fe609c3` | JSON 拒绝和迟到侧流 |
| `8378c86` | 分层持续集成 |
| `66be60f` | KafkaSource 与 checkpoint 作业入口 |
| `b3d07d6` | ClickHouse 指标 Sink |
| `1e609d6` | FastAPI 查询服务 |
| `a90ecc4` | ECharts 经营看板 |
| `0dd0025` | 配置化数据质量门禁 |
| `37ac96d` | SQLite 质量历史 |
| `dbf7858` | 质量诊断 API 与看板 |
| `f072e09` | 异常侧流 ClickHouse 持久化 |
| `ef119de` | 批流指标对账 |
| `eb69541` | 隔离端到端验收流程 |
| `45074de` | 项目讲解、追问与证据指南 |

## 面试前自检

- 能不用文档画出链路和三张 ClickHouse 表。
- 能区分 ODS 订单粒度、DWD 商品明细粒度及各自正确的聚合指标。
- 能解释同文件重跑、跨批次重复与同 ID 冲突的不同处理方式。
- 能计算为什么 20 条事件无法触发第一分钟窗口。
- 能区分 checkpoint exactly-once、Sink at-least-once 和版本替换。
- 能解释每个稳定键为什么这样选择。
- 能说明 `FINAL` 的作用和代价。
- 能讲清至少一个真实发现并修复的问题。
- 能指出预览数据、静态配置、单元测试和真实运行证据的区别。
- 不背性能数字；没有脚本、环境和原始报告就不写。
- 遇到没做过的问题，回答“当前没有实现，我会先验证……”，不要虚构。
