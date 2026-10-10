package com.zhangliyang.ecommerce.job;

import java.util.Locale;

public enum MetricsSinkMode {
    CLICKHOUSE,
    PRINT,
    BOTH;

    public static MetricsSinkMode parse(String value) {
        return parse(value, "metrics sink");
    }

    public static MetricsSinkMode parse(String value, String optionName) {
        if (value == null) {
            throw new IllegalArgumentException(optionName + " mode must not be null");
        }
        try {
            return valueOf(value.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException error) {
            throw new IllegalArgumentException(
                    optionName + " must be one of: clickhouse, print, both",
                    error);
        }
    }

    public boolean writesClickHouse() {
        return this == CLICKHOUSE || this == BOTH;
    }

    public boolean writesConsole() {
        return this == PRINT || this == BOTH;
    }
}
