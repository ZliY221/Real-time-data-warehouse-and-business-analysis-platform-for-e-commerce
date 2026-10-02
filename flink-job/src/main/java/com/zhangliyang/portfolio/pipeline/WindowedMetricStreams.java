package com.zhangliyang.portfolio.pipeline;

import com.zhangliyang.portfolio.model.MinuteMetric;
import com.zhangliyang.portfolio.model.OrderEvent;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.datastream.SingleOutputStreamOperator;

public final class WindowedMetricStreams {
    private final SingleOutputStreamOperator<MinuteMetric> metrics;
    private final DataStream<OrderEvent> lateEvents;

    public WindowedMetricStreams(
            SingleOutputStreamOperator<MinuteMetric> metrics,
            DataStream<OrderEvent> lateEvents) {
        this.metrics = metrics;
        this.lateEvents = lateEvents;
    }

    public SingleOutputStreamOperator<MinuteMetric> getMetrics() {
        return metrics;
    }

    public DataStream<OrderEvent> getLateEvents() {
        return lateEvents;
    }
}

