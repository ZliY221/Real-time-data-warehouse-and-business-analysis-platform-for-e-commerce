package com.zhangliyang.ecommerce.pipeline;

import com.zhangliyang.ecommerce.model.ProductContribution;
import org.apache.flink.api.java.functions.KeySelector;
import org.apache.flink.api.java.tuple.Tuple2;

public class ProductMetricKeySelector implements KeySelector<ProductContribution, Tuple2<String, String>> {
    @Override
    public Tuple2<String, String> getKey(ProductContribution value) {
        return Tuple2.of(value.getCategory(), value.getSkuId());
    }
}
