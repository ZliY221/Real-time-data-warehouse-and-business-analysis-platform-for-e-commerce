package com.zhangliyang.portfolio.job;

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
                    "parallelism")));

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
            int parallelism) {
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
                integer(options, "parallelism", 1));
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
}
