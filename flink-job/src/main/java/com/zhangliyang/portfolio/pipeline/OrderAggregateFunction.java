package com.zhangliyang.portfolio.pipeline;

import com.zhangliyang.portfolio.model.OrderEvent;
import org.apache.flink.api.common.functions.AggregateFunction;

public class OrderAggregateFunction
        implements AggregateFunction<OrderEvent, OrderMetricAccumulator, OrderMetricAccumulator> {

    @Override
    public OrderMetricAccumulator createAccumulator() {
        return new OrderMetricAccumulator();
    }

    @Override
    public OrderMetricAccumulator add(OrderEvent value, OrderMetricAccumulator accumulator) {
        accumulator.add(value.getTotalAmount());
        return accumulator;
    }

    @Override
    public OrderMetricAccumulator getResult(OrderMetricAccumulator accumulator) {
        return accumulator;
    }

    @Override
    public OrderMetricAccumulator merge(
            OrderMetricAccumulator first,
            OrderMetricAccumulator second) {
        first.merge(second);
        return first;
    }
}

