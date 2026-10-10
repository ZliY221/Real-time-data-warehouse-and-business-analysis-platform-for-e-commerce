package com.zhangliyang.ecommerce.pipeline;

import com.zhangliyang.ecommerce.model.OrderEvent;
import org.apache.flink.api.java.functions.KeySelector;
import org.apache.flink.api.java.tuple.Tuple2;

public class RegionChannelKeySelector
        implements KeySelector<OrderEvent, Tuple2<String, String>> {
    private static final long serialVersionUID = 1L;

    @Override
    public Tuple2<String, String> getKey(OrderEvent event) {
        return Tuple2.of(event.getRegion(), event.getChannel());
    }
}

