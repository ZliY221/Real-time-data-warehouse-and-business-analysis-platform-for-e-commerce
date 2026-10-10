package com.zhangliyang.ecommerce.model;

import java.io.Serializable;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

public class RejectedEvent implements Serializable {
    private static final long serialVersionUID = 1L;

    private String rawPayload;
    private String errorType;
    private String reason;

    public RejectedEvent() {
    }

    public RejectedEvent(String rawPayload, String errorType, String reason) {
        this.rawPayload = rawPayload;
        this.errorType = errorType;
        this.reason = reason;
    }

    public String getRawPayload() {
        return rawPayload;
    }

    public void setRawPayload(String rawPayload) {
        this.rawPayload = rawPayload;
    }

    public String getErrorType() {
        return errorType;
    }

    public void setErrorType(String errorType) {
        this.errorType = errorType;
    }

    public String getReason() {
        return reason;
    }

    public void setReason(String reason) {
        this.reason = reason;
    }

    public int getPayloadSizeBytes() {
        return rawPayload == null ? 0 : rawPayload.getBytes(StandardCharsets.UTF_8).length;
    }

    @Override
    public boolean equals(Object value) {
        if (this == value) {
            return true;
        }
        if (!(value instanceof RejectedEvent)) {
            return false;
        }
        RejectedEvent that = (RejectedEvent) value;
        return Objects.equals(rawPayload, that.rawPayload)
                && Objects.equals(errorType, that.errorType)
                && Objects.equals(reason, that.reason);
    }

    @Override
    public int hashCode() {
        return Objects.hash(rawPayload, errorType, reason);
    }

    @Override
    public String toString() {
        return "RejectedEvent{" +
                "errorType='" + errorType + '\'' +
                ", payloadSizeBytes=" + getPayloadSizeBytes() +
                '}';
    }
}

