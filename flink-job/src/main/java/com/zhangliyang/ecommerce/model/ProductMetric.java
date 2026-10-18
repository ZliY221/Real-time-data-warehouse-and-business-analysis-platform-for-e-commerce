package com.zhangliyang.ecommerce.model;

import java.io.Serializable;
import java.math.BigDecimal;

public class ProductMetric implements Serializable {
    private static final long serialVersionUID = 1L;
    private long windowStart;
    private long windowEnd;
    private String category;
    private String skuId;
    private long orderCount;
    private long unitQuantity;
    private BigDecimal gmv;

    public ProductMetric() { }

    public ProductMetric(long windowStart, long windowEnd, String category, String skuId,
                         long orderCount, long unitQuantity, BigDecimal gmv) {
        this.windowStart = windowStart;
        this.windowEnd = windowEnd;
        this.category = category;
        this.skuId = skuId;
        this.orderCount = orderCount;
        this.unitQuantity = unitQuantity;
        this.gmv = gmv;
    }

    public long getWindowStart() { return windowStart; }
    public void setWindowStart(long windowStart) { this.windowStart = windowStart; }
    public long getWindowEnd() { return windowEnd; }
    public void setWindowEnd(long windowEnd) { this.windowEnd = windowEnd; }
    public String getCategory() { return category; }
    public void setCategory(String category) { this.category = category; }
    public String getSkuId() { return skuId; }
    public void setSkuId(String skuId) { this.skuId = skuId; }
    public long getOrderCount() { return orderCount; }
    public void setOrderCount(long orderCount) { this.orderCount = orderCount; }
    public long getUnitQuantity() { return unitQuantity; }
    public void setUnitQuantity(long unitQuantity) { this.unitQuantity = unitQuantity; }
    public BigDecimal getGmv() { return gmv; }
    public void setGmv(BigDecimal gmv) { this.gmv = gmv; }
}
