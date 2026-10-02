package com.zhangliyang.portfolio.model;

import java.io.Serializable;
import java.math.BigDecimal;
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
        this.eventId = eventId;
        this.orderId = orderId;
        this.eventTime = eventTime;
        this.ingestTime = ingestTime;
        this.region = region;
        this.channel = channel;
        this.totalAmount = totalAmount;
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
                && Objects.equals(totalAmount, that.totalAmount);
    }

    @Override
    public int hashCode() {
        return Objects.hash(eventId, orderId, eventTime, ingestTime, region, channel, totalAmount);
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

