package com.zhangliyang.ecommerce.model;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.Objects;

public class OrderEvent implements Serializable {
    private static final long serialVersionUID = 1L;

    private String eventId;
    private String orderId;
    private long eventTime;
    private long ingestTime;
    private String region;
    private String channel;
    private BigDecimal totalAmount;
    private OrderItem[] items = new OrderItem[0];

    public OrderEvent() {
    }

    public OrderEvent(
            String eventId,
            String orderId,
            long eventTime,
            long ingestTime,
            String region,
            String channel,
            BigDecimal totalAmount) {
        this(eventId, orderId, eventTime, ingestTime, region, channel, totalAmount, new OrderItem[0]);
    }

    public OrderEvent(
            String eventId,
            String orderId,
            long eventTime,
            long ingestTime,
            String region,
            String channel,
            BigDecimal totalAmount,
            OrderItem[] items) {
        this.eventId = eventId;
        this.orderId = orderId;
        this.eventTime = eventTime;
        this.ingestTime = ingestTime;
        this.region = region;
        this.channel = channel;
        this.totalAmount = totalAmount;
        this.items = items == null ? new OrderItem[0] : Arrays.copyOf(items, items.length);
    }

    public String getEventId() {
        return eventId;
    }

    public void setEventId(String eventId) {
        this.eventId = eventId;
    }

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }

    public long getEventTime() {
        return eventTime;
    }

    public void setEventTime(long eventTime) {
        this.eventTime = eventTime;
    }

    public long getIngestTime() {
        return ingestTime;
    }

    public void setIngestTime(long ingestTime) {
        this.ingestTime = ingestTime;
    }

    public String getRegion() {
        return region;
    }

    public void setRegion(String region) {
        this.region = region;
    }

    public String getChannel() {
        return channel;
    }

    public void setChannel(String channel) {
        this.channel = channel;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public void setTotalAmount(BigDecimal totalAmount) {
        this.totalAmount = totalAmount;
    }

    public OrderItem[] getItems() { return Arrays.copyOf(items, items.length); }
    public void setItems(OrderItem[] items) {
        this.items = items == null ? new OrderItem[0] : Arrays.copyOf(items, items.length);
    }

    @Override
    public boolean equals(Object value) {
        if (this == value) {
            return true;
        }
        if (!(value instanceof OrderEvent)) {
            return false;
        }
        OrderEvent that = (OrderEvent) value;
        return eventTime == that.eventTime
                && ingestTime == that.ingestTime
                && Objects.equals(eventId, that.eventId)
                && Objects.equals(orderId, that.orderId)
                && Objects.equals(region, that.region)
                && Objects.equals(channel, that.channel)
                && Objects.equals(totalAmount, that.totalAmount)
                && Arrays.equals(items, that.items);
    }

    @Override
    public int hashCode() {
        int result = Objects.hash(eventId, orderId, eventTime, ingestTime, region, channel, totalAmount);
        return 31 * result + Arrays.hashCode(items);
    }

    @Override
    public String toString() {
        return "OrderEvent{" +
                "eventId='" + eventId + '\'' +
                ", orderId='" + orderId + '\'' +
                ", eventTime=" + eventTime +
                ", ingestTime=" + ingestTime +
                ", region='" + region + '\'' +
                ", channel='" + channel + '\'' +
                ", totalAmount=" + totalAmount +
                '}';
    }
}

