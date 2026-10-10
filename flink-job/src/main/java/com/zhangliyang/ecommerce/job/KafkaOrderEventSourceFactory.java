package com.zhangliyang.ecommerce.job;

import org.apache.flink.api.common.serialization.SimpleStringSchema;
import org.apache.flink.connector.kafka.source.KafkaSource;
import org.apache.flink.connector.kafka.source.enumerator.initializer.OffsetsInitializer;
import org.apache.kafka.clients.consumer.OffsetResetStrategy;

public final class KafkaOrderEventSourceFactory {
    private KafkaOrderEventSourceFactory() {
    }

    public static KafkaSource<String> create(KafkaJobConfig config) {
        if (config == null) {
            throw new IllegalArgumentException("config must not be null");
        }
        return KafkaSource.<String>builder()
                .setBootstrapServers(config.getBootstrapServers())
                .setTopics(config.getTopic())
                .setGroupId(config.getGroupId())
                .setStartingOffsets(startingOffsets(config.getStartingOffsetsMode()))
                .setValueOnlyDeserializer(new SimpleStringSchema())
                .setProperty("partition.discovery.interval.ms", "10000")
                .build();
    }

    private static OffsetsInitializer startingOffsets(StartingOffsetsMode mode) {
        switch (mode) {
            case EARLIEST:
                return OffsetsInitializer.earliest();
            case LATEST:
                return OffsetsInitializer.latest();
            case COMMITTED:
                return OffsetsInitializer.committedOffsets(OffsetResetStrategy.EARLIEST);
            default:
                throw new IllegalArgumentException("unsupported starting offsets mode: " + mode);
        }
    }
}
