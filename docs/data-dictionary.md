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

