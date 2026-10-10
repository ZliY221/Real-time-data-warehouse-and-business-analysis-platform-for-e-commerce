# 架构设计

## 设计原则

项目按“事件契约、消息传输、流式计算、分析存储、查询展示、质量监控”分层。每层先定义输入、输出和验收方法，再选择组件。

## 数据流

```mermaid
sequenceDiagram
    participant Generator as Python 事件生成器
    participant Quality as 数据质量门禁
    participant History as SQLite 质量历史
    participant Kafka as Kafka
    participant Flink as Flink 作业
    participant Store as ClickHouse
    participant Reconcile as 批流对账
    participant Warehouse as DuckDB 离线数仓
    participant API as FastAPI
    participant Dashboard as ECharts 看板

    Generator->>Quality: NDJSON 批次
    Quality-->>Generator: 报告与退出码
    Quality->>History: 运行摘要与规则指标
    Generator->>Kafka: 通过门禁的 order_created v1
    Kafka->>Flink: 按事件时间消费
    Flink->>Flink: 校验 去重 窗口聚合
    Flink->>Store: 分钟级指标 拒绝指纹 迟到事件
    Generator->>Reconcile: 固定批次离线重算
    Generator->>Warehouse: 事务型增量装载
    Store->>Reconcile: FINAL 指标与迟到事件
    Reconcile-->>Generator: 差异报告与退出码
    Warehouse-->>Generator: 分层指标与验收报告
    API->>Store: 参数化查询
    API->>History: 只读质量历史
    Dashboard->>API: 获取经营指标与质量趋势
```

## 事件时间策略

- `event_time` 表示订单在业务系统中发生的时间。
- `ingest_time` 表示事件进入数据链路的模拟时间。
- Flink 从 `event_time` 提取时间戳。
- 第一版使用 bounded out-of-orderness Watermark，初始容忍时间设为 10 秒。
- Kafka 分区超过 60 秒无事件时标记 idle，避免某一空闲分区阻塞整体 Watermark。
- 超过 Watermark 的事件进入迟到事件处理路径，是否回补主指标由实验结果决定并记录。
- Kafka Source 是无界流，仅发送窗口内事件不会自动产生“输入结束”Watermark。端到端验收使用独立单分区 Topic，并在 20 条第一分钟业务事件后发送 3 条 `10:01:15` 起的有效事件，使 10 秒乱序 Watermark 确定越过 `10:01:00` 窗口终点。

这些参数是第一版实验值，不作为生产最佳实践宣称。后续使用生成器构造不同延迟分布，再比较准确性与延迟。

## 一致性与去重

- 生成器保证正常批次内 `event_id` 唯一。
- 测试批次可以主动注入重复事件。
- Flink 使用 `event_id` 作为去重键，并为状态设置合理 TTL。
- 开启 checkpoint，并使用 exactly-once checkpoint consistency mode。
- 端到端 exactly-once 需要同时满足 source、state、sink 和外部系统条件；项目完成前不在文档中宣称端到端 exactly-once。
- 当前 JDBC Sink 允许批量重试，ClickHouse 使用 `(window_start, region, channel)` 稳定键和单调版本降低重放影响。
- 拒绝事件以载荷 SHA-256 指纹、迟到事件以 `event_id` 作为稳定键；ClickHouse 对三个 Sink 都使用 `ReplacingMergeTree(version)`，即时查询通过 `FINAL` 消除重试或重放版本。
- `ReplacingMergeTree` 的物理去重发生在后台合并阶段；即时查询通过包含 `FINAL` 的视图获得最新版本，不能把“最终替换”误写成事务型 upsert。

## 指标定义

| 指标 | 定义 | 维度 |
| --- | --- | --- |
| 订单量 | 去重后的有效订单数 | 分钟、地区、渠道 |
| 成交额 | 去重后的 `total_amount` 之和 | 分钟、地区、渠道 |
| 客单价 | 成交额除以订单量 | 分钟、地区、渠道 |
| 商品销量 | 商品明细 `quantity` 之和 | 分钟、商品 |
| 无效事件数 | 未通过契约或业务规则的事件数 | 分钟、错误类型 |
| 迟到事件数 | Watermark 通过后到达的事件数 | 分钟 |

## 查询服务边界

- FastAPI 只读取 `minute_metrics_latest`，不向分析表写数据，读写职责分离。
- 明细和汇总接口共用开始时间、结束时间、地区、渠道四类筛选条件。
- API 将带时区和不带时区的输入统一为 UTC；无时区输入按 UTC 解释，并限制单次查询不超过 31 天。
- ClickHouse 查询中的值使用 `{name:Type}` 占位符，通过 HTTP `param_name` 传递，用户输入不进入 SQL 结构。
- 金额字段以十进制字符串返回，避免 JavaScript 浮点表示改变金额。
- 空结果返回 `200`、`has_data=false` 或空数组；参数错误返回 `422`；ClickHouse 不可用返回 `503` 和稳定错误码，不向调用者泄露数据库错误详情。
- 当前 API 使用同步标准库 HTTP 客户端。查询规模受范围与条数限制，足以支持个人项目；若后续压测证明阻塞查询成为瓶颈，再依据数据决定是否引入连接池或异步客户端。
- 质量历史接口读取 `quality_runs` 和单规则趋势，最多返回 500 条；公开响应只包含摘要与绘图字段，输入路径只保留文件名。历史库按需创建，并用进程内锁保护首次并行初始化。
- ClickHouse 与 SQLite 采用独立错误边界：任一存储不可用时返回各自稳定的 `503` 错误码，前端可以分别降级。

## 批流对账边界

- `reconciliation` 复用 v1 事件业务校验，并按“解析与校验 → `event_id` 去重 → 剔除迟到事件 → UTC 分钟窗口聚合”的顺序构建离线基准。
- 金额全程使用 `Decimal`，不使用浮点容差掩盖分币差异；订单量和 GMV 都必须精确相等。
- ClickHouse 导出读取 `minute_metrics_latest` 和 `late_order_events FINAL`，使用有类型的时间参数限定最多 7 天，不拼接用户输入。
- 实际指标文件要求每个 `(window_start, region, channel)` 只出现一次，并校验 UTC 时区、一分钟窗口、枚举维度和两位小数金额。
- 报告仅包含窗口、地区、渠道和聚合值，不复制订单、用户标识或事件负载。
- 有界批次内假设 Flink 去重状态未因 TTL 过期；长期运行和 TTL 边界需要单独场景验证。

## 离线维度模型

- `ods.order_events` 的粒度是一条通过契约校验的订单创建事件；订单总额只在这一粒度聚合，避免展开商品后重复累计 GMV。
- `dwd.fact_order_items` 的粒度是一个订单中的一行商品，使用 `(event_id, item_position)` 唯一确定事实记录。
- 地区和渠道使用预置稳定代理键；日期键由 UTC 业务日期生成；商品使用递增代理键并校验同一 SKU 的品类和标价一致性。
- 当前商品维度采用 Type 1 式静态约束：SKU 的品类或标价变化会使批次失败。需要分析历史变化时再引入有效期和当前标记，不能在没有业务需求时声称已实现 SCD2。
- 文件内容 SHA-256 形成 `run_id`，完成过的同一文件直接返回历史统计；新批次中的已有同载荷事件计为重复。
- 事件 ID 对应不同规范化负载属于完整性冲突，整个批次在 DuckDB 事务中回滚；坏 JSON 或契约错误则进入最小披露隔离表并允许其他合法记录继续装载。
- DWS 从订单粒度计算订单数、客户数、GMV 和客单价；ADS 从商品事实计算品类销量与销售额，并用 `DENSE_RANK` 在每日分区内排名。
- DuckDB 是本地嵌入式分析引擎，选择它是为了让评审者无需 Docker 即可复现建模和 SQL 语义；这不等同于 Hive/Spark 集群经验。

## 看板展示层

- FastAPI 在 `/dashboard` 提供同源静态页面，浏览器访问 API 不需要开放跨域权限。
- 看板不会下载最多 500 条分钟明细后重新计算总体指标；总体、时间序列和维度排行分别由 ClickHouse 聚合接口提供，避免截断数据造成图表口径错误。
- `timeseries` 接口会根据查询范围自动选择 1 分钟、5 分钟、15 分钟或 1 小时时间桶，并限制显式细粒度查询最多约 1500 个点。
- `breakdown` 只允许 `region` 和 `channel` 两个枚举值；列名来自服务端白名单，而不是用户输入。
- ECharts 使用固定版本和子资源完整性校验；页面设置 CSP、`nosniff` 和 `no-referrer` 响应头。
- 图表启用 ARIA 与纹理模式，地区和渠道图提供可展开数据表；页面支持键盘焦点、深色模式、减少动画和移动端布局。
- 独立预览入口使用内存数据，并通过 API 响应头驱动醒目的“演示数据”状态，不把预览结果冒充真实链路证据。
- 质量诊断区展示最近门禁、近期通过率、失败规则计数、异常分类和渠道分布漂移；阈值线与失败节点同时编码，表格保留等价文本证据。
- 经营指标和质量历史并行请求、独立处理失败，避免一个数据源异常导致另一类证据被清空。

## 数据质量门禁

- `data_quality` 在进入中间件前对 NDJSON 批次执行配置化规则，规则结构固定，不执行配置中的任意表达式或 SQL。
- 质量报告区分总记录、成功解析、非法 JSON、契约无效、重复和超时记录，并以退出码 `0/1/2` 区分通过、规则失败和运行配置错误。
- 分布规则比较实际分类占比与基线占比的最大绝对偏差，并要求最小样本数，避免把小样本波动误判为稳定分布。
- 报告只输出行号、规则原因和必要异常值，不复制整条事件负载；构建产物写入被 Git 忽略的 `build/data-quality`。
- SQLite 历史库使用 `quality_runs` 与 `quality_rule_results` 两张表、外键和事务保存运行摘要；报告内容哈希形成确定性 `run_id`，相同报告重复写入不会产生重复运行。
- 历史查询限制最多 500 条，所有值使用 SQL 参数绑定；趋势按规则 ID 查询并按时间正序返回，便于后续绘图。
- FastAPI 对历史读取提供运行列表与规则趋势两个只读端点；预览应用使用确定性内存历史，明确标注为演示数据。
- Flink 拒绝侧流只向 ClickHouse 写入载荷指纹、错误类型和大小，迟到侧流写入合成事件字段；不保存原始坏消息或解析器原因。
- 当前批次门禁仍需要脚本触发；SQLite 历史和 Flink 异常账本都不能替代持续调度或生产告警。

## 版本选择

当前已在 Maven 中锁定 Apache Flink 1.20.1、Flink Kafka Connector 3.3.0-1.20、Flink JDBC Connector 3.4.0-1.20、ClickHouse JDBC 0.10.0、Java 11 编译目标和 Jackson 2.19.1，并生成包含 Kafka 与 JDBC 连接器的 shaded 作业 JAR。查询层锁定 FastAPI 0.142.2、Uvicorn 0.54.0 和测试客户端 httpx2 2.13.1；离线数仓锁定 DuckDB 1.5.6；展示层锁定 ECharts 6.1.0。Kafka broker 使用官方 3.9.1 KRaft 镜像，ClickHouse 使用官方 25.8.33.6 镜像；这些版本已在 GitHub Actions 单节点端到端验收中组合通过，但未验证生产集群兼容性与高可用。

