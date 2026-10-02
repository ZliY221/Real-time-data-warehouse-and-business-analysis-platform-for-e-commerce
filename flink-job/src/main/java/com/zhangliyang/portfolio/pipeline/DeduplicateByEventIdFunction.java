package com.zhangliyang.portfolio.pipeline;

import com.zhangliyang.portfolio.model.OrderEvent;
import org.apache.flink.api.common.functions.OpenContext;
import org.apache.flink.api.common.state.StateTtlConfig;
import org.apache.flink.api.common.state.ValueState;
import org.apache.flink.api.common.state.ValueStateDescriptor;
import org.apache.flink.api.common.typeinfo.Types;
import org.apache.flink.configuration.Configuration;
import org.apache.flink.streaming.api.functions.KeyedProcessFunction;
import org.apache.flink.util.Collector;

import java.time.Duration;

public class DeduplicateByEventIdFunction
        extends KeyedProcessFunction<String, OrderEvent, OrderEvent> {
    private static final long serialVersionUID = 1L;

    private final Duration stateTtl;
    private transient ValueState<Boolean> seen;

    public DeduplicateByEventIdFunction(Duration stateTtl) {
        if (stateTtl == null || stateTtl.isZero() || stateTtl.isNegative()) {
            throw new IllegalArgumentException("stateTtl must be positive");
        }
        this.stateTtl = stateTtl;
    }

    @Override
    public void open(OpenContext openContext) throws Exception {
        configureState();
    }

    @Deprecated
    @Override
    public void open(Configuration parameters) throws Exception {
        configureState();
    }

    private void configureState() throws Exception {
        ValueStateDescriptor<Boolean> descriptor =
                new ValueStateDescriptor<>("seen-event", Types.BOOLEAN);
        StateTtlConfig ttlConfig = StateTtlConfig
                .newBuilder(stateTtl)
                .setUpdateType(StateTtlConfig.UpdateType.OnCreateAndWrite)
                .setStateVisibility(StateTtlConfig.StateVisibility.NeverReturnExpired)
                .build();
        descriptor.enableTimeToLive(ttlConfig);
        seen = getRuntimeContext().getState(descriptor);
    }

    @Override
    public void processElement(
            OrderEvent event,
            Context context,
            Collector<OrderEvent> output) throws Exception {
        if (seen.value() == null) {
            seen.update(Boolean.TRUE);
            output.collect(event);
        }
    }
}

