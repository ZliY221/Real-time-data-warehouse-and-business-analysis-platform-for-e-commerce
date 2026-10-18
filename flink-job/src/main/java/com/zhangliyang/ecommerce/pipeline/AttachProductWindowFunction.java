package com.zhangliyang.ecommerce.pipeline;

import com.zhangliyang.ecommerce.model.ProductMetric;
import org.apache.flink.api.java.tuple.Tuple2;
import org.apache.flink.streaming.api.functions.windowing.ProcessWindowFunction;
import org.apache.flink.streaming.api.windowing.windows.TimeWindow;
import org.apache.flink.util.Collector;

public class AttachProductWindowFunction extends ProcessWindowFunction<ProductMetricAccumulator, ProductMetric, Tuple2<String, String>, TimeWindow> {
    @Override
    public void process(Tuple2<String, String> key, Context context,
                        Iterable<ProductMetricAccumulator> values, Collector<ProductMetric> output) {
        ProductMetricAccumulator value = values.iterator().next();
        output.collect(new ProductMetric(context.window().getStart(), context.window().getEnd(),
                key.f0, key.f1, value.getOrderCount(), value.getUnitQuantity(), value.getGmv()));
    }
}
