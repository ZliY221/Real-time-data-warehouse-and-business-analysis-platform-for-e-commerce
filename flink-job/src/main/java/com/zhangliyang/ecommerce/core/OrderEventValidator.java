package com.zhangliyang.ecommerce.core;

import com.zhangliyang.ecommerce.model.OrderEvent;

import java.math.BigDecimal;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public final class OrderEventValidator {
    private static final Set<String> REGIONS = new HashSet<>(
            Arrays.asList("辽宁", "北京", "上海", "广东", "四川"));
    private static final Set<String> CHANNELS = new HashSet<>(
            Arrays.asList("app", "web", "mini_program"));

    private OrderEventValidator() {
    }

    public static boolean isValid(OrderEvent event) {
        return event != null
                && isNotBlank(event.getEventId())
                && isNotBlank(event.getOrderId())
                && event.getEventTime() > 0
                && event.getIngestTime() >= event.getEventTime()
                && REGIONS.contains(event.getRegion())
                && CHANNELS.contains(event.getChannel())
                && event.getTotalAmount() != null
                && event.getTotalAmount().compareTo(BigDecimal.ZERO) > 0;
    }

    private static boolean isNotBlank(String value) {
        return value != null && !value.trim().isEmpty();
    }
}

