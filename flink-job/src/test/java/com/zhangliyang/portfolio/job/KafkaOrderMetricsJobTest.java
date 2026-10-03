package com.zhangliyang.portfolio.job;

import org.apache.flink.core.execution.CheckpointingMode;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class KafkaOrderMetricsJobTest {
    @Test
    void buildsKafkaSourceForEveryStartingOffsetMode() {
        for (StartingOffsetsMode mode : StartingOffsetsMode.values()) {
            KafkaJobConfig config = KafkaJobConfig.fromArgs(new String[]{
                    "--starting-offsets", mode.name().toLowerCase()
            });
            assertNotNull(KafkaOrderEventSourceFactory.create(config));
        }
    }

    @Test
    void createsCheckpointedKafkaProcessingGraphWithoutContactingABroker() {
        StreamExecutionEnvironment environment =
                StreamExecutionEnvironment.getExecutionEnvironment();
        KafkaJobConfig config = KafkaJobConfig.fromArgs(new String[0]);

        KafkaOrderMetricsJob.configure(environment, config);
        String executionPlan = environment.getExecutionPlan();

        assertEquals(1, environment.getParallelism());
        assertEquals(10_000L, environment.getCheckpointConfig().getCheckpointInterval());
        assertEquals(
                CheckpointingMode.EXACTLY_ONCE,
                environment.getCheckpointConfig().getCheckpointingConsistencyMode());
        assertTrue(executionPlan.contains("consume-order-events-from-kafka"));
        assertTrue(executionPlan.contains("write-minute-metrics-to-clickhouse"));
        assertTrue(executionPlan.contains("write-rejected-events-to-clickhouse"));
        assertTrue(executionPlan.contains("write-late-events-to-clickhouse"));
        assertFalse(executionPlan.contains("print-rejected-events"));
        assertFalse(executionPlan.contains("print-late-events"));
    }

    @Test
    void canUseConsoleMetricsSinkForBrokerOnlyDebugging() {
        StreamExecutionEnvironment environment =
                StreamExecutionEnvironment.getExecutionEnvironment();
        KafkaJobConfig config = KafkaJobConfig.fromArgs(new String[]{
                "--metrics-sink", "print",
                "--anomaly-sink", "print"
        });

        KafkaOrderMetricsJob.configure(environment, config);
        String executionPlan = environment.getExecutionPlan();

        assertTrue(executionPlan.contains("print-minute-metrics"));
        assertTrue(executionPlan.contains("print-rejected-events"));
        assertTrue(executionPlan.contains("print-late-events"));
        assertFalse(executionPlan.contains("write-minute-metrics-to-clickhouse"));
        assertFalse(executionPlan.contains("write-rejected-events-to-clickhouse"));
        assertFalse(executionPlan.contains("write-late-events-to-clickhouse"));
    }
}
