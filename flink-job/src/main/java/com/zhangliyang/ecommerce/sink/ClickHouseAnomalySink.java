package com.zhangliyang.ecommerce.sink;

import com.zhangliyang.ecommerce.job.KafkaJobConfig;
import com.zhangliyang.ecommerce.model.OrderEvent;
import com.zhangliyang.ecommerce.model.RejectedEvent;
import org.apache.flink.connector.jdbc.JdbcConnectionOptions;
import org.apache.flink.connector.jdbc.JdbcExecutionOptions;
import org.apache.flink.connector.jdbc.core.datastream.sink.JdbcSink;
import org.apache.flink.streaming.api.datastream.DataStream;

public final class ClickHouseAnomalySink {
    public static final String REJECTED_INSERT_SQL =
            "INSERT INTO rejected_order_events "
                    + "(rejection_id, error_type, payload_size_bytes, detected_at, version) "
                    + "VALUES (?, ?, ?, ?, ?)";
    public static final String LATE_INSERT_SQL =
            "INSERT INTO late_order_events "
                    + "(event_id, order_id, event_time, ingest_time, region, channel, "
                    + "total_amount, detected_at, version) "
                    + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)";

    private ClickHouseAnomalySink() {
    }

    public static void attach(
            DataStream<RejectedEvent> rejectedEvents,
            DataStream<OrderEvent> lateEvents,
            KafkaJobConfig config,
            String password) {
        if (rejectedEvents == null) {
            throw new IllegalArgumentException("rejected events must not be null");
        }
        if (lateEvents == null) {
            throw new IllegalArgumentException("late events must not be null");
        }
        if (config == null) {
            throw new IllegalArgumentException("config must not be null");
        }

        JdbcExecutionOptions executionOptions = executionOptions(config);
        JdbcConnectionOptions connectionOptions = connectionOptions(config, password);

        JdbcSink<RejectedEvent> rejectedSink = JdbcSink.<RejectedEvent>builder()
                .withExecutionOptions(executionOptions)
                .withQueryStatement(
                        REJECTED_INSERT_SQL,
                        new ClickHouseRejectedEventStatement())
                .buildAtLeastOnce(connectionOptions);
        rejectedEvents.sinkTo(rejectedSink)
                .name("write-rejected-events-to-clickhouse")
                .setParallelism(1);

        JdbcSink<OrderEvent> lateSink = JdbcSink.<OrderEvent>builder()
                .withExecutionOptions(executionOptions)
                .withQueryStatement(LATE_INSERT_SQL, new ClickHouseLateEventStatement())
                .buildAtLeastOnce(connectionOptions);
        lateEvents.sinkTo(lateSink)
                .name("write-late-events-to-clickhouse")
                .setParallelism(1);
    }

    private static JdbcExecutionOptions executionOptions(KafkaJobConfig config) {
        return JdbcExecutionOptions.builder()
                .withBatchSize(config.getClickHouseBatchSize())
                .withBatchIntervalMs(config.getClickHouseBatchInterval().toMillis())
                .withMaxRetries(config.getClickHouseMaxRetries())
                .build();
    }

    private static JdbcConnectionOptions connectionOptions(
            KafkaJobConfig config,
            String password) {
        return new JdbcConnectionOptions.JdbcConnectionOptionsBuilder()
                .withUrl(config.getClickHouseUrl())
                .withDriverName("com.clickhouse.jdbc.ClickHouseDriver")
                .withUsername(config.getClickHouseUser())
                .withPassword(password == null ? "" : password)
                .withConnectionCheckTimeoutSeconds(10)
                .build();
    }
}
