package com.zhangliyang.portfolio.sink;

import com.zhangliyang.portfolio.job.KafkaJobConfig;
import com.zhangliyang.portfolio.model.MinuteMetric;
import org.apache.flink.connector.jdbc.JdbcConnectionOptions;
import org.apache.flink.connector.jdbc.JdbcExecutionOptions;
import org.apache.flink.connector.jdbc.core.datastream.sink.JdbcSink;
import org.apache.flink.streaming.api.datastream.DataStream;

public final class ClickHouseMinuteMetricSink {
    public static final String INSERT_SQL =
            "INSERT INTO minute_metrics "
                    + "(window_start, window_end, region, channel, order_count, gmv, version, processed_at) "
                    + "VALUES (?, ?, ?, ?, ?, ?, ?, ?)";

    private ClickHouseMinuteMetricSink() {
    }

    public static void attach(
            DataStream<MinuteMetric> metrics,
            KafkaJobConfig config,
            String password) {
        if (metrics == null) {
            throw new IllegalArgumentException("metrics must not be null");
        }
        if (config == null) {
            throw new IllegalArgumentException("config must not be null");
        }

        JdbcExecutionOptions executionOptions = JdbcExecutionOptions.builder()
                .withBatchSize(config.getClickHouseBatchSize())
                .withBatchIntervalMs(config.getClickHouseBatchInterval().toMillis())
                .withMaxRetries(config.getClickHouseMaxRetries())
                .build();
        JdbcConnectionOptions connectionOptions =
                new JdbcConnectionOptions.JdbcConnectionOptionsBuilder()
                        .withUrl(config.getClickHouseUrl())
                        .withDriverName("com.clickhouse.jdbc.ClickHouseDriver")
                        .withUsername(config.getClickHouseUser())
                        .withPassword(password == null ? "" : password)
                        .withConnectionCheckTimeoutSeconds(10)
                        .build();

        JdbcSink<MinuteMetric> sink = JdbcSink.<MinuteMetric>builder()
                .withExecutionOptions(executionOptions)
                .withQueryStatement(INSERT_SQL, new ClickHouseMinuteMetricStatement())
                .buildAtLeastOnce(connectionOptions);
        metrics.sinkTo(sink)
                .name("write-minute-metrics-to-clickhouse");
    }
}
