# 学习单元 17：可复现负载输入与 Flink 运行快照

## 为什么先做证据工具

“生成 1 万条数据”不是“系统达到每秒 1 万条吞吐”。完整压力测试至少要区分：事件本身的业务时间密度、Kafka 生产速率、Flink 实际处理速率、ClickHouse 落库完成时间，以及采样时的机器与并行度。当前单元先固定输入和采集口径，避免后续把生成参数误写成性能结果。

## 确定性负载数据

生成 10,000 条、事件时间密度为每秒 1,000 条的输入：

```powershell
./scripts/generate-load-dataset.ps1 `
  -Count 10000 `
  -EventTimeRate 1000 `
  -Profile ci-baseline
```

输出位于 Git 忽略的 `build/load/ci-baseline/`：

- `events.ndjson`：通过 v1 契约校验的合成订单；
- `manifest.json`：数量、种子、起点、事件时间跨度、字节数和 SHA-256；
- `claims.measured_publish_rate=false`：明确没有把事件时间密度冒充发送速率；
- `claims.measured_pipeline_throughput=false`：明确没有把输入规模冒充链路吞吐。

相同数量、种子、起点和事件时间密度会产生字节级相同的数据集。清单只记录文件名，不泄露本机绝对路径。

## Flink 运行快照

Flink 1.20.1 提供只读 REST 接口，可读取 Job、Vertex 指标、反压和 Checkpoint 统计。作业运行时执行：

```powershell
./scripts/collect-flink-runtime.ps1 `
  -JobId 0123456789abcdef0123456789abcdef
```

采集器记录：

- Job 状态、运行时长、重启次数、uptime 和 downtime；
- 每个 Vertex 的输入/输出总数及每秒速率；
- busy、idle 和 backpressured 毫秒数；
- Vertex 反压等级与最大子任务反压比例；
- Checkpoint 完成、失败、进行中和恢复次数，以及最近一次完成摘要。

Vertex 指标 ID 在真实 REST 响应中可能带子任务或算子前缀。采集器先读取可用 ID，再按指标名后缀选择并归组：记录数和每秒速率跨序列求和，busy、idle 与 backpressured 时间取最大值用于观察最忙或最受压的子任务。快照额外保留最多 50 个只含 `record/busy/idle/backpress` 关键词的候选 ID，便于发现版本或拓扑导致的命名差异，不保存其他任意指标。Flink 1.20.1 的独立 Vertex 反压接口可能返回 `deprecated`；此时使用 `backPressuredTimeMsPerSecond / 1000` 推导比例和 `ok/low/high` 等级，并在报告里标记来源为 `task_metric`，不把不可用接口写成零反压。

默认只允许访问 `localhost`、`127.0.0.1` 或 `::1`，URL 不能携带凭据。JSON 和 Markdown 结果不保存事件载荷、异常正文、Checkpoint 外部路径或服务凭据。端到端 CI 会在取消作业之前采集一次快照，并将其与对账报告一起作为 90 天脱敏 Artifact 上传。

## 当前证据与下一步

当前已经完成：

1. 负载数据的确定性、契约、参数边界和清单脱敏测试；
2. REST 响应解析、数值规范化、远程主机保护和敏感字段排除测试；
3. 10,000 条本地输入生成实验；
4. 完整链路 CI 中的真实 Flink REST 探针接入，并在采样前最多等待 20 秒观察已完成 Checkpoint。

仍未完成分档限速生产、连续采样、端到端完成时间计算与瓶颈结论。因此现在可以说“实现可复现负载输入和 Flink 运行指标采集”，不能写“系统吞吐达到某个 TPS”或“无反压稳定运行”。

下一阶段将增加低、中、高三档限速发布，按固定间隔连续采样，并把 Kafka 发送结果、Flink 指标、ClickHouse 最终行数和运行环境合并为一份性能报告。
