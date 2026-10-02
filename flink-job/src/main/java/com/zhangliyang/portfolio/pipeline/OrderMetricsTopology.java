package com.zhangliyang.portfolio.pipeline;

import com.zhangliyang.portfolio.model.MinuteMetric;
import com.zhangliyang.portfolio.model.OrderEvent;
import com.zhangliyang.portfolio.model.RejectedEvent;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.datastream.SingleOutputStreamOperator;

public final class OrderMetricsTopology {
    private final SingleOutputStreamOperator<MinuteMetric> metrics;
    private final DataStream<RejectedEvent> rejectedEvents;
    private final DataStream<OrderEvent> lateEvents;

    public OrderMetricsTopology(
            SingleOutputStreamOperator<MinuteMetric> metrics,
            DataStream<RejectedEvent> rejectedEvents,
            DataStream<OrderEvent> lateEvents) {
        this.metrics = metrics;
        this.rejectedEvents = rejectedEvents;
        this.lateEvents = lateEvents;
    }

    public SingleOutputStreamOperator<MinuteMetric> getMetrics() {
        return metrics;
    }

    public DataStream<RejectedEvent> getRejectedEvents() {
        return rejectedEvents;
    }

    public DataStream<OrderEvent> getLateEvents() {
        return lateEvents;
    }
}

