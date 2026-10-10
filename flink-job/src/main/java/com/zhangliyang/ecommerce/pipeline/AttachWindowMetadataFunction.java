package com.zhangliyang.ecommerce.pipeline;

import com.zhangliyang.ecommerce.model.MinuteMetric;
import org.apache.flink.api.java.tuple.Tuple2;
import org.apache.flink.streaming.api.functions.windowing.ProcessWindowFunction;
import org.apache.flink.streaming.api.windowing.windows.TimeWindow;
import org.apache.flink.util.Collector;

public class AttachWindowMetadataFunction extends ProcessWindowFunction<
        OrderMetricAccumulator,
        MinuteMetric,
        Tuple2<String, String>,
        TimeWindow> {

    @Override
    public void process(
            Tuple2<String, String> key,
            Context context,
            Iterable<OrderMetricAccumulator> values,
            Collector<MinuteMetric> output) {
        OrderMetricAccumulator value = values.iterator().next();
        output.collect(new MinuteMetric(
                context.window().getStart(),
                context.window().getEnd(),
                key.f0,
                key.f1,
                value.getOrderCount(),
                value.getGmv()));
    }
}

