package com.zhangliyang.ecommerce.sink;

import com.zhangliyang.ecommerce.model.MinuteMetric;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Proxy;
import java.math.BigDecimal;
import java.sql.PreparedStatement;
import java.sql.Timestamp;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ClickHouseMinuteMetricStatementTest {
    @Test
    void bindsEveryMetricColumnWithoutConvertingDecimalToDouble() throws Exception {
        Map<Integer, Object> values = new HashMap<>();
        PreparedStatement statement = recordingStatement(values);
        MinuteMetric metric = new MinuteMetric(
                1_767_225_600_000L,
                1_767_225_660_000L,
                "辽宁",
                "app",
                3L,
                new BigDecimal("123.45"));

        new ClickHouseMinuteMetricStatement().accept(statement, metric);

        assertEquals(1_767_225_600_000L, ((Timestamp) values.get(1)).getTime());
        assertEquals(1_767_225_660_000L, ((Timestamp) values.get(2)).getTime());
        assertEquals("辽宁", values.get(3));
        assertEquals("app", values.get(4));
        assertEquals(3L, values.get(5));
        assertEquals(new BigDecimal("123.45"), values.get(6));
        assertTrue((long) values.get(7) > 0L);
        assertTrue(((Timestamp) values.get(8)).getTime() > 0L);
    }

    @Test
    void assignsStrictlyIncreasingVersionsWithinOneSinkInstance() throws Exception {
        Map<Integer, Object> values = new HashMap<>();
        PreparedStatement statement = recordingStatement(values);
        ClickHouseMinuteMetricStatement builder = new ClickHouseMinuteMetricStatement();
        MinuteMetric metric = new MinuteMetric(
                1_000L,
                61_000L,
                "辽宁",
                "web",
                1L,
                new BigDecimal("10.00"));

        builder.accept(statement, metric);
        long first = (long) values.get(7);
        builder.accept(statement, metric);
        long second = (long) values.get(7);

        assertTrue(second > first);
    }

    private static PreparedStatement recordingStatement(Map<Integer, Object> values) {
        return (PreparedStatement) Proxy.newProxyInstance(
                ClickHouseMinuteMetricStatementTest.class.getClassLoader(),
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
