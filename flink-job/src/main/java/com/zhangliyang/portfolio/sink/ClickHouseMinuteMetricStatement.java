package com.zhangliyang.portfolio.sink;

import com.zhangliyang.portfolio.model.MinuteMetric;
import org.apache.flink.connector.jdbc.JdbcStatementBuilder;

import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;

public final class ClickHouseMinuteMetricStatement
        implements JdbcStatementBuilder<MinuteMetric> {
    private static final long serialVersionUID = 1L;

    private final AtomicLong lastVersion = new AtomicLong();

    @Override
    public void accept(PreparedStatement statement, MinuteMetric metric) throws SQLException {
        if (statement == null) {
            throw new IllegalArgumentException("statement must not be null");
        }
        if (metric == null) {
            throw new IllegalArgumentException("metric must not be null");
        }

        long processedAt = System.currentTimeMillis();
        long version = lastVersion.updateAndGet(
                previous -> Math.max(processedAt, previous + 1));
        statement.setTimestamp(1, timestamp(metric.getWindowStart()));
        statement.setTimestamp(2, timestamp(metric.getWindowEnd()));
        statement.setString(3, metric.getRegion());
        statement.setString(4, metric.getChannel());
        statement.setLong(5, metric.getOrderCount());
        statement.setBigDecimal(6, metric.getGmv());
        statement.setLong(7, version);
        statement.setTimestamp(8, timestamp(processedAt));
    }

    private static Timestamp timestamp(long epochMilliseconds) {
        return Timestamp.from(Instant.ofEpochMilli(epochMilliseconds));
    }
}
