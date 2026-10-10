package com.zhangliyang.ecommerce.core;

import com.zhangliyang.ecommerce.model.OrderEvent;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderEventValidatorTest {
    @Test
    void acceptsAValidEvent() {
        OrderEvent event = event("evt-1", 1_000L, 1_005L, new BigDecimal("12.50"));
        assertTrue(OrderEventValidator.isValid(event));
    }

    @Test
    void rejectsAnIngestTimeBeforeEventTime() {
        OrderEvent event = event("evt-1", 2_000L, 1_999L, new BigDecimal("12.50"));
        assertFalse(OrderEventValidator.isValid(event));
    }

    @Test
    void rejectsUnsupportedDimensionsAndNonPositiveAmount() {
        OrderEvent event = event("evt-1", 1_000L, 1_000L, BigDecimal.ZERO);
        event.setRegion("未知地区");
        assertFalse(OrderEventValidator.isValid(event));
    }

    private static OrderEvent event(
            String eventId,
            long eventTime,
            long ingestTime,
            BigDecimal amount) {
        return new OrderEvent(
                eventId,
                "order-1",
                eventTime,
                ingestTime,
                "辽宁",
                "app",
                amount);
    }
}

