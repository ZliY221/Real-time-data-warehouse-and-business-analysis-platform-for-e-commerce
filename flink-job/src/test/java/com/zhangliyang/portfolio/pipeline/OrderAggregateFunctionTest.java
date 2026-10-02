package com.zhangliyang.portfolio.pipeline;

import com.zhangliyang.portfolio.model.OrderEvent;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderAggregateFunctionTest {
    @Test
    void accumulatesOrderCountAndGmvWithoutFloatingPointLoss() {
        OrderAggregateFunction function = new OrderAggregateFunction();
        OrderMetricAccumulator accumulator = function.createAccumulator();

        function.add(event("evt-1", "0.10"), accumulator);
        function.add(event("evt-2", "0.20"), accumulator);

        assertEquals(2L, accumulator.getOrderCount());
        assertEquals(new BigDecimal("0.30"), accumulator.getGmv());
    }

    @Test
    void mergesPartialAccumulators() {
        OrderAggregateFunction function = new OrderAggregateFunction();
        OrderMetricAccumulator first = function.createAccumulator();
        OrderMetricAccumulator second = function.createAccumulator();
        function.add(event("evt-1", "10.00"), first);
        function.add(event("evt-2", "20.00"), second);

        OrderMetricAccumulator merged = function.merge(first, second);

        assertEquals(2L, merged.getOrderCount());
        assertEquals(new BigDecimal("30.00"), merged.getGmv());
    }

    private static OrderEvent event(String eventId, String amount) {
        return new OrderEvent(
                eventId,
                "order-" + eventId,
                1_000L,
                1_001L,
                "辽宁",
                "app",
                new BigDecimal(amount));
    }
}

