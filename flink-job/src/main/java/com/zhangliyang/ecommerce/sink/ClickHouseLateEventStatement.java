package com.zhangliyang.ecommerce.sink;

import com.zhangliyang.ecommerce.model.OrderEvent;
import org.apache.flink.connector.jdbc.JdbcStatementBuilder;

import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;

public final class ClickHouseLateEventStatement
        implements JdbcStatementBuilder<OrderEvent> {
    private static final long serialVersionUID = 1L;

    private final AtomicLong lastVersion = new AtomicLong();

    @Override
    public void accept(PreparedStatement statement, OrderEvent event) throws SQLException {
        if (statement == null) {
            throw new IllegalArgumentException("statement must not be null");
        }
        if (event == null) {
            throw new IllegalArgumentException("event must not be null");
        }

        long detectedAt = System.currentTimeMillis();
        long version = lastVersion.updateAndGet(
                previous -> Math.max(detectedAt, previous + 1));
        statement.setString(1, event.getEventId());
        statement.setString(2, event.getOrderId());
        statement.setTimestamp(3, timestamp(event.getEventTime()));
        statement.setTimestamp(4, timestamp(event.getIngestTime()));
        statement.setString(5, event.getRegion());
        statement.setString(6, event.getChannel());
        statement.setBigDecimal(7, event.getTotalAmount());
        statement.setTimestamp(8, timestamp(detectedAt));
        statement.setLong(9, version);
    }

    private static Timestamp timestamp(long epochMilliseconds) {
        return Timestamp.from(Instant.ofEpochMilli(epochMilliseconds));
    }
}
