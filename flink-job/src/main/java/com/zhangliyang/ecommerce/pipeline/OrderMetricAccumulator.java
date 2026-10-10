package com.zhangliyang.ecommerce.pipeline;

import java.io.Serializable;
import java.math.BigDecimal;

public class OrderMetricAccumulator implements Serializable {
    private static final long serialVersionUID = 1L;

    private long orderCount;
    private BigDecimal gmv = BigDecimal.ZERO;

    public OrderMetricAccumulator() {
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

    public void add(BigDecimal amount) {
        orderCount += 1;
        gmv = gmv.add(amount);
    }

    public void merge(OrderMetricAccumulator other) {
        orderCount += other.orderCount;
        gmv = gmv.add(other.gmv);
    }
}

