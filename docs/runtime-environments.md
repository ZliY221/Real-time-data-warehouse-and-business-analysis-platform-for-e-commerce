# 运行环境分层

项目按职责拆分三类运行环境，日常使用无需一次安装全部组件。

| 环境 | 适用场景 | 主要依赖 | 检查命令 |
| --- | --- | --- | --- |
| 离线便携环境 | 样例数据、质量校验、DuckDB 数仓 | Python 3.11+ | `python scripts/project_doctor.py --profile warehouse` |
| 查询与看板环境 | FastAPI 与经营看板 | Python 3.11+、API 依赖 | `python scripts/project_doctor.py --profile api` |
| 实时集成环境 | Kafka、Flink、ClickHouse 全链路 | Docker、JDK 17+、Maven | `python scripts/project_doctor.py --profile full` |

公开快速启动使用项目专属虚拟环境，并固定 UTF-8 子进程输出，适配中文目录和不同系统区域设置。自动化环境覆盖 Linux Python 3.11/3.13、Windows Python 3.11 和 macOS Python 3.11；完整实时链路在 Linux 容器环境独立执行。

建议先运行离线便携环境。只有开发实时作业或核对 Kafka、Flink、ClickHouse 集成行为时，才启用完整环境。
