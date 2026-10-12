# 隔离运行时启动器

`scripts/bootstrap.py` 面向全新检出或 ZIP 解压后的首次运行。入口只要求 Python 3.11 或更高版本，在受控的用户缓存目录中创建虚拟环境、安装锁定的 DuckDB 依赖，然后执行公开 Quickstart。

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

Windows 默认使用 `%LOCALAPPDATA%/ZliY221/project-runtimes/`，Linux 与 macOS 使用 `$XDG_CACHE_HOME/ZliY221/project-runtimes/` 或 `~/.cache/ZliY221/project-runtimes/`。目录名包含检出路径指纹，避免多个仓库副本共用错误的可编辑安装。短缓存路径也避免 GitHub 长仓库名在深层 Windows 解压目录中触发原生扩展路径限制。

使用 `--runtime-dir build/custom-runtime` 可以把环境放回当前项目。自定义位置只能位于项目 `build/` 或上述受控缓存目录。启动器不会修改系统 Python，业务产物始终写入项目 `build/`。首次安装依赖需要能够访问 Python 软件包索引；Kafka、Flink 与 ClickHouse 完整实时链路仍需要 Docker、JDK 17 和 Maven。
