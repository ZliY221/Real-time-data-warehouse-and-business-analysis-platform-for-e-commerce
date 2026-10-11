# Kafka 本地消息链路

## 设计范围

本地链路覆盖 Topic 创建、三分区写入、Consumer Group 消费和业务契约复核。Kafka 以单节点 KRaft combined mode 运行，并分别暴露宿主机与 Compose 网络 listener。

## 当前配置

`compose.yaml` 使用官方 `apache/kafka:3.9.1` 镜像，以单节点 KRaft combined mode 运行：

- 宿主机客户端：`localhost:9092`
- Compose 网络内客户端：`kafka:29092`
- controller listener：`kafka:29093`
- 业务 Topic：`order-events`
- 分区数：3
- 副本数：1，仅用于本地开发和自动化测试

单节点环境必须把 offsets topic 和 transaction state topic 的副本数降为 1，否则 Kafka 会沿用面向多节点集群的默认副本数并导致内部 Topic 无法创建。这个配置不适用于生产环境。

## 启动与验证

需要 Docker Desktop 和 Docker Compose v2。

```powershell
./scripts/kafka-up.ps1
./scripts/kafka-produce-sample.ps1
./scripts/kafka-consume.ps1 -FromBeginning -Count 20
./scripts/kafka-smoke-test.ps1 -Count 20
```

停止服务但保留数据：

```powershell
./scripts/kafka-down.ps1
```

停止服务并删除本地 Kafka 数据卷：

```powershell
./scripts/kafka-down.ps1 -RemoveData
```

## 消息链路冒烟测试

Smoke test 会：

1. 创建一个名称唯一的临时 Topic。
2. 生成固定数量的合法订单事件。
3. 使用 `acks=all` 写入 Kafka。
4. 从头消费相同数量的记录。
5. 对消费结果再次执行 v1 业务契约校验。
6. 删除临时 Topic 和临时文件。

验收同时覆盖生产、存储、消费和数据契约，不以容器启动日志作为成功条件。

## 设计约束

- 顺序只在单个 Partition 内成立；同一业务键需要稳定的消息 Key。
- `acks=all` 约束 broker 写入确认，不提供端到端 exactly-once。
- 同一 Consumer Group 的有效并行度受 Partition 数量限制。
- 单节点、副本数 1 的配置不具备 broker 故障容错能力。

## 当前验证状态

配置、脚本和静态测试已经完成；GitHub Actions 已在 `apache/kafka:3.9.1` 容器中完成 Topic 创建、20 条事件生产、消费和契约校验。开发机仍没有 Docker CLI，且该证据不等同于 Kafka → Flink → ClickHouse 整链路验收。

