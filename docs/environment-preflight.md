# 跨平台环境自检

`scripts/project_doctor.py` 仅使用 Python 标准库，可在安装项目依赖之前运行。脚本从自身位置定位仓库根目录，因此不依赖当前工作目录。

## 检查范围

| Profile | 检查内容 | 适用入口 |
|---|---|---|
| `core` | Python 3.11、关键配置与样例文件、`build/` 写权限 | 数据生成与基础校验 |
| `warehouse` | `core` 加 DuckDB | 一键本地离线仓库 |
| `api` | `core` 加 FastAPI、Uvicorn | 查询 API 和经营看板 |
| `full` | `core` 加 DuckDB、FastAPI、Uvicorn、JDK 17、Maven、Docker Engine、Docker Compose | 完整本地数据链路 |

```shell
python scripts/project_doctor.py --profile full --json-output build/doctor/report.json --markdown-output build/doctor/report.md
```

所有检查满足时退出码为 `0`，报告状态为 `READY`；缺少必需条件时退出码为 `1`，状态为 `BLOCKED`。每个失败项会给出缺少的命令、模块或项目文件，不会读取服务凭据或业务数据正文。

## 平台验证范围

`portable-smoke.yml` 在 Windows、Ubuntu 和 macOS 上从全新检出执行 `scripts/quickstart.py`，覆盖 `warehouse` 环境自检、事件契约校验、DuckDB 离线仓库构建和汇总报告。Kafka、Flink 与 ClickHouse 的容器组合链路由 Linux `ci.yml` 独立执行。
