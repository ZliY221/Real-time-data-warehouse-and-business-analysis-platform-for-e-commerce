package com.zhangliyang.portfolio.job;

import java.util.Locale;

public enum StartingOffsetsMode {
    COMMITTED,
    EARLIEST,
    LATEST;

    public static StartingOffsetsMode parse(String value) {
        if (value == null) {
            throw new IllegalArgumentException("starting offsets must not be null");
        }
        try {
            return valueOf(value.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException error) {
            throw new IllegalArgumentException(
                    "starting offsets must be one of: committed, earliest, latest",
                    error);
        }
    }
}
