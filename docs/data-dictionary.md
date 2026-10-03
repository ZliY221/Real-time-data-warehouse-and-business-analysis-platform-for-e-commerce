# 订单事件数据字典

事件主题：`order-events`

事件类型：`order_created`

契约版本：`1.0`

## 事件信封

| 字段 | 类型 | 必填 | 含义 | 示例 |
| --- | --- | --- | --- | --- |
| schema_version | string | 是 | 事件契约版本 | `1.0` |
| event_id | string | 是 | 全局唯一事件标识 | `evt_...` |
| event_type | string | 是 | 事件类型 | `order_created` |
| event_time | string | 是 | UTC 业务发生时间 | `2026-10-02T10:00:00Z` |
| ingest_time | string | 是 | UTC 模拟入链时间 | `2026-10-02T10:00:03Z` |
| source | string | 是 | 事件来源 | `order-service` |
| payload | object | 是 | 订单业务数据 | 见下表 |

## payload

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| order_id | string | 是 | 批次内唯一 |
| user_id | string | 是 | 模拟匿名标识，不对应真人 |
| region | string | 是 | 枚举：辽宁、北京、上海、广东、四川 |
| channel | string | 是 | 枚举：app、web、mini_program |
| currency | string | 是 | 当前固定为 CNY |
| total_amount | string | 是 | 两位小数，等于明细金额之和 |
| items | array | 是 | 至少包含一个商品明细 |

## items 元素

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| sku_id | string | 是 | 模拟商品标识 |
| category | string | 是 | 商品分类 |
| quantity | integer | 是 | 1 至 5 |
| unit_price | string | 是 | 两位小数且大于 0 |
| line_amount | string | 是 | `quantity × unit_price` |

## 隐私边界

项目不生成或保存姓名、手机号、详细地址、邮箱、身份证号、设备号等个人敏感信息。所有用户、订单和商品标识均为模拟值。

## ClickHouse 分钟指标表

表名：`ecommerce.minute_metrics`

业务唯一键：`(window_start, region, channel)`

| 字段 | ClickHouse 类型 | 含义 |
| --- | --- | --- |
| window_start | DateTime64(3, UTC) | 一分钟事件时间窗口起点，左闭 |
| window_end | DateTime64(3, UTC) | 一分钟事件时间窗口终点，右开 |
| region | LowCardinality(String) | 地区维度 |
| channel | LowCardinality(String) | 渠道维度 |
| order_count | UInt64 | 去重后的有效订单数 |
| gmv | Decimal(18, 2) | 去重后的成交额，保留两位小数 |
| version | UInt64 | Sink 生成的单调版本，用于替换重放或迟到更新结果 |
| processed_at | DateTime64(3, UTC) | 当前版本写入 Sink 的处理时间 |

表引擎使用 `ReplacingMergeTree(version)`。物理去重是后台异步行为，因此对外查询使用 `ecommerce.minute_metrics_latest` 视图；该视图通过 `FINAL` 获取每个业务键的最新版本，并计算 `average_order_value = gmv / order_count`。

## ClickHouse 拒绝事件审计表

表名：`ecommerce.rejected_order_events`

稳定键：`rejection_id`，即带类型域前缀的原始载荷 SHA-256 十六进制指纹。空值使用 `null:` 域，非空文本使用 `text:` 域，避免空值和字面文本发生语义碰撞。

| 字段 | ClickHouse 类型 | 含义 |
| --- | --- | --- |
| rejection_id | FixedString(64) | 带类型域前缀的原始载荷 SHA-256 单向摘要，用于重放替换 |
| error_type | LowCardinality(String) | `malformed_json`、`invalid_json_shape`、`invalid_field` 或 `business_validation_failed` |
| payload_size_bytes | UInt32 | 原始载荷 UTF-8 字节数；不保存载荷本身 |
| detected_at | DateTime64(3, UTC) | Sink 观察到该拒绝记录的处理时间 |
| version | UInt64 | Sink 生成的单调版本 |

表中不包含 `raw_payload` 和解析器原因。相同载荷会收敛为一条最新记录，因此它表示不同拒绝载荷签名，而不是精确的消息发生次数。

## ClickHouse 迟到事件审计表

表名：`ecommerce.late_order_events`

稳定键：事件契约中的唯一 `event_id`。

| 字段 | ClickHouse 类型 | 含义 |
| --- | --- | --- |
| event_id | String | 合成事件唯一标识，用于重放替换 |
| order_id | String | 合成订单标识 |
| event_time | DateTime64(3, UTC) | 业务事件时间 |
| ingest_time | DateTime64(3, UTC) | 模拟进入链路时间 |
| region | LowCardinality(String) | 地区维度 |
| channel | LowCardinality(String) | 渠道维度 |
| total_amount | Decimal(18, 2) | 订单金额，保持十进制精度 |
| detected_at | DateTime64(3, UTC) | Sink 观察到迟到事件的处理时间 |
| version | UInt64 | Sink 生成的单调版本 |

`ecommerce.event_anomaly_summary` 对两张表执行 `FINAL` 后按分钟、异常类型和原因汇总，供诊断脚本查询。

## 批流对账指标文件

格式：UTF-8 NDJSON / ClickHouse `JSONEachRow`，每行代表一个最终分钟指标键。

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| window_start | UTC ISO 8601 string | 必须对齐整分钟 |
| window_end | UTC ISO 8601 string | 必须等于 `window_start + 1 minute` |
| region | string | 使用事件契约地区枚举 |
| channel | string | 使用事件契约渠道枚举 |
| order_count | non-negative integer | 去重、校验并剔除迟到事件后的订单量 |
| gmv | decimal string | 非负且恰好两位小数 |

文件中不包含 `event_id`、`order_id` 或 `user_id`。迟到事件单独导出最小化的 `event_id` 集合，只用于让离线基准采用与实时窗口一致的排除口径。

