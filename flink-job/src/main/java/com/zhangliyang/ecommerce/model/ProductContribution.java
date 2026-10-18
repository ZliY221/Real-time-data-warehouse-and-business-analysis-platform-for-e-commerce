package com.zhangliyang.ecommerce.model;

import java.io.Serializable;
import java.math.BigDecimal;

public class ProductContribution implements Serializable {
    private static final long serialVersionUID = 1L;
    private long eventTime;
    private String category;
    private String skuId;
    private long quantity;
    private BigDecimal lineAmount;

    public ProductContribution() { }

    public ProductContribution(long eventTime, String category, String skuId, long quantity, BigDecimal lineAmount) {
        this.eventTime = eventTime;
        this.category = category;
        this.skuId = skuId;
        this.quantity = quantity;
        this.lineAmount = lineAmount;
    }

    public long getEventTime() { return eventTime; }
    public void setEventTime(long eventTime) { this.eventTime = eventTime; }
    public String getCategory() { return category; }
    public void setCategory(String category) { this.category = category; }
    public String getSkuId() { return skuId; }
    public void setSkuId(String skuId) { this.skuId = skuId; }
    public long getQuantity() { return quantity; }
    public void setQuantity(long quantity) { this.quantity = quantity; }
    public BigDecimal getLineAmount() { return lineAmount; }
    public void setLineAmount(BigDecimal lineAmount) { this.lineAmount = lineAmount; }
}
