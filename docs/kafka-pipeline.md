# Kafka 本地消息链路

## 本单元目标

完成本单元后，应能够解释：

1. Topic、Partition、Offset、Producer 和 Consumer Group 的关系。
2. 为什么一个本地单节点 Kafka 仍然需要区分 broker 和 controller 角色。
3. 容器内客户端和宿主机客户端为什么使用不同的 listener。
4. `acks=all` 能保证什么，不能保证什么。
5. 为什么项目不能仅凭“容器启动成功”就宣称消息链路完成。

## 当前配置

`compose.yaml` 使用官方 `apache/kafka:3.9.1` 镜像，以单节点 KRaft combined mode 运行：

- 宿主机客户端：`localhost:9092`
- Compose 网络内客户端：`kafka:29092`
- controller listener：`kafka:29093`
- 业务 Topic：`order-events`
- 分区数：3
- 副本数：1，仅适合本地学习和测试

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

## 为什么需要 smoke test

Smoke test 会：

1. 创建一个名称唯一的临时 Topic。
2. 生成固定数量的合法订单事件。
3. 使用 `acks=all` 写入 Kafka。
4. 从头消费相同数量的记录。
5. 对消费结果再次执行 v1 业务契约校验。
6. 删除临时 Topic 和临时文件。

这比“看到 Kafka 日志没有报错”更强，因为它验证了真实的生产、存储、消费和数据契约闭环。

## 设计验证

1. 三个 Partition 是否意味着同一个订单的事件一定有序？
2. 如果 Producer 没有设置消息 Key，同一个订单的后续事件可能发生什么？
3. `acks=all` 是否等于端到端 exactly-once？
4. Consumer Group 中增加消费者数量，吞吐为什么不会无限增长？
5. 单节点副本数为 1 有什么故障风险？

## 当前验证状态

配置、脚本和静态测试已经完成；GitHub Actions 已在 `apache/kafka:3.9.1` 容器中完成 Topic 创建、20 条事件生产、消费和契约校验。开发机仍没有 Docker CLI，且该证据不等同于 Kafka → Flink → ClickHouse 整链路验收。

