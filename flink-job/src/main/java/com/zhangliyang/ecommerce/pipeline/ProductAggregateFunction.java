package com.zhangliyang.ecommerce.pipeline;

import com.zhangliyang.ecommerce.model.ProductContribution;
import org.apache.flink.api.common.functions.AggregateFunction;

public class ProductAggregateFunction implements AggregateFunction<ProductContribution, ProductMetricAccumulator, ProductMetricAccumulator> {
    @Override public ProductMetricAccumulator createAccumulator() { return new ProductMetricAccumulator(); }
    @Override public ProductMetricAccumulator add(ProductContribution value, ProductMetricAccumulator accumulator) {
        accumulator.add(value.getQuantity(), value.getLineAmount());
        return accumulator;
    }
    @Override public ProductMetricAccumulator getResult(ProductMetricAccumulator accumulator) { return accumulator; }
    @Override public ProductMetricAccumulator merge(ProductMetricAccumulator left, ProductMetricAccumulator right) {
        left.merge(right);
        return left;
    }
}
