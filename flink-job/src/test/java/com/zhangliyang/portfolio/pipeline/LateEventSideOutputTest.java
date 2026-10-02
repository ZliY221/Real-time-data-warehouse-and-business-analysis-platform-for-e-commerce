package com.zhangliyang.portfolio.pipeline;

import com.zhangliyang.portfolio.model.OrderEvent;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.streaming.api.functions.source.SourceFunction;
import org.apache.flink.streaming.api.watermark.Watermark;
import org.apache.flink.util.CloseableIterator;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LateEventSideOutputTest {
    private static final long BASE_MINUTE = 1_759_395_600_000L;

    @Test
    void routesAnEventBehindTheClosedWindowToTheLateSideOutput() throws Exception {
        StreamExecutionEnvironment environment =
                StreamExecutionEnvironment.getExecutionEnvironment();
        environment.setParallelism(1);

        WindowedMetricStreams streams = OrderMetricsPipeline.buildFromWatermarkedEvents(
                environment.addSource(new WatermarkThenLateSource()),
                Duration.ofHours(24),
                Duration.ZERO);

        List<OrderEvent> lateEvents = new ArrayList<>();
        try (CloseableIterator<OrderEvent> iterator =
                     streams.getLateEvents().executeAndCollect()) {
            iterator.forEachRemaining(lateEvents::add);
        }

        assertEquals(1, lateEvents.size());
        assertEquals("evt-late", lateEvents.get(0).getEventId());
    }

    @SuppressWarnings("deprecation")
    private static final class WatermarkThenLateSource
            implements SourceFunction<OrderEvent> {
        private static final long serialVersionUID = 1L;

        @Override
        public void run(SourceContext<OrderEvent> context) {
            synchronized (context.getCheckpointLock()) {
                OrderEvent onTime = event("evt-on-time", BASE_MINUTE + 125_000L);
                context.collectWithTimestamp(onTime, onTime.getEventTime());
                context.emitWatermark(new Watermark(BASE_MINUTE + 120_000L));

                OrderEvent late = event("evt-late", BASE_MINUTE + 5_000L);
                context.collectWithTimestamp(late, late.getEventTime());
                context.emitWatermark(new Watermark(Long.MAX_VALUE));
            }
        }

        @Override
        public void cancel() {
        }

        private static OrderEvent event(String eventId, long eventTime) {
            return new OrderEvent(
                    eventId,
                    "order-" + eventId,
                    eventTime,
                    eventTime + 1_000L,
                    "辽宁",
                    "app",
                    new BigDecimal("10.00"));
        }
    }
}

