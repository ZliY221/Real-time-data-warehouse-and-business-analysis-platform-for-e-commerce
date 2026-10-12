# 持续集成

## 工作流目标

CI 分层执行 Python、API、数据质量、前端、Flink、Kafka、ClickHouse 和端到端测试。快速测试先运行，中间件测试在基础检查通过后启动；工作流同时限制权限、执行时间和并发运行数量。

## 工作流结构

`.github/workflows/ci.yml` 包含五个 Job：

```text
Python/API/quality/reconciliation/dashboard tests ─┐
                                                   ├─> Kafka smoke test
                                                   ├─> ClickHouse metric and anomaly replacement smoke test
                                                   ├─> Kafka → Flink → ClickHouse → reconciliation acceptance
Java and Flink tests ──────────────────────────────┘
```

- Python Job 验证事件生成器、业务契约、FastAPI、预览仓库、Compose 静态约束、数据质量引擎和批流对账引擎，实际对参考 NDJSON 执行质量门禁并生成离线指标基准，再使用 Node 内置测试运行看板 JavaScript 测试。
- Flink Job 使用 JDK 17 和 Maven 缓存，执行真实 DataStream 测试。
- Kafka Job 在前两个 Job 通过后启动官方 Kafka 容器，执行生产、消费和再次校验，最后始终清理容器与数据卷。
- ClickHouse Job 在前两个 Job 通过后初始化指标表与异常审计表，分别向同一指标键、拒绝指纹和迟到事件键写入两个版本，并验证 `FINAL` 只返回最新版本。
- 端到端 Job 从版本与镜像摘要双重固定的官方镜像提取 Flink 1.20.1 运行时，校验版本后启动单节点集群，创建隔离 Topic 和数据库，提交真实作业，并要求 10 个指标键精确对账通过。

## 安全和资源控制

- 全局 `permissions: contents: read`：普通 Job 只读取代码；端到端 Job 额外获得 `actions: write`，仅用于上传脱敏验收 Artifact，不授予源码、Issue 或 PR 写权限。
- `timeout-minutes`：防止 Maven、Kafka 启动或消费异常时无限占用 Runner。
- `concurrency.cancel-in-progress`：同一分支有新提交时取消旧运行，减少重复消耗。
- `if: ${{ always() }}`：即使冒烟测试失败，也执行 Kafka 清理步骤。
- 所有依赖版本和容器镜像均固定，不使用 `latest`。
- 完整链路成功后只上传聚合指标、对账报告和 manifest，排除原始业务事件、Watermark 事件与迟到事件标识；Artifact 保留 90 天并在 Job Summary 记录下载链接和 SHA-256。

## 本地统一测试

Windows 环境运行：

```powershell
./scripts/test-all.ps1
```

该脚本依次运行 Python/API 测试、参考数据质量门禁、JavaScript 看板测试和 Java/Flink 测试。Kafka 冒烟测试仍需要 Docker，单独执行：

```powershell
./scripts/kafka-up.ps1
./scripts/kafka-smoke-test.ps1 -Count 20
./scripts/kafka-down.ps1 -RemoveData
```

## 当前验证状态

工作流语法和关键配置已在本地进行静态检查，本地 Python 与 Flink 测试已经通过。提交 `963be45` 的五个 Job 已在 GitHub 全部成功，包括真实单节点链路及批流对账；这仍不能证明生产高可用、长期运行或性能 SLA。

## 工作流约束

- Kafka、ClickHouse 和端到端 Job 依赖基础测试，避免为明显失败的提交启动中间件。
- ClickHouse 冒烟测试向同一业务键写入两个版本，用于验证替换语义。
- 清理步骤使用 `always()`，确保失败路径也回收容器和数据卷。
- Maven 只缓存依赖，不复用 `target` 产物，避免旧构建结果污染验证。
- CI 结果只代表工作流覆盖的单节点场景，不代表生产高可用或性能 SLA。

