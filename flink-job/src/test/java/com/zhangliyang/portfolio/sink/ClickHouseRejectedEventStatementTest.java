package com.zhangliyang.portfolio.sink;

import com.zhangliyang.portfolio.model.RejectedEvent;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Proxy;
import java.sql.PreparedStatement;
import java.sql.Timestamp;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ClickHouseRejectedEventStatementTest {
    @Test
    void storesOnlyFingerprintTypeAndSizeInsteadOfTheRawPayload() throws Exception {
        Map<Integer, Object> values = new HashMap<>();
        PreparedStatement statement = recordingStatement(values);
        String rawPayload = "{\"email\":\"private@example.com\"}";
        RejectedEvent event = new RejectedEvent(
                rawPayload,
                "malformed_json",
                "diagnostic may include parser internals");

        new ClickHouseRejectedEventStatement().accept(statement, event);

        assertTrue(((String) values.get(1)).matches("[0-9a-f]{64}"));
        assertEquals("malformed_json", values.get(2));
        assertEquals(rawPayload.getBytes(java.nio.charset.StandardCharsets.UTF_8).length,
                values.get(3));
        assertTrue(((Timestamp) values.get(4)).getTime() > 0L);
        assertTrue((long) values.get(5) > 0L);
        assertFalse(values.containsValue(rawPayload));
        assertFalse(values.containsValue(event.getReason()));
    }

    @Test
    void fingerprintIsStableAndConsoleTextDoesNotRevealPayload() {
        String rawPayload = "private-user-payload";
        RejectedEvent event = new RejectedEvent(rawPayload, "invalid_field", "bad value");

        assertEquals(
                ClickHouseRejectedEventStatement.fingerprint(rawPayload),
                ClickHouseRejectedEventStatement.fingerprint(rawPayload));
        assertNotEquals(
                ClickHouseRejectedEventStatement.fingerprint(null),
                ClickHouseRejectedEventStatement.fingerprint("<null>"));
        assertFalse(event.toString().contains(rawPayload));
        assertTrue(event.toString().contains("payloadSizeBytes"));
    }

    private static PreparedStatement recordingStatement(Map<Integer, Object> values) {
        return (PreparedStatement) Proxy.newProxyInstance(
                ClickHouseRejectedEventStatementTest.class.getClassLoader(),
                new Class<?>[]{PreparedStatement.class},
                (proxy, method, arguments) -> {
                    if (method.getName().startsWith("set")
                            && arguments != null
                            && arguments.length >= 2
                            && arguments[0] instanceof Integer) {
                        values.put((Integer) arguments[0], arguments[1]);
                        return null;
                    }
                    Class<?> returnType = method.getReturnType();
                    if (returnType == boolean.class) {
                        return false;
                    }
                    if (returnType == int.class) {
                        return 0;
                    }
                    if (returnType == long.class) {
                        return 0L;
                    }
                    return null;
                });
    }
}
