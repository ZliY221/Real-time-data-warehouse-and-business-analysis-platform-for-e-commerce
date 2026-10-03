package com.zhangliyang.portfolio.sink;

import com.zhangliyang.portfolio.model.RejectedEvent;
import org.apache.flink.connector.jdbc.JdbcStatementBuilder;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;

public final class ClickHouseRejectedEventStatement
        implements JdbcStatementBuilder<RejectedEvent> {
    private static final long serialVersionUID = 1L;

    private final AtomicLong lastVersion = new AtomicLong();

    @Override
    public void accept(PreparedStatement statement, RejectedEvent event) throws SQLException {
        if (statement == null) {
            throw new IllegalArgumentException("statement must not be null");
        }
        if (event == null) {
            throw new IllegalArgumentException("event must not be null");
        }

        long detectedAt = System.currentTimeMillis();
        long version = lastVersion.updateAndGet(
                previous -> Math.max(detectedAt, previous + 1));
        statement.setString(1, fingerprint(event.getRawPayload()));
        statement.setString(2, event.getErrorType());
        statement.setInt(3, event.getPayloadSizeBytes());
        statement.setTimestamp(4, timestamp(detectedAt));
        statement.setLong(5, version);
    }

    static String fingerprint(String payload) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            String canonical = payload == null ? "null:" : "text:" + payload;
            byte[] hash = digest.digest(canonical.getBytes(StandardCharsets.UTF_8));
            StringBuilder value = new StringBuilder(hash.length * 2);
            for (byte part : hash) {
                value.append(String.format("%02x", part & 0xff));
            }
            return value.toString();
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 is unavailable", error);
        }
    }

    private static Timestamp timestamp(long epochMilliseconds) {
        return Timestamp.from(Instant.ofEpochMilli(epochMilliseconds));
    }
}
