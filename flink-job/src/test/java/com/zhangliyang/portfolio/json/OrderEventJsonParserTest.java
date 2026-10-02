package com.zhangliyang.portfolio.json;

import com.zhangliyang.portfolio.model.OrderEvent;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderEventJsonParserTest {
    private final OrderEventJsonParser parser = new OrderEventJsonParser();

    @Test
    void parsesAValidOrderCreatedEvent() {
        OrderEventParseResult result = parser.parse(validJson("559.30"));

        assertTrue(result.isAccepted());
        OrderEvent event = result.getEvent();
        assertEquals("evt-1", event.getEventId());
        assertEquals("ord-1", event.getOrderId());
        assertEquals("辽宁", event.getRegion());
        assertEquals("app", event.getChannel());
        assertEquals(new BigDecimal("559.30"), event.getTotalAmount());
    }

    @Test
    void rejectsMalformedJson() {
        OrderEventParseResult result = parser.parse("{not-json}");

        assertFalse(result.isAccepted());
        assertEquals("malformed_json", result.getRejection().getErrorType());
    }

    @Test
    void rejectsAJsonArrayRoot() {
        OrderEventParseResult result = parser.parse("[]");

        assertFalse(result.isAccepted());
        assertEquals("invalid_json_shape", result.getRejection().getErrorType());
    }

    @Test
    void rejectsNumericMoneyBecauseTheContractRequiresAString() {
        String json = validJson("559.30").replace("\"559.30\"", "559.30");
        OrderEventParseResult result = parser.parse(json);

        assertFalse(result.isAccepted());
        assertEquals("invalid_field", result.getRejection().getErrorType());
    }

    @Test
    void rejectsMoneyWithoutTwoDecimalPlaces() {
        OrderEventParseResult result = parser.parse(validJson("559.3"));

        assertFalse(result.isAccepted());
        assertEquals("invalid_field", result.getRejection().getErrorType());
    }

    @Test
    void parsesEverySharedPythonSampleEvent() throws IOException {
        Path sample = Path.of("..", "data", "sample", "order_events.ndjson");
        List<String> lines = Files.readAllLines(sample);

        assertEquals(20, lines.size());
        for (String line : lines) {
            assertTrue(parser.parse(line).isAccepted());
        }
    }

    private static String validJson(String totalAmount) {
        return "{" +
                "\"schema_version\":\"1.0\"," +
                "\"event_id\":\"evt-1\"," +
                "\"event_type\":\"order_created\"," +
                "\"event_time\":\"2026-10-02T10:00:00Z\"," +
                "\"ingest_time\":\"2026-10-02T10:00:03Z\"," +
                "\"source\":\"order-service\"," +
                "\"payload\":{" +
                "\"order_id\":\"ord-1\"," +
                "\"user_id\":\"usr-1\"," +
                "\"region\":\"辽宁\"," +
                "\"channel\":\"app\"," +
                "\"currency\":\"CNY\"," +
                "\"total_amount\":\"" + totalAmount + "\"," +
                "\"items\":[]}}";
    }
}

