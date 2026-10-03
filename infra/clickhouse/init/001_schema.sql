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
