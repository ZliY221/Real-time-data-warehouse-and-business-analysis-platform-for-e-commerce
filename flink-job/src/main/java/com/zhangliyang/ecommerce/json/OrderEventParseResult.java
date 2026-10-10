package com.zhangliyang.ecommerce.json;

import com.zhangliyang.ecommerce.model.OrderEvent;
import com.zhangliyang.ecommerce.model.RejectedEvent;

public final class OrderEventParseResult {
    private final OrderEvent event;
    private final RejectedEvent rejection;

    private OrderEventParseResult(OrderEvent event, RejectedEvent rejection) {
        this.event = event;
        this.rejection = rejection;
    }

    public static OrderEventParseResult accepted(OrderEvent event) {
        return new OrderEventParseResult(event, null);
    }

    public static OrderEventParseResult rejected(RejectedEvent rejection) {
        return new OrderEventParseResult(null, rejection);
    }

    public boolean isAccepted() {
        return event != null;
    }

    public OrderEvent getEvent() {
        return event;
    }

    public RejectedEvent getRejection() {
        return rejection;
    }
}

