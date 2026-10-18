package com.zhangliyang.ecommerce.pipeline;

import com.zhangliyang.ecommerce.model.OrderEvent;
import com.zhangliyang.ecommerce.model.OrderItem;
import com.zhangliyang.ecommerce.model.ProductContribution;
import org.apache.flink.api.common.functions.FlatMapFunction;
import org.apache.flink.util.Collector;

public class ExpandOrderItemsFunction implements FlatMapFunction<OrderEvent, ProductContribution> {
    @Override
    public void flatMap(OrderEvent event, Collector<ProductContribution> output) {
        for (OrderItem item : event.getItems()) {
            output.collect(new ProductContribution(event.getEventTime(), item.getCategory(),
                    item.getSkuId(), item.getQuantity(), item.getLineAmount()));
        }
    }
}
