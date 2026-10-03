"""DuckDB schemas for the local ODS, DIM, DWD, DWS, and ADS layers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


DDL: tuple[str, ...] = (
    "CREATE SCHEMA IF NOT EXISTS meta",
    "CREATE SCHEMA IF NOT EXISTS ods",
    "CREATE SCHEMA IF NOT EXISTS dim",
    "CREATE SCHEMA IF NOT EXISTS dwd",
    "CREATE SCHEMA IF NOT EXISTS dws",
    "CREATE SCHEMA IF NOT EXISTS ads",
    """
    CREATE TABLE IF NOT EXISTS meta.etl_runs (
        run_id VARCHAR PRIMARY KEY,
        input_sha256 VARCHAR NOT NULL,
        input_name VARCHAR NOT NULL,
        source_records INTEGER NOT NULL,
        loaded_events INTEGER NOT NULL,
        loaded_items INTEGER NOT NULL,
        rejected_records INTEGER NOT NULL,
        duplicate_records INTEGER NOT NULL,
        started_at TIMESTAMPTZ NOT NULL,
        completed_at TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meta.rejected_records (
        run_id VARCHAR NOT NULL,
        line_number INTEGER NOT NULL,
        error_type VARCHAR NOT NULL,
        error_summary VARCHAR NOT NULL,
        payload_sha256 VARCHAR NOT NULL,
        payload_bytes INTEGER NOT NULL,
        PRIMARY KEY (run_id, line_number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ods.order_events (
        event_id VARCHAR PRIMARY KEY,
        event_hash VARCHAR NOT NULL,
        order_id VARCHAR NOT NULL UNIQUE,
        user_id VARCHAR NOT NULL,
        event_time TIMESTAMPTZ NOT NULL,
        ingest_time TIMESTAMPTZ NOT NULL,
        region VARCHAR NOT NULL,
        channel VARCHAR NOT NULL,
        currency VARCHAR NOT NULL,
        total_amount DECIMAL(18, 2) NOT NULL,
        load_run_id VARCHAR NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim.dim_date (
        date_key INTEGER PRIMARY KEY,
        calendar_date DATE NOT NULL UNIQUE,
        year_number SMALLINT NOT NULL,
        month_number TINYINT NOT NULL,
        day_number TINYINT NOT NULL,
        iso_weekday TINYINT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim.dim_region (
        region_key SMALLINT PRIMARY KEY,
        region_name VARCHAR NOT NULL UNIQUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim.dim_channel (
        channel_key SMALLINT PRIMARY KEY,
        channel_name VARCHAR NOT NULL UNIQUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim.dim_product (
        product_key INTEGER PRIMARY KEY,
        sku_id VARCHAR NOT NULL UNIQUE,
        category VARCHAR NOT NULL,
        list_unit_price DECIMAL(18, 2) NOT NULL,
        first_seen_at TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dwd.fact_order_items (
        event_id VARCHAR NOT NULL,
        item_position SMALLINT NOT NULL,
        order_id VARCHAR NOT NULL,
        date_key INTEGER NOT NULL,
        event_time TIMESTAMPTZ NOT NULL,
        ingest_time TIMESTAMPTZ NOT NULL,
        user_id VARCHAR NOT NULL,
        region_key SMALLINT NOT NULL,
        channel_key SMALLINT NOT NULL,
        product_key INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price DECIMAL(18, 2) NOT NULL,
        line_amount DECIMAL(18, 2) NOT NULL,
        load_run_id VARCHAR NOT NULL,
        PRIMARY KEY (event_id, item_position)
    )
    """,
    """
    CREATE OR REPLACE VIEW dws.daily_sales_by_region_channel AS
    SELECT
        CAST(event_time AT TIME ZONE 'UTC' AS DATE) AS calendar_date,
        region,
        channel,
        COUNT(*) AS order_count,
        COUNT(DISTINCT user_id) AS customer_count,
        SUM(total_amount) AS gmv,
        CAST(AVG(total_amount) AS DECIMAL(18, 2)) AS average_order_value
    FROM ods.order_events
    GROUP BY 1, 2, 3
    """,
    """
    CREATE OR REPLACE VIEW dws.daily_category_sales AS
    SELECT
        dd.calendar_date,
        dp.category,
        SUM(fi.quantity) AS units_sold,
        SUM(fi.line_amount) AS sales_amount
    FROM dwd.fact_order_items AS fi
    JOIN dim.dim_date AS dd USING (date_key)
    JOIN dim.dim_product AS dp USING (product_key)
    GROUP BY 1, 2
    """,
    """
    CREATE OR REPLACE VIEW ads.daily_category_sales_rank AS
    SELECT
        calendar_date,
        category,
        units_sold,
        sales_amount,
        DENSE_RANK() OVER (
            PARTITION BY calendar_date
            ORDER BY sales_amount DESC, category ASC
        ) AS sales_rank
    FROM dws.daily_category_sales
    """,
)


REGIONS = ("辽宁", "北京", "上海", "广东", "四川")
CHANNELS = ("app", "web", "mini_program")


def ensure_schema(connection: Any) -> None:
    """Create every warehouse layer and seed stable small dimensions."""

    for statement in DDL:
        connection.execute(statement)
    connection.executemany(
        "INSERT OR IGNORE INTO dim.dim_region VALUES (?, ?)",
        [(index, name) for index, name in enumerate(REGIONS, start=1)],
    )
    connection.executemany(
        "INSERT OR IGNORE INTO dim.dim_channel VALUES (?, ?)",
        [(index, name) for index, name in enumerate(CHANNELS, start=1)],
    )


def fetch_one_value(connection: Any, query: str, parameters: Iterable[object] = ()) -> Any:
    """Return the first column of one required result row."""

    row = connection.execute(query, list(parameters)).fetchone()
    if row is None:
        raise RuntimeError("expected a query result row")
    return row[0]
