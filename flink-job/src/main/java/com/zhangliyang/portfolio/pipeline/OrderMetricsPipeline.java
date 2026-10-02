package com.zhangliyang.portfolio.pipeline;

import com.zhangliyang.portfolio.core.OrderEventValidator;
import com.zhangliyang.portfolio.model.MinuteMetric;
import com.zhangliyang.portfolio.model.OrderEvent;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.windowing.assigners.TumblingEventTimeWindows;

import java.time.Duration;

public final class OrderMetricsPipeline {
    private OrderMetricsPipeline() {
    }

    public static DataStream<MinuteMetric> build(
            DataStream<OrderEvent> source,
            Duration outOfOrderness,
            Duration idleness,
            Duration deduplicationTtl) {
        if (source == null) {
            throw new IllegalArgumentException("source must not be null");
        }

        WatermarkStrategy<OrderEvent> watermarks = WatermarkStrategy
                .<OrderEvent>forBoundedOutOfOrderness(outOfOrderness)
                .withTimestampAssigner((event, previousTimestamp) -> event.getEventTime())
                .withIdleness(idleness);

        return source
                .filter(OrderEventValidator::isValid)
                .name("validate-order-events")
                .assignTimestampsAndWatermarks(watermarks)
                .name("assign-event-time-watermarks")
                .keyBy(OrderEvent::getEventId)
                .process(new DeduplicateByEventIdFunction(deduplicationTtl))
                .name("deduplicate-by-event-id")
                .keyBy(new RegionChannelKeySelector())
                .window(TumblingEventTimeWindows.of(Duration.ofMinutes(1)))
                .aggregate(new OrderAggregateFunction(), new AttachWindowMetadataFunction())
                .name("aggregate-minute-metrics");
    }
}

