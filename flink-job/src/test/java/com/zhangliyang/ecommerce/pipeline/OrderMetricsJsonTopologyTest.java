package com.zhangliyang.ecommerce.pipeline;

import com.zhangliyang.ecommerce.model.MinuteMetric;
import com.zhangliyang.ecommerce.model.RejectedEvent;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.util.CloseableIterator;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderMetricsJsonTopologyTest {
    @Test
    void routesMalformedAndBusinessInvalidEventsToTheQualitySideOutput() throws Exception {
        StreamExecutionEnvironment environment =
                StreamExecutionEnvironment.getExecutionEnvironment();
        environment.setParallelism(1);

        String valid = json("evt-1", "2026-10-02T10:00:00Z", "10.00");
        String invalidBusiness = json("evt-2", "2026-10-02T10:00:01Z", "-1.00");
        String malformed = "{not-json}";

        OrderMetricsTopology topology = OrderMetricsPipeline.buildFromJson(
                environment.fromData(valid, invalidBusiness, malformed),
                Duration.ZERO,
                Duration.ofSeconds(30),
                Duration.ofHours(24),
                Duration.ZERO);

        List<MinuteMetric> metrics = collect(topology.getMetrics().executeAndCollect());
        assertEquals(1, metrics.size());
        assertEquals(1L, metrics.get(0).getOrderCount());

        List<RejectedEvent> rejected = collect(
                topology.getRejectedEvents().executeAndCollect());
        assertEquals(2, rejected.size());
    }

    private static <T> List<T> collect(CloseableIterator<T> iterator) throws Exception {
        try (CloseableIterator<T> closeable = iterator) {
            List<T> values = new ArrayList<>();
            closeable.forEachRemaining(values::add);
            return values;
        }
    }

    private static String json(String eventId, String eventTime, String amount) {
        return "{" +
                "\"event_id\":\"" + eventId + "\"," +
                "\"event_time\":\"" + eventTime + "\"," +
                "\"ingest_time\":\"2026-10-02T10:00:05Z\"," +
                "\"payload\":{" +
                "\"order_id\":\"ord-1\"," +
                "\"region\":\"辽宁\"," +
                "\"channel\":\"app\"," +
                "\"total_amount\":\"" + amount + "\"}}";
    }
}

