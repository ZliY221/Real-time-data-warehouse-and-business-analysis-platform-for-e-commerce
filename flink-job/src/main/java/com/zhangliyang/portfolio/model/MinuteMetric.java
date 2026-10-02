package com.zhangliyang.portfolio.model;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.Objects;

public class MinuteMetric implements Serializable {
    private static final long serialVersionUID = 1L;

    private long windowStart;
    private long windowEnd;
    private String region;
    private String channel;
    private long orderCount;
    private BigDecimal gmv;

    public MinuteMetric() {
    }

    public MinuteMetric(
            long windowStart,
            long windowEnd,
            String region,
            String channel,
            long orderCount,
            BigDecimal gmv) {
        this.windowStart = windowStart;
        this.windowEnd = windowEnd;
        this.region = region;
        this.channel = channel;
        this.orderCount = orderCount;
        this.gmv = gmv;
    }

    public long getWindowStart() {
        return windowStart;
    }

    public void setWindowStart(long windowStart) {
        this.windowStart = windowStart;
    }

    public long getWindowEnd() {
        return windowEnd;
    }

    public void setWindowEnd(long windowEnd) {
        this.windowEnd = windowEnd;
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

    public long getOrderCount() {
        return orderCount;
    }

    public void setOrderCount(long orderCount) {
        this.orderCount = orderCount;
    }

    public BigDecimal getGmv() {
        return gmv;
    }

    public void setGmv(BigDecimal gmv) {
        this.gmv = gmv;
    }

    @Override
    public boolean equals(Object value) {
        if (this == value) {
            return true;
        }
        if (!(value instanceof MinuteMetric)) {
            return false;
        }
        MinuteMetric that = (MinuteMetric) value;
        return windowStart == that.windowStart
                && windowEnd == that.windowEnd
                && orderCount == that.orderCount
                && Objects.equals(region, that.region)
                && Objects.equals(channel, that.channel)
                && Objects.equals(gmv, that.gmv);
    }

    @Override
    public int hashCode() {
        return Objects.hash(windowStart, windowEnd, region, channel, orderCount, gmv);
    }

    @Override
    public String toString() {
        return "MinuteMetric{" +
                "windowStart=" + windowStart +
                ", windowEnd=" + windowEnd +
                ", region='" + region + '\'' +
                ", channel='" + channel + '\'' +
                ", orderCount=" + orderCount +
                ", gmv=" + gmv +
                '}';
    }
}

