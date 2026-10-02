package com.zhangliyang.portfolio.json;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.zhangliyang.portfolio.core.OrderEventValidator;
import com.zhangliyang.portfolio.model.OrderEvent;
import com.zhangliyang.portfolio.model.RejectedEvent;

import java.math.BigDecimal;
import java.time.DateTimeException;
import java.time.Instant;

public class OrderEventJsonParser {
    private final ObjectMapper objectMapper;

    public OrderEventJsonParser() {
        this(new ObjectMapper());
    }

    OrderEventJsonParser(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public OrderEventParseResult parse(String rawPayload) {
        if (rawPayload == null || rawPayload.trim().isEmpty()) {
            return rejected(rawPayload, "empty_payload", "payload must not be blank");
        }

        try {
            JsonNode root = objectMapper.readTree(rawPayload);
            if (root == null || !root.isObject()) {
                return rejected(rawPayload, "invalid_json_shape", "root must be a JSON object");
            }
            JsonNode payload = requireObject(root, "payload");
            OrderEvent event = new OrderEvent(
                    requireText(root, "event_id"),
                    requireText(payload, "order_id"),
                    parseInstantMillis(requireText(root, "event_time"), "event_time"),
                    parseInstantMillis(requireText(root, "ingest_time"), "ingest_time"),
                    requireText(payload, "region"),
                    requireText(payload, "channel"),
                    parseMoney(requireText(payload, "total_amount")));

            if (!OrderEventValidator.isValid(event)) {
                return rejected(
                        rawPayload,
                        "business_validation_failed",
                        "event violates the order_created v1 business rules");
            }
            return OrderEventParseResult.accepted(event);
        } catch (JsonProcessingException error) {
            return rejected(rawPayload, "malformed_json", error.getOriginalMessage());
        } catch (IllegalArgumentException | DateTimeException error) {
            return rejected(rawPayload, "invalid_field", error.getMessage());
        }
    }

    private static JsonNode requireObject(JsonNode parent, String field) {
        JsonNode node = parent.get(field);
        if (node == null || !node.isObject()) {
            throw new IllegalArgumentException(field + " must be an object");
        }
        return node;
    }

    private static String requireText(JsonNode parent, String field) {
        JsonNode node = parent.get(field);
        if (node == null || !node.isTextual() || node.textValue().trim().isEmpty()) {
            throw new IllegalArgumentException(field + " must be a non-empty string");
        }
        return node.textValue();
    }

    private static long parseInstantMillis(String value, String field) {
        try {
            return Instant.parse(value).toEpochMilli();
        } catch (DateTimeException error) {
            throw new IllegalArgumentException(field + " must be a UTC ISO-8601 timestamp", error);
        }
    }

    private static BigDecimal parseMoney(String value) {
        BigDecimal amount;
        try {
            amount = new BigDecimal(value);
        } catch (NumberFormatException error) {
            throw new IllegalArgumentException("total_amount must be a decimal string", error);
        }
        if (amount.scale() != 2) {
            throw new IllegalArgumentException("total_amount must have exactly two decimal places");
        }
        return amount;
    }

    private static OrderEventParseResult rejected(
            String rawPayload,
            String errorType,
            String reason) {
        return OrderEventParseResult.rejected(
                new RejectedEvent(rawPayload, errorType, reason));
    }
}

