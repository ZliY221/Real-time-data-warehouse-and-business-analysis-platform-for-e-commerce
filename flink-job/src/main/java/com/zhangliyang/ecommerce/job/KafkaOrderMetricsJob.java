package com.zhangliyang.ecommerce.job;

import com.zhangliyang.ecommerce.pipeline.OrderMetricsPipeline;
import com.zhangliyang.ecommerce.pipeline.OrderMetricsTopology;
import com.zhangliyang.ecommerce.sink.ClickHouseAnomalySink;
import com.zhangliyang.ecommerce.sink.ClickHouseMinuteMetricSink;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.connector.kafka.source.KafkaSource;
import org.apache.flink.core.execution.CheckpointingMode;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;

public final class KafkaOrderMetricsJob {
    private KafkaOrderMetricsJob() {
    }

    public static void main(String[] args) throws Exception {
        KafkaJobConfig config = KafkaJobConfig.fromArgs(args);
        StreamExecutionEnvironment environment =
                StreamExecutionEnvironment.getExecutionEnvironment();
        configure(environment, config, System.getenv("CLICKHOUSE_PASSWORD"));
        environment.execute("ecommerce-order-metrics");
    }

    public static OrderMetricsTopology configure(
            StreamExecutionEnvironment environment,
            KafkaJobConfig config) {
        return configure(environment, config, "");
    }

    public static OrderMetricsTopology configure(
            StreamExecutionEnvironment environment,
            KafkaJobConfig config,
            String clickHousePassword) {
        if (environment == null) {
            throw new IllegalArgumentException("environment must not be null");
        }
        if (config == null) {
            throw new IllegalArgumentException("config must not be null");
        }

        environment.setParallelism(config.getParallelism());
        environment.enableCheckpointing(
                config.getCheckpointInterval().toMillis(),
                CheckpointingMode.EXACTLY_ONCE);
        environment.getCheckpointConfig().setMaxConcurrentCheckpoints(1);
        environment.getCheckpointConfig().setCheckpointTimeout(60_000L);
        environment.getCheckpointConfig().setMinPauseBetweenCheckpoints(
                Math.min(5_000L, config.getCheckpointInterval().toMillis()));

        KafkaSource<String> source = KafkaOrderEventSourceFactory.create(config);
        DataStream<String> rawEvents = environment
                .fromSource(source, WatermarkStrategy.noWatermarks(), "kafka-order-events")
                .name("consume-order-events-from-kafka");

        OrderMetricsTopology topology = OrderMetricsPipeline.buildFromJson(
                rawEvents,
                config.getOutOfOrderness(),
                config.getIdleness(),
                config.getDeduplicationTtl(),
                config.getAllowedLateness());

        if (config.getMetricsSinkMode().writesClickHouse()) {
            ClickHouseMinuteMetricSink.attach(
                    topology.getMetrics(),
                    config,
                    clickHousePassword);
        }
        if (config.getMetricsSinkMode().writesConsole()) {
            topology.getMetrics()
                    .print("minute-metrics")
                    .name("print-minute-metrics");
        }
        if (config.getAnomalySinkMode().writesClickHouse()) {
            ClickHouseAnomalySink.attach(
                    topology.getRejectedEvents(),
                    topology.getLateEvents(),
                    config,
                    clickHousePassword);
        }
        if (config.getAnomalySinkMode().writesConsole()) {
            topology.getRejectedEvents()
                    .printToErr("rejected-events")
                    .name("print-rejected-events");
            topology.getLateEvents()
                    .printToErr("late-events")
                    .name("print-late-events");
        }
        return topology;
    }
}
