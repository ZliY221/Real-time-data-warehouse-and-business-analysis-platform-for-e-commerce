CREATE DATABASE IF NOT EXISTS ecommerce;

CREATE TABLE IF NOT EXISTS ecommerce.minute_metrics
(
    window_start DateTime64(3, 'UTC'),
    window_end DateTime64(3, 'UTC'),
    region LowCardinality(String),
    channel LowCardinality(String),
    order_count UInt64,
    gmv Decimal(18, 2),
    version UInt64,
    processed_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(version)
PARTITION BY toYYYYMM(window_start)
ORDER BY (window_start, region, channel);

CREATE VIEW IF NOT EXISTS ecommerce.minute_metrics_latest AS
SELECT
    window_start,
    window_end,
    region,
    channel,
    order_count,
    gmv,
    round(gmv / order_count, 2) AS average_order_value,
    version,
    processed_at
FROM ecommerce.minute_metrics FINAL;

CREATE TABLE IF NOT EXISTS ecommerce.rejected_order_events
(
    rejection_id FixedString(64),
    error_type LowCardinality(String),
    payload_size_bytes UInt32,
    detected_at DateTime64(3, 'UTC'),
    version UInt64
)
ENGINE = ReplacingMergeTree(version)
ORDER BY rejection_id;

CREATE TABLE IF NOT EXISTS ecommerce.late_order_events
(
    event_id String,
    order_id String,
    event_time DateTime64(3, 'UTC'),
    ingest_time DateTime64(3, 'UTC'),
    region LowCardinality(String),
    channel LowCardinality(String),
    total_amount Decimal(18, 2),
    detected_at DateTime64(3, 'UTC'),
    version UInt64
)
ENGINE = ReplacingMergeTree(version)
ORDER BY event_id;

CREATE VIEW IF NOT EXISTS ecommerce.event_anomaly_summary AS
SELECT
    toStartOfMinute(detected_at) AS minute_start,
    'rejected' AS anomaly_type,
    error_type AS reason,
    count() AS anomaly_count
FROM ecommerce.rejected_order_events FINAL
GROUP BY minute_start, anomaly_type, reason
UNION ALL
SELECT
    toStartOfMinute(detected_at) AS minute_start,
    'late' AS anomaly_type,
    'window_late' AS reason,
    count() AS anomaly_count
FROM ecommerce.late_order_events FINAL
GROUP BY minute_start, anomaly_type, reason;
