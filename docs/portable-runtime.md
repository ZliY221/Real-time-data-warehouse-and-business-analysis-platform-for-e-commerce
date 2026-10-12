# 隔离运行时启动器

`scripts/bootstrap.py` 面向全新检出或 ZIP 解压后的首次运行。入口只要求 Python 3.11 或更高版本，在项目的 `build/portable-runtime/` 中创建虚拟环境、安装锁定的 DuckDB 依赖，然后执行公开 Quickstart。

```bash
python scripts/bootstrap.py
```

Quickstart 参数可以直接追加：

```bash
python scripts/bootstrap.py -- --count 100 --seed 2027 --output-dir build/local-run
```

运行时标记记录项目版本、Python 版本、安装范围和 `pyproject.toml` 的 SHA-256。标记与当前配置一致时复用已有环境；版本或依赖配置变化时自动重建。需要主动重建时使用：

```bash
python scripts/bootstrap.py --refresh-runtime
```

运行时目录必须位于项目 `build/` 目录内，并由 `.gitignore` 排除。启动器不会修改系统 Python，也不会写入仓库源码目录。首次安装依赖需要能够访问 Python 软件包索引；Kafka、Flink 与 ClickHouse 完整实时链路仍需要 Docker、JDK 17 和 Maven。
