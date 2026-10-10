package com.zhangliyang.ecommerce.pipeline;

import com.zhangliyang.ecommerce.model.MinuteMetric;
import com.zhangliyang.ecommerce.model.OrderEvent;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.util.CloseableIterator;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderMetricsPipelineTest {
    private static final long BASE_MINUTE = 1_759_395_600_000L;

    @Test
    void deduplicatesAndAggregatesByEventMinuteRegionAndChannel() throws Exception {
        StreamExecutionEnvironment environment =
                StreamExecutionEnvironment.getExecutionEnvironment();
        environment.setParallelism(1);

        OrderEvent first = event(
                "evt-1", "order-1", BASE_MINUTE + 5_000L, "辽宁", "app", "10.10");
        OrderEvent duplicate = event(
                "evt-1", "order-1", BASE_MINUTE + 5_000L, "辽宁", "app", "10.10");
        OrderEvent second = event(
                "evt-2", "order-2", BASE_MINUTE + 30_000L, "辽宁", "app", "20.20");
        OrderEvent otherDimension = event(
                "evt-3", "order-3", BASE_MINUTE + 35_000L, "北京", "web", "5.00");
        OrderEvent invalid = event(
                "evt-4", "order-4", BASE_MINUTE + 40_000L, "辽宁", "app", "1.00");
        invalid.setIngestTime(invalid.getEventTime() - 1L);

        DataStream<MinuteMetric> metrics = OrderMetricsPipeline.build(
                environment.fromData(first, duplicate, second, otherDimension, invalid),
                Duration.ZERO,
                Duration.ofSeconds(30),
                Duration.ofHours(24));

        List<MinuteMetric> results = new ArrayList<>();
        try (CloseableIterator<MinuteMetric> iterator = metrics.executeAndCollect()) {
            iterator.forEachRemaining(results::add);
        }
        results.sort(Comparator.comparing(MinuteMetric::getRegion));

        assertEquals(2, results.size());
        MinuteMetric beijing = results.get(0);
        assertEquals("北京", beijing.getRegion());
        assertEquals("web", beijing.getChannel());
        assertEquals(1L, beijing.getOrderCount());
        assertEquals(new BigDecimal("5.00"), beijing.getGmv());

        MinuteMetric liaoning = results.get(1);
        assertEquals("辽宁", liaoning.getRegion());
        assertEquals("app", liaoning.getChannel());
        assertEquals(2L, liaoning.getOrderCount());
        assertEquals(new BigDecimal("30.30"), liaoning.getGmv());
        assertEquals(BASE_MINUTE, liaoning.getWindowStart());
        assertEquals(BASE_MINUTE + 60_000L, liaoning.getWindowEnd());
    }

    private static OrderEvent event(
            String eventId,
            String orderId,
            long eventTime,
            String region,
            String channel,
            String amount) {
        return new OrderEvent(
                eventId,
                orderId,
                eventTime,
                eventTime + 2_000L,
                region,
                channel,
                new BigDecimal(amount));
    }
}

