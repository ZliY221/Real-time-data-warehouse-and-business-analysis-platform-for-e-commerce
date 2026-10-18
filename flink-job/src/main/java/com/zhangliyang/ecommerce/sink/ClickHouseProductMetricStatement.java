package com.zhangliyang.ecommerce.sink;

import com.zhangliyang.ecommerce.model.ProductMetric;
import org.apache.flink.connector.jdbc.JdbcStatementBuilder;

import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;

public final class ClickHouseProductMetricStatement implements JdbcStatementBuilder<ProductMetric> {
    private static final long serialVersionUID = 1L;
    private final AtomicLong lastVersion = new AtomicLong();

    @Override
    public void accept(PreparedStatement statement, ProductMetric metric) throws SQLException {
        long processedAt = System.currentTimeMillis();
        long version = lastVersion.updateAndGet(previous -> Math.max(processedAt, previous + 1));
        statement.setTimestamp(1, Timestamp.from(Instant.ofEpochMilli(metric.getWindowStart())));
        statement.setTimestamp(2, Timestamp.from(Instant.ofEpochMilli(metric.getWindowEnd())));
        statement.setString(3, metric.getCategory());
        statement.setString(4, metric.getSkuId());
        statement.setLong(5, metric.getOrderCount());
        statement.setLong(6, metric.getUnitQuantity());
        statement.setBigDecimal(7, metric.getGmv());
        statement.setLong(8, version);
        statement.setTimestamp(9, Timestamp.from(Instant.ofEpochMilli(processedAt)));
    }
}
