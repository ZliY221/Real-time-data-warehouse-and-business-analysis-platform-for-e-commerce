# Flink 运行指标 CI 证据

## 可追溯信息

- Git 提交：`7d6b93b7241bd31cfaca602183828f8c92014370`
- GitHub Actions：[run 38039610557](https://github.com/ZliY221/Real-time-data-warehouse-and-business-analysis-platform-for-e-commerce/actions/runs/38039610557)
- Artifact：`e2e-evidence-38039610557-1`（保留期由 GitHub Actions 配置决定）
- 采集时间：`2026-10-10T08:59:31.058Z`
- `flink-runtime.json` SHA-256：`536edcd766db08f30c0c438b82c501a8d3b0f4e65f07b648bdc8e864e0d7b0c4`
- `report.json` SHA-256：`fad226f70f0506504f9ea03498641dab29c99d0e3e709826d36f445253c120a2`

## 已验证结果

| 项目 | 结果 |
| --- | ---: |
| CI Job | 5/5 成功 |
| Job 状态 | RUNNING（采样时） |
| Job uptime | 11,090 ms |
| Job 重启 | 0 |
| Checkpoint | 1 完成、0 失败，最近一次 67 ms |
| 有运行指标的 Vertex | 3/3 |
| 事件去重 Vertex | 23 条输入、23 条输出 |
| 分钟聚合 Vertex | 23 条输入 |
| 最大反压 | 0 ms/s，等级 `ok` |
| 脱敏检查 | 不含事件载荷和异常正文 |

Source Vertex 输出 23 条，包括 20 条业务事件和 3 条只用于推进 Watermark 的事件。事件去重 Vertex 的 task 级输入/输出均为 23。采集器优先选择每个 Subtask 不带算子前缀的 task 指标，避免链式 Vertex 同时暴露 task 与 operator 同名序列时重复累计。

## 证据边界

这是 GitHub 托管 Runner 上的单节点、短时、单次快照，证明真实 Kafka → Flink → ClickHouse 验收期间能够采到任务、Checkpoint 和反压指标。它不是吞吐压测，不能据此声称生产级 TPS、长期稳定性、Exactly-once 或高可用。分档限速生产和持续采样仍属于下一阶段。
