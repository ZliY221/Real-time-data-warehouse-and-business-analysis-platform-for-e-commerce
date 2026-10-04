# 学习单元 05 持续集成与可验证交付

## 本单元目标

完成本单元后，应能够解释：

1. 为什么本地测试通过不等于项目可交付。
2. Python/API/数据质量/看板、Flink 和 Kafka 测试为什么应该按成本拆分。
3. `needs`、`concurrency`、`timeout-minutes` 和 `always()` 分别解决什么问题。
4. 为什么工作流只授予 `contents: read` 权限。
5. CI 通过后仍然不能证明哪些生产能力。

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
- 端到端 Job 校验并启动 Flink 1.20.1 单节点集群，创建隔离 Topic 和数据库，提交真实作业，并要求 10 个指标键精确对账通过。

## 安全和资源控制

- `permissions: contents: read`：工作流只需要读取代码，不授予写仓库或操作 Issue 的权限。
- `timeout-minutes`：防止 Maven、Kafka 启动或消费异常时无限占用 Runner。
- `concurrency.cancel-in-progress`：同一分支有新提交时取消旧运行，减少重复消耗。
- `if: ${{ always() }}`：即使冒烟测试失败，也执行 Kafka 清理步骤。
- 所有依赖版本和容器镜像均固定，不使用 `latest`。

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

## 面试自测

1. 为什么 Kafka Job 要依赖两个单元测试 Job？
2. ClickHouse 冒烟测试为什么要写入同一个业务键的两个版本？
3. 如果清理步骤没有 `always()`，失败后可能留下什么问题？
4. 缓存 Maven 依赖与缓存 `target` 构建产物有什么区别？
5. CI 全绿是否等于系统具备生产高可用能力？
6. 如何把测试失败日志变成可追踪的质量改进记录？

