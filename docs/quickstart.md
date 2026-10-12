# 一键本地数据流

`scripts/quickstart.py` 提供不依赖当前工作目录的跨平台入口，用于构建可查询的本地电商离线仓库。入口依次执行环境自检、确定性事件生成、业务契约校验、DuckDB 分层装载和聚合报告导出。

全新环境可先运行 `python scripts/bootstrap.py`，由[隔离运行时启动器](portable-runtime.md)创建项目内虚拟环境、安装锁定依赖并调用本入口。

## 运行

```shell
python -m pip install -e ".[warehouse]"
python scripts/quickstart.py
```

默认输出目录为 `build/quickstart/`。可指定事件数量、随机种子和输出目录：

```shell
python scripts/quickstart.py --count 100 --seed 2027 --output-dir build/local-run
```

入口使用当前 Python 解释器启动所有子进程，并从脚本位置解析仓库根目录，因此可从任意目录调用。相同数量与种子使用独立且稳定命名的 DuckDB 文件；重复执行同一输入时，装载器按输入指纹返回已有批次，不重复写入事实表。

## 输出契约

成功运行后，输出目录至少包含：

- `doctor.json` 和 `doctor.md`：运行条件诊断；
- `order_events.ndjson`：确定性订单事件；
- `ecommerce-<seed>-<count>.duckdb`：本地分层仓库；
- `warehouse-report.json` 和 `warehouse-report.md`：不包含事件、订单和用户标识的聚合报告；
- `summary.json`：运行状态、版本、输入参数和产物位置。

`summary.json` 仅在全部阶段完成且仓库事件数与请求数量一致后写入，完成状态为 `COMPLETE`。Kafka、Flink 与 ClickHouse 组合链路不属于该入口范围，仍通过容器化端到端验收脚本运行。
