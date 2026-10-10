package com.zhangliyang.ecommerce.job;

import java.time.Duration;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

public final class KafkaJobConfig {
    private static final Set<String> SUPPORTED_OPTIONS = Collections.unmodifiableSet(
            new LinkedHashSet<>(Arrays.asList(
                    "bootstrap-servers",
                    "topic",
                    "group-id",
                    "starting-offsets",
                    "out-of-orderness-seconds",
                    "idleness-seconds",
                    "deduplication-ttl-hours",
                    "allowed-lateness-seconds",
                    "checkpoint-interval-seconds",
                    "parallelism",
                    "metrics-sink",
                    "anomaly-sink",
                    "clickhouse-url",
                    "clickhouse-user",
                    "clickhouse-batch-size",
                    "clickhouse-batch-interval-ms",
                    "clickhouse-max-retries")));

    private final String bootstrapServers;
    private final String topic;
    private final String groupId;
    private final StartingOffsetsMode startingOffsetsMode;
    private final Duration outOfOrderness;
    private final Duration idleness;
    private final Duration deduplicationTtl;
    private final Duration allowedLateness;
    private final Duration checkpointInterval;
    private final int parallelism;
    private final MetricsSinkMode metricsSinkMode;
    private final MetricsSinkMode anomalySinkMode;
    private final String clickHouseUrl;
    private final String clickHouseUser;
    private final int clickHouseBatchSize;
    private final Duration clickHouseBatchInterval;
    private final int clickHouseMaxRetries;

    public KafkaJobConfig(
            String bootstrapServers,
            String topic,
            String groupId,
            StartingOffsetsMode startingOffsetsMode,
            Duration outOfOrderness,
            Duration idleness,
            Duration deduplicationTtl,
            Duration allowedLateness,
            Duration checkpointInterval,
            int parallelism,
            MetricsSinkMode metricsSinkMode,
            MetricsSinkMode anomalySinkMode,
            String clickHouseUrl,
            String clickHouseUser,
            int clickHouseBatchSize,
            Duration clickHouseBatchInterval,
            int clickHouseMaxRetries) {
        this.bootstrapServers = requireText(bootstrapServers, "bootstrap servers");
        this.topic = requireText(topic, "topic");
        this.groupId = requireText(groupId, "group id");
        if (startingOffsetsMode == null) {
            throw new IllegalArgumentException("starting offsets mode must not be null");
        }
        this.startingOffsetsMode = startingOffsetsMode;
        this.outOfOrderness = requireNonNegative(outOfOrderness, "out of orderness");
        this.idleness = requirePositive(idleness, "idleness");
        this.deduplicationTtl = requirePositive(deduplicationTtl, "deduplication TTL");
        this.allowedLateness = requireNonNegative(allowedLateness, "allowed lateness");
        this.checkpointInterval = requirePositive(checkpointInterval, "checkpoint interval");
        if (parallelism <= 0) {
            throw new IllegalArgumentException("parallelism must be greater than zero");
        }
        this.parallelism = parallelism;
        if (metricsSinkMode == null) {
            throw new IllegalArgumentException("metrics sink mode must not be null");
        }
        this.metricsSinkMode = metricsSinkMode;
        if (anomalySinkMode == null) {
            throw new IllegalArgumentException("anomaly sink mode must not be null");
        }
        this.anomalySinkMode = anomalySinkMode;
        this.clickHouseUrl = requireClickHouseUrl(clickHouseUrl);
        this.clickHouseUser = requireText(clickHouseUser, "ClickHouse user");
        if (clickHouseBatchSize <= 0) {
            throw new IllegalArgumentException("ClickHouse batch size must be greater than zero");
        }
        this.clickHouseBatchSize = clickHouseBatchSize;
        this.clickHouseBatchInterval = requirePositive(
                clickHouseBatchInterval,
                "ClickHouse batch interval");
        if (clickHouseMaxRetries < 0) {
            throw new IllegalArgumentException("ClickHouse max retries must not be negative");
        }
        this.clickHouseMaxRetries = clickHouseMaxRetries;
    }

    public static KafkaJobConfig fromArgs(String[] args) {
        Map<String, String> options = parseOptions(args);
        return new KafkaJobConfig(
                options.getOrDefault("bootstrap-servers", "localhost:9092"),
                options.getOrDefault("topic", "order-events"),
                options.getOrDefault("group-id", "ecommerce-order-metrics"),
                StartingOffsetsMode.parse(options.getOrDefault("starting-offsets", "committed")),
                seconds(options, "out-of-orderness-seconds", 10),
                seconds(options, "idleness-seconds", 60),
                hours(options, "deduplication-ttl-hours", 24),
                seconds(options, "allowed-lateness-seconds", 0),
                seconds(options, "checkpoint-interval-seconds", 10),
                integer(options, "parallelism", 1),
                MetricsSinkMode.parse(options.getOrDefault("metrics-sink", "clickhouse")),
                MetricsSinkMode.parse(
                        options.getOrDefault("anomaly-sink", "clickhouse"),
                        "anomaly sink"),
                options.getOrDefault(
                        "clickhouse-url",
                        "jdbc:clickhouse://localhost:8123/ecommerce"),
                options.getOrDefault("clickhouse-user", "default"),
                integer(options, "clickhouse-batch-size", 100),
                milliseconds(options, "clickhouse-batch-interval-ms", 1_000),
                integer(options, "clickhouse-max-retries", 3));
    }

    private static Map<String, String> parseOptions(String[] args) {
        if (args == null) {
            throw new IllegalArgumentException("arguments must not be null");
        }
        Map<String, String> options = new LinkedHashMap<>();
        for (int index = 0; index < args.length; index += 2) {
            String option = args[index];
            if (!option.startsWith("--") || option.length() == 2) {
                throw new IllegalArgumentException("expected an option beginning with --: " + option);
            }
            String key = option.substring(2);
            if (!SUPPORTED_OPTIONS.contains(key)) {
                throw new IllegalArgumentException("unsupported option: --" + key);
            }
            if (index + 1 >= args.length || args[index + 1].startsWith("--")) {
                throw new IllegalArgumentException("missing value for option: --" + key);
            }
            if (options.putIfAbsent(key, args[index + 1]) != null) {
                throw new IllegalArgumentException("duplicate option: --" + key);
            }
        }
        return options;
    }

    private static Duration seconds(Map<String, String> options, String key, long defaultValue) {
        return Duration.ofSeconds(longValue(options, key, defaultValue));
    }

    private static Duration hours(Map<String, String> options, String key, long defaultValue) {
        return Duration.ofHours(longValue(options, key, defaultValue));
    }

    private static Duration milliseconds(
            Map<String, String> options,
            String key,
            long defaultValue) {
        return Duration.ofMillis(longValue(options, key, defaultValue));
    }

    private static int integer(Map<String, String> options, String key, int defaultValue) {
        String value = options.get(key);
        if (value == null) {
            return defaultValue;
        }
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException error) {
            throw new IllegalArgumentException("--" + key + " must be an integer", error);
        }
    }

    private static long longValue(Map<String, String> options, String key, long defaultValue) {
        String value = options.get(key);
        if (value == null) {
            return defaultValue;
        }
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException error) {
            throw new IllegalArgumentException("--" + key + " must be an integer", error);
        }
    }

    private static String requireText(String value, String name) {
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
        return value.trim();
    }

    private static Duration requirePositive(Duration value, String name) {
        if (value == null || value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException(name + " must be greater than zero");
        }
        return value;
    }

    private static Duration requireNonNegative(Duration value, String name) {
        if (value == null || value.isNegative()) {
            throw new IllegalArgumentException(name + " must not be negative");
        }
        return value;
    }

    private static String requireClickHouseUrl(String value) {
        String url = requireText(value, "ClickHouse URL");
        if (!url.startsWith("jdbc:clickhouse://")) {
            throw new IllegalArgumentException(
                    "ClickHouse URL must begin with jdbc:clickhouse://");
        }
        return url;
    }

    public String getBootstrapServers() {
        return bootstrapServers;
    }

    public String getTopic() {
        return topic;
    }

    public String getGroupId() {
        return groupId;
    }

    public StartingOffsetsMode getStartingOffsetsMode() {
        return startingOffsetsMode;
    }

    public Duration getOutOfOrderness() {
        return outOfOrderness;
    }

    public Duration getIdleness() {
        return idleness;
    }

    public Duration getDeduplicationTtl() {
        return deduplicationTtl;
    }

    public Duration getAllowedLateness() {
        return allowedLateness;
    }

    public Duration getCheckpointInterval() {
        return checkpointInterval;
    }

    public int getParallelism() {
        return parallelism;
    }

    public MetricsSinkMode getMetricsSinkMode() {
        return metricsSinkMode;
    }

    public MetricsSinkMode getAnomalySinkMode() {
        return anomalySinkMode;
    }

    public String getClickHouseUrl() {
        return clickHouseUrl;
    }

    public String getClickHouseUser() {
        return clickHouseUser;
    }

    public int getClickHouseBatchSize() {
        return clickHouseBatchSize;
    }

    public Duration getClickHouseBatchInterval() {
        return clickHouseBatchInterval;
    }

    public int getClickHouseMaxRetries() {
        return clickHouseMaxRetries;
    }
}
