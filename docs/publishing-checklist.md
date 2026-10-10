# 远程仓库发布与验收清单

当前仓库已于 2026 年 10 月 4 日公开发布到 GitHub，包含完整源码、自动化测试、离线数仓基准和真实链路验收脚本。本机仍没有 Docker CLI 与运行中的 Flink 集群，但远程 CI 已完成单节点真实链路验收；必须继续把“本机已验证”“远程单节点已验证”和“生产级未验证”分开表达。

## 推荐仓库信息

- 远程仓库：<https://github.com/ZliY221/Real-time-data-warehouse-and-business-analysis-platform-for-e-commerce>
- 仓库名：`Real-time-data-warehouse-and-business-analysis-platform-for-e-commerce`
- 简介：`Event-time ecommerce data platform with Flink, ClickHouse, reconciliation, data quality and a DuckDB dimensional warehouse.`
- 建议 Topics：`apache-flink`、`kafka`、`clickhouse`、`data-engineering`、`data-quality`、`duckdb`、`fastapi`、`echarts`
- 默认分支：`main`
- 可见性：Public

## 发布前本地验收

```powershell
git status --short
python scripts/audit-publication.py
./scripts/test-all.ps1
git log --oneline -20
```

必须确认：

- 工作树无未提交修改；
- 发布审计不存在高置信密钥或超过 20 MiB 的跟踪文件；`PASS_WITH_REVIEW` 项逐条确认是合成测试内容；
- 当前基线为 105 项 Python/API/质量/对账/离线数仓/运行证据测试、8 项 JavaScript 测试、28 项 Java/Flink 测试，共 141 项；
- 5 万条离线数仓基准的原始多轮结果与 README 数字一致；
- 仓库中没有 `.env`、访问令牌、个人简历、证书原图、学籍验证码或真实订单数据；
- README 继续明确链路已在远程单节点 CI 验收，但尚未在本机复现，也不是生产环境证据。

## 当前审计结果

2026 年 10 月 4 日已实际运行发布审计：没有高置信密钥、私钥、本机用户路径或超过 5 MiB 的 Git 跟踪文件。唯一人工复核项是 `ClickHouseRejectedEventStatementTest.java` 中的合成邮箱字符串，它用于验证拒绝载荷不会被持久化，不是真实联系方式。

## 仍需本人决定

- 开源许可证。没有本人选择前不自动添加；
- 是否在自己的可用 Docker/Flink 环境再次复现远程链路验收；
- 是否录制看板与端到端流程演示视频。

## 后续推送与远程验证

`origin` 已指向上述 GitHub 仓库，后续提交使用：

```powershell
git remote -v
git status --short
git push origin main
```

推送后依次确认：

1. Python、Flink、Kafka、ClickHouse 和完整端到端验收五个 CI Job 的实际状态；
2. CI 失败时保留运行 URL、日志结论和修复提交，不只重复运行；
3. README Mermaid、文档链接、ECharts 静态资源和性能证据可以公开访问；
4. About、Topics、仓库简介和置顶顺序已经设置；
5. 只有 CI 真正成功后，才把“远程 CI 已通过”写入项目说明。

## 真实链路验收条件

运行 `scripts/e2e-acceptance.ps1` 前需要：

- Docker 与 Compose 可用；
- 本地 Flink 1.20.1 集群正在运行；
- JDK 17、Maven 和 Python 3.11 环境满足 README；
- 端口、磁盘和内存足够，且没有需要保留的同名测试资源。

验收成功必须产生 `build/e2e/<run-id>/` 报告，包含隔离 Topic、独立 ClickHouse 数据库、JobID、10 个指标键和批流精确对账结果。仅脚本存在、Maven 测试通过或等待固定秒数，都不能替代真实验收证据。

## 可公开截图

- 141 项本地测试最终摘要；
- DuckDB 5 万条多轮基准报告；
- 数据质量失败样例与趋势看板；
- 批流对账报告格式；
- 远程真实链路的 JobID、指标键和对账 PASS，并明确它来自单节点 CI。

截图不得暴露 Windows 用户目录、令牌、密码、私有仓库地址或个人证件。

## 发布后证据记录

- 远程仓库 URL：<https://github.com/ZliY221/Real-time-data-warehouse-and-business-analysis-platform-for-e-commerce>
- 首次公开提交：`9617a0ca46e8f72ae11bb35bf05bcab1a34bee84`
- 首次推送日期：2026 年 10 月 4 日
- 首次四层成功 CI：<https://github.com/ZliY221/Real-time-data-warehouse-and-business-analysis-platform-for-e-commerce/actions/runs/37186145537>
- 首次四层成功提交：`4fd0660c25ba840cb4f3471be8d28a37f437dbba`
- 首次五 Job 及真实端到端验收成功 CI：<https://github.com/ZliY221/Real-time-data-warehouse-and-business-analysis-platform-for-e-commerce/actions/runs/37188134524>
- 真实端到端验收提交：`963be45ef4163de26868effe565418b4cca0fcb5`
- 验收摘要：Flink JobID `7eaef8f77086847befded3990b9e1df1`，20 条业务事件、3 条推进事件、10 个指标键全部匹配；
- 发布版本标签；
- README 中根据新证据更新了哪些边界。
