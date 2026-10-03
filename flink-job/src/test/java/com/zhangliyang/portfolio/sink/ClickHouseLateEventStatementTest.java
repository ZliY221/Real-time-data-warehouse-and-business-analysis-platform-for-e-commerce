package com.zhangliyang.portfolio.sink;

import com.zhangliyang.portfolio.model.OrderEvent;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Proxy;
import java.math.BigDecimal;
import java.sql.PreparedStatement;
import java.sql.Timestamp;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ClickHouseLateEventStatementTest {
    @Test
    void bindsStableEventIdentityTimestampsDimensionsAndExactAmount() throws Exception {
        Map<Integer, Object> values = new HashMap<>();
        PreparedStatement statement = recordingStatement(values);
        OrderEvent event = event();

        new ClickHouseLateEventStatement().accept(statement, event);

        assertEquals("evt-late-1", values.get(1));
        assertEquals("ord-late-1", values.get(2));
        assertEquals(1_767_225_600_000L, ((Timestamp) values.get(3)).getTime());
        assertEquals(1_767_225_605_000L, ((Timestamp) values.get(4)).getTime());
        assertEquals("辽宁", values.get(5));
        assertEquals("app", values.get(6));
        assertEquals(new BigDecimal("123.45"), values.get(7));
        assertTrue(((Timestamp) values.get(8)).getTime() > 0L);
        assertTrue((long) values.get(9) > 0L);
    }

    @Test
    void assignsStrictlyIncreasingVersionsWithinOneSinkInstance() throws Exception {
        Map<Integer, Object> values = new HashMap<>();
        PreparedStatement statement = recordingStatement(values);
        ClickHouseLateEventStatement builder = new ClickHouseLateEventStatement();

        builder.accept(statement, event());
        long first = (long) values.get(9);
        builder.accept(statement, event());
        long second = (long) values.get(9);

        assertTrue(second > first);
    }

    private static OrderEvent event() {
        return new OrderEvent(
                "evt-late-1",
                "ord-late-1",
                1_767_225_600_000L,
                1_767_225_605_000L,
                "辽宁",
                "app",
                new BigDecimal("123.45"));
    }

    private static PreparedStatement recordingStatement(Map<Integer, Object> values) {
        return (PreparedStatement) Proxy.newProxyInstance(
                ClickHouseLateEventStatementTest.class.getClassLoader(),
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
