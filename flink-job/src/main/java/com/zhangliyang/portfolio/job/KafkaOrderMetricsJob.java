package com.zhangliyang.portfolio.job;

import com.zhangliyang.portfolio.pipeline.OrderMetricsPipeline;
import com.zhangliyang.portfolio.pipeline.OrderMetricsTopology;
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
        configure(environment, config);
        environment.execute("ecommerce-order-metrics");
    }

    public static OrderMetricsTopology configure(
            StreamExecutionEnvironment environment,
            KafkaJobConfig config) {
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

        topology.getMetrics()
                .print("minute-metrics")
                .name("print-minute-metrics");
        topology.getRejectedEvents()
                .printToErr("rejected-events")
                .name("print-rejected-events");
        topology.getLateEvents()
                .printToErr("late-events")
                .name("print-late-events");
        return topology;
    }
}
