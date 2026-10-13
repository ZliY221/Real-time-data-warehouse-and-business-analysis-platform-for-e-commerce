# 用户使用指南

适用版本：`v0.9.2`

本指南随项目版本同步更新，介绍当前版本可直接使用的入口、功能和输出位置。

## 1. 环境要求

- Python 3.11 或更高版本
- 本地离线流程无需 Docker
- 完整实时链路需要 Docker、JDK 17 和 Maven

## 2. 最快启动

在仓库根目录执行：

```powershell
python scripts/bootstrap.py
```

启动器会创建隔离运行时，生成订单事件，校验事件契约，构建 DuckDB 离线数仓并导出经营报告。主要输出位于 `build/quickstart/`。

## 3. 启动经营看板

界面预览模式使用固定演示数据，不依赖 ClickHouse：

```powershell
./scripts/dashboard-preview.ps1
```

浏览器访问 `http://127.0.0.1:8000/dashboard`。真实链路启动后使用：

```powershell
./scripts/api-up.ps1
```

看板支持时间、地区和渠道筛选，并展示 GMV、订单量、客单价、分钟趋势、异常侧流和质量历史。

## 4. 数据资产运维

- `GET /api/v1/operations/assets`：查看资产责任团队与上下游关系。
- `GET /api/v1/operations/assets/health`：查看全部受监控资产的健康汇总与受影响下游。
- `GET /api/v1/operations/assets/{asset_id}/freshness`：查看单个资产的新鲜度、延迟和影响范围。

可以传入 `evaluated_at` UTC 时间复现某一时点的健康判定。

## 5. 完整实时链路

```powershell
docker compose up -d
./scripts/flink-up.ps1
./scripts/submit-flink-job.ps1
./scripts/api-up.ps1
```

实时链路从 Kafka 读取订单事件，经 Flink 完成事件时间计算、去重和分钟聚合，再将结果写入 ClickHouse。接口文档位于 `http://127.0.0.1:8000/docs`。

## 6. 常见问题

- 端口占用：通过脚本的 `-Port` 参数改用其他端口。
- ClickHouse 不可用：先检查 `docker compose ps`，再核对 `CLICKHOUSE_HTTP_URL`。
- 本地 Python 依赖冲突：重新执行 `python scripts/bootstrap.py --refresh`。
- 看板显示预览提示：当前连接的是演示数据入口，不代表实时基础设施已启动。

## 7. 数据与运行边界

仓库内样例数据均为合成数据。运行产物写入 `build/`，不应将业务凭据、个人数据或生产连接信息提交到仓库。
