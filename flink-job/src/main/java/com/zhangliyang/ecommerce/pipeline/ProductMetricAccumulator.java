package com.zhangliyang.ecommerce.pipeline;

import java.io.Serializable;
import java.math.BigDecimal;

public class ProductMetricAccumulator implements Serializable {
    private static final long serialVersionUID = 1L;
    private long orderCount;
    private long unitQuantity;
    private BigDecimal gmv = BigDecimal.ZERO;

    public void add(long quantity, BigDecimal amount) {
        orderCount += 1;
        unitQuantity += quantity;
        gmv = gmv.add(amount);
    }

    public void merge(ProductMetricAccumulator other) {
        orderCount += other.orderCount;
        unitQuantity += other.unitQuantity;
        gmv = gmv.add(other.gmv);
    }

    public long getOrderCount() { return orderCount; }
    public long getUnitQuantity() { return unitQuantity; }
    public BigDecimal getGmv() { return gmv; }
}
