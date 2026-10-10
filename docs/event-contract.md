# 事件契约与可复现数据

## 本单元目标

完成本单元后，应能够解释：

1. 为什么数据平台需要事件契约，而不能只约定“发送一段 JSON”。
2. `event_time` 和 `ingest_time` 有什么区别。
3. 为什么金额不能使用二进制浮点数直接累计。
4. 为什么测试数据需要固定随机种子。
5. JSON Schema 和业务校验为什么需要同时存在。

## 代码阅读顺序

1. `docs/data-dictionary.md`：先理解字段和业务规则。
2. `schemas/order_created_v1.json`：观察机器可读契约。
3. `src/event_generator/generator.py`：理解确定性数据生成。
4. `src/event_generator/validation.py`：理解跨字段业务校验。
5. `tests/test_generator.py`：理解如何把规则变成可重复验证的证据。

## 核心概念

### 事件信封与业务载荷

事件信封描述“这条消息是什么、何时发生、来自哪里”；`payload` 描述订单本身。分开设计后，公共处理逻辑可以统一读取 `event_id`、`event_type` 和时间字段，不必理解每一种业务载荷。

### 事件时间与进入时间

- `event_time`：业务动作实际发生的时间，后续经营指标使用它进行窗口统计。
- `ingest_time`：消息进入数据链路的时间，可用来估算上游传输延迟。

如果使用处理时间，同一批历史事件在不同机器或不同运行时刻可能得到不同的窗口结果。使用事件时间和明确的 Watermark 策略，结果更容易重放和验证。

### 确定性生成

随机数据并不等于不可重复。生成器使用固定随机种子、固定起始时间和基于名称的 UUID。相同输入会产生相同输出，因此测试失败时可以稳定复现。

### 金额精度

代码使用 `Decimal` 计算金额，并在 JSON 中以两位小数字符串传输。这样可以避免 `0.1 + 0.2` 一类二进制浮点误差，并让不同语言按同一规则解析。

### 结构校验与业务校验

JSON Schema 适合校验字段、类型、枚举和格式。项目内校验器还会检查跨字段关系，例如：

- `ingest_time` 不能早于 `event_time`。
- 商品行金额等于数量乘以单价。
- 订单总额等于所有商品行金额之和。

## 动手练习

### 练习一 重放数据

用相同参数生成两份文件，然后比较文件哈希。两份文件应完全一致。

```powershell
$env:PYTHONPATH = "src"
python -m event_generator.cli --count 100 --seed 7 --output data/generated/a.ndjson
python -m event_generator.cli --count 100 --seed 7 --output data/generated/b.ndjson
Get-FileHash data/generated/a.ndjson
Get-FileHash data/generated/b.ndjson
```

### 练习二 制造错误

复制一条示例事件，把 `total_amount` 改成 `0.01`，然后调用 `validate_order_event`。观察返回的错误信息，并说明为什么只检查字段类型无法发现这个问题。

### 练习三 增加渠道

尝试增加 `store` 渠道。需要同时修改生成器枚举、JSON Schema 和文档。运行测试，观察“枚举与 Schema 不漂移”测试如何帮助定位遗漏。

## 设计验证

1. Kafka 已经保证分区内有序，为什么仍然可能出现业务事件乱序？
2. `event_id` 和 `order_id` 是否可以合并？为什么？
3. 使用随机 UUID 会对测试复现造成什么影响？
4. 如果订单发生修改，应覆盖原事件还是新增事件？
5. Schema 兼容性中的向后兼容和向前兼容分别是什么意思？

## 完成标准

- 能在不看答案的情况下解释五个核心概念。
- 能运行生成器和全部测试。
- 能完成至少一个动手练习，并把变更保留在独立 Git 分支。

