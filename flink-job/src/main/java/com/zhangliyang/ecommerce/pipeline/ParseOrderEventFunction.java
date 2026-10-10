package com.zhangliyang.ecommerce.pipeline;

import com.zhangliyang.ecommerce.json.OrderEventJsonParser;
import com.zhangliyang.ecommerce.json.OrderEventParseResult;
import com.zhangliyang.ecommerce.model.OrderEvent;
import com.zhangliyang.ecommerce.model.RejectedEvent;
import org.apache.flink.api.common.functions.OpenContext;
import org.apache.flink.streaming.api.functions.ProcessFunction;
import org.apache.flink.util.Collector;
import org.apache.flink.util.OutputTag;

public class ParseOrderEventFunction extends ProcessFunction<String, OrderEvent> {
    private static final long serialVersionUID = 1L;

    public static final OutputTag<RejectedEvent> REJECTED_EVENTS =
            new OutputTag<RejectedEvent>("rejected-order-events") {
                private static final long serialVersionUID = 1L;
            };

    private transient OrderEventJsonParser parser;

    @Override
    public void open(OpenContext openContext) {
        parser = new OrderEventJsonParser();
    }

    @Override
    public void processElement(
            String rawPayload,
            Context context,
            Collector<OrderEvent> output) {
        OrderEventParseResult result = parser.parse(rawPayload);
        if (result.isAccepted()) {
            output.collect(result.getEvent());
        } else {
            context.output(REJECTED_EVENTS, result.getRejection());
        }
    }
}

