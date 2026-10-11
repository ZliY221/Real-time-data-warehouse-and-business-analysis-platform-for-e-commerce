# 事件契约与可复现数据

## 设计范围

事件契约同时定义字段结构、枚举、时间语义、金额格式和跨字段业务规则。数据生成器使用固定随机种子、固定起始时间和确定性 UUID，保证相同参数产生字节级一致的输入。

## 相关实现

1. `docs/data-dictionary.md`：字段和业务规则。
2. `schemas/order_created_v1.json`：机器可读契约。
3. `src/event_generator/generator.py`：确定性数据生成。
4. `src/event_generator/validation.py`：跨字段业务校验。
5. `tests/test_generator.py`：契约与生成结果测试。

## 契约设计

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

## 运行验证

### 确定性重放

使用相同参数生成两份文件并比较哈希；两份文件必须完全一致。

```powershell
$env:PYTHONPATH = "src"
python -m event_generator.cli --count 100 --seed 7 --output data/generated/a.ndjson
python -m event_generator.cli --count 100 --seed 7 --output data/generated/b.ndjson
Get-FileHash data/generated/a.ndjson
Get-FileHash data/generated/b.ndjson
```

### 跨字段校验

将示例事件的 `total_amount` 改为 `0.01` 后调用 `validate_order_event`。校验器应报告订单总额与商品行金额不一致。

### 枚举一致性

新增渠道时必须同步修改生成器枚举、JSON Schema 和数据字典；枚举一致性测试会拦截遗漏项。

## 设计约束

- Kafka 只保证分区内记录顺序，网络重试、上游缓存和跨分区写入仍可能造成业务时间乱序。
- `event_id` 标识一次事件，`order_id` 标识业务实体，两者不能合并。
- 测试数据禁止使用不可控随机 UUID，以保证失败可复现。
- 订单修改应产生新事件并保留原始事实，不覆盖历史事件。
- 契约演进必须单独评估生产者与消费者的向前、向后兼容性。

## 验收条件

- 相同参数生成的数据文件哈希一致。
- JSON Schema 与生成器枚举一致。
- 跨字段金额和时间规则均有自动化测试。

