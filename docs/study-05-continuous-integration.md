# 学习单元 05 持续集成与可验证交付

## 本单元目标

完成本单元后，应能够解释：

1. 为什么本地测试通过不等于项目可交付。
2. Python、Flink 和 Kafka 测试为什么应该拆成不同 CI Job。
3. `needs`、`concurrency`、`timeout-minutes` 和 `always()` 分别解决什么问题。
4. 为什么工作流只授予 `contents: read` 权限。
5. CI 通过后仍然不能证明哪些生产能力。

## 工作流结构

`.github/workflows/ci.yml` 包含三个 Job：

```text
Python contract tests ─┐
                       ├─> Kafka smoke test
Java and Flink tests ──┘
```

- Python Job 验证事件生成器、业务契约、Compose 静态约束和 NDJSON 校验工具。
- Flink Job 使用 JDK 17 和 Maven 缓存，执行真实 DataStream 测试。
- Kafka Job 在前两个 Job 通过后启动官方 Kafka 容器，执行生产、消费和再次校验，最后始终清理容器与数据卷。

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

该脚本依次运行 Python 测试和 Java/Flink 测试。Kafka 冒烟测试仍需要 Docker，单独执行：

```powershell
./scripts/kafka-up.ps1
./scripts/kafka-smoke-test.ps1 -Count 20
./scripts/kafka-down.ps1 -RemoveData
```

## 当前验证状态

工作流语法和关键配置已在本地进行静态检查，本地 Python 与 Flink 测试已经通过。只有把仓库推送到 GitHub 并看到三个 Job 全部成功，才能宣称 CI 和 Kafka 冒烟测试在远程环境通过。

## 面试自测

1. 为什么 Kafka Job 要依赖两个单元测试 Job？
2. 如果清理步骤没有 `always()`，失败后可能留下什么问题？
3. 缓存 Maven 依赖与缓存 `target` 构建产物有什么区别？
4. CI 全绿是否等于系统具备生产高可用能力？
5. 如何把测试失败日志变成可追踪的质量改进记录？

