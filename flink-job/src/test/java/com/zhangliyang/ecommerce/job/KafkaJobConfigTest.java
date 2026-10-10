package com.zhangliyang.ecommerce.job;

import org.junit.jupiter.api.Test;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class KafkaJobConfigTest {
    @Test
    void usesDocumentedLocalDefaults() {
        KafkaJobConfig config = KafkaJobConfig.fromArgs(new String[0]);

        assertEquals("localhost:9092", config.getBootstrapServers());
        assertEquals("order-events", config.getTopic());
        assertEquals("ecommerce-order-metrics", config.getGroupId());
        assertEquals(StartingOffsetsMode.COMMITTED, config.getStartingOffsetsMode());
        assertEquals(Duration.ofSeconds(10), config.getOutOfOrderness());
        assertEquals(Duration.ofSeconds(60), config.getIdleness());
        assertEquals(Duration.ofHours(24), config.getDeduplicationTtl());
        assertEquals(Duration.ZERO, config.getAllowedLateness());
        assertEquals(Duration.ofSeconds(10), config.getCheckpointInterval());
        assertEquals(1, config.getParallelism());
        assertEquals(MetricsSinkMode.CLICKHOUSE, config.getMetricsSinkMode());
        assertEquals(MetricsSinkMode.CLICKHOUSE, config.getAnomalySinkMode());
        assertEquals(
                "jdbc:clickhouse://localhost:8123/ecommerce",
                config.getClickHouseUrl());
        assertEquals("default", config.getClickHouseUser());
        assertEquals(100, config.getClickHouseBatchSize());
        assertEquals(Duration.ofSeconds(1), config.getClickHouseBatchInterval());
        assertEquals(3, config.getClickHouseMaxRetries());
    }

    @Test
    void parsesEverySupportedOverride() {
        KafkaJobConfig config = KafkaJobConfig.fromArgs(new String[]{
                "--bootstrap-servers", "kafka:29092",
                "--topic", "orders-v2",
                "--group-id", "metrics-v2",
                "--starting-offsets", "earliest",
                "--out-of-orderness-seconds", "15",
                "--idleness-seconds", "45",
                "--deduplication-ttl-hours", "48",
                "--allowed-lateness-seconds", "5",
                "--checkpoint-interval-seconds", "20",
                "--parallelism", "3",
                "--metrics-sink", "both",
                "--anomaly-sink", "print",
                "--clickhouse-url", "jdbc:clickhouse://clickhouse:8123/analytics",
                "--clickhouse-user", "analytics",
                "--clickhouse-batch-size", "250",
                "--clickhouse-batch-interval-ms", "2000",
                "--clickhouse-max-retries", "5"
        });

        assertEquals("kafka:29092", config.getBootstrapServers());
        assertEquals("orders-v2", config.getTopic());
        assertEquals("metrics-v2", config.getGroupId());
        assertEquals(StartingOffsetsMode.EARLIEST, config.getStartingOffsetsMode());
        assertEquals(Duration.ofSeconds(15), config.getOutOfOrderness());
        assertEquals(Duration.ofSeconds(45), config.getIdleness());
        assertEquals(Duration.ofHours(48), config.getDeduplicationTtl());
        assertEquals(Duration.ofSeconds(5), config.getAllowedLateness());
        assertEquals(Duration.ofSeconds(20), config.getCheckpointInterval());
        assertEquals(3, config.getParallelism());
        assertEquals(MetricsSinkMode.BOTH, config.getMetricsSinkMode());
        assertEquals(MetricsSinkMode.PRINT, config.getAnomalySinkMode());
        assertEquals(
                "jdbc:clickhouse://clickhouse:8123/analytics",
                config.getClickHouseUrl());
        assertEquals("analytics", config.getClickHouseUser());
        assertEquals(250, config.getClickHouseBatchSize());
        assertEquals(Duration.ofSeconds(2), config.getClickHouseBatchInterval());
        assertEquals(5, config.getClickHouseMaxRetries());
    }

    @Test
    void rejectsUnknownAndDuplicateOptions() {
        assertThrows(
                IllegalArgumentException.class,
                () -> KafkaJobConfig.fromArgs(new String[]{"--unknown", "value"}));
        assertThrows(
                IllegalArgumentException.class,
                () -> KafkaJobConfig.fromArgs(new String[]{
                        "--topic", "one",
                        "--topic", "two"
                }));
    }

    @Test
    void rejectsMissingOrMalformedValues() {
        assertThrows(
                IllegalArgumentException.class,
                () -> KafkaJobConfig.fromArgs(new String[]{"--topic"}));
        assertThrows(
                IllegalArgumentException.class,
                () -> KafkaJobConfig.fromArgs(new String[]{"--parallelism", "many"}));
        assertThrows(
                IllegalArgumentException.class,
                () -> KafkaJobConfig.fromArgs(new String[]{"--starting-offsets", "middle"}));
        assertThrows(
                IllegalArgumentException.class,
                () -> KafkaJobConfig.fromArgs(new String[]{"--metrics-sink", "file"}));
        IllegalArgumentException anomalyError = assertThrows(
                IllegalArgumentException.class,
                () -> KafkaJobConfig.fromArgs(new String[]{"--anomaly-sink", "file"}));
        assertTrue(anomalyError.getMessage().contains("anomaly sink"));
    }

    @Test
    void rejectsUnsafeDurationAndParallelismValues() {
        assertThrows(
                IllegalArgumentException.class,
                () -> KafkaJobConfig.fromArgs(new String[]{"--idleness-seconds", "0"}));
        assertThrows(
                IllegalArgumentException.class,
                () -> KafkaJobConfig.fromArgs(new String[]{"--allowed-lateness-seconds", "-1"}));
        assertThrows(
                IllegalArgumentException.class,
                () -> KafkaJobConfig.fromArgs(new String[]{"--parallelism", "0"}));
        assertThrows(
                IllegalArgumentException.class,
                () -> KafkaJobConfig.fromArgs(new String[]{
                        "--clickhouse-url", "jdbc:postgresql://localhost/ecommerce"
                }));
        assertThrows(
                IllegalArgumentException.class,
                () -> KafkaJobConfig.fromArgs(new String[]{
                        "--clickhouse-batch-size", "0"
                }));
        assertThrows(
                IllegalArgumentException.class,
                () -> KafkaJobConfig.fromArgs(new String[]{
                        "--clickhouse-max-retries", "-1"
                }));
    }
}
