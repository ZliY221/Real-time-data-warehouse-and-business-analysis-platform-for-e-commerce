package com.zhangliyang.ecommerce.sink;

import com.zhangliyang.ecommerce.model.ProductMetric;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Proxy;
import java.math.BigDecimal;
import java.sql.PreparedStatement;
import java.sql.Timestamp;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ClickHouseProductMetricStatementTest {
    @Test
    void bindsTheProductMetricUsingExactDecimalValues() throws Exception {
        Map<Integer, Object> values = new HashMap<>();
        PreparedStatement statement = recordingStatement(values);
        ProductMetric metric = new ProductMetric(
                1_767_225_600_000L, 1_767_225_660_000L, "数码配件", "SKU-1001",
                4L, 9L, new BigDecimal("359.10"));

        new ClickHouseProductMetricStatement().accept(statement, metric);

        assertEquals(1_767_225_600_000L, ((Timestamp) values.get(1)).getTime());
        assertEquals(1_767_225_660_000L, ((Timestamp) values.get(2)).getTime());
        assertEquals("数码配件", values.get(3));
        assertEquals("SKU-1001", values.get(4));
        assertEquals(4L, values.get(5));
        assertEquals(9L, values.get(6));
        assertEquals(new BigDecimal("359.10"), values.get(7));
        assertTrue((long) values.get(8) > 0L);
        assertTrue(((Timestamp) values.get(9)).getTime() > 0L);
    }

    private static PreparedStatement recordingStatement(Map<Integer, Object> values) {
        return (PreparedStatement) Proxy.newProxyInstance(
                ClickHouseProductMetricStatementTest.class.getClassLoader(),
                new Class<?>[]{PreparedStatement.class},
                (proxy, method, arguments) -> {
                    if (method.getName().startsWith("set") && arguments != null
                            && arguments.length >= 2 && arguments[0] instanceof Integer) {
                        values.put((Integer) arguments[0], arguments[1]);
                        return null;
                    }
                    if (method.getReturnType() == boolean.class) return false;
                    if (method.getReturnType() == int.class) return 0;
                    if (method.getReturnType() == long.class) return 0L;
                    return null;
                });
    }
}
