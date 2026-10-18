package com.zhangliyang.ecommerce.pipeline;

import com.zhangliyang.ecommerce.model.MinuteMetric;
import com.zhangliyang.ecommerce.model.OrderEvent;
import com.zhangliyang.ecommerce.model.ProductMetric;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.datastream.SingleOutputStreamOperator;

public final class WindowedMetricStreams {
    private final SingleOutputStreamOperator<MinuteMetric> metrics;
    private final DataStream<OrderEvent> lateEvents;
    private final SingleOutputStreamOperator<ProductMetric> productMetrics;

    public WindowedMetricStreams(
            SingleOutputStreamOperator<MinuteMetric> metrics,
            DataStream<OrderEvent> lateEvents,
            SingleOutputStreamOperator<ProductMetric> productMetrics) {
        this.metrics = metrics;
        this.lateEvents = lateEvents;
        this.productMetrics = productMetrics;
    }

    public SingleOutputStreamOperator<MinuteMetric> getMetrics() {
        return metrics;
    }

    public DataStream<OrderEvent> getLateEvents() {
        return lateEvents;
    }

    public SingleOutputStreamOperator<ProductMetric> getProductMetrics() { return productMetrics; }
}

