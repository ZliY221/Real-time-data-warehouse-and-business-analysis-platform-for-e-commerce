package com.zhangliyang.portfolio.job;

import java.util.Locale;

public enum MetricsSinkMode {
    CLICKHOUSE,
    PRINT,
    BOTH;

    public static MetricsSinkMode parse(String value) {
        if (value == null) {
            throw new IllegalArgumentException("metrics sink mode must not be null");
        }
        try {
            return valueOf(value.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException error) {
            throw new IllegalArgumentException(
                    "metrics sink must be one of: clickhouse, print, both",
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
