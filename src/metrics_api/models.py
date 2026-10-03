from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class UtcModel(BaseModel):
    @field_validator("*", mode="after")
    @classmethod
    def attach_utc_to_naive_datetimes(cls, value: object) -> object:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class HealthResponse(UtcModel):
    status: Literal["ok"]
    data_source: Literal["clickhouse", "preview"]
    analytics_store: Literal["reachable", "in_memory"]


class ErrorDetail(UtcModel):
    code: str
    message: str


class ErrorResponse(UtcModel):
    detail: ErrorDetail


class MetricFilters(UtcModel):
    start: datetime
    end: datetime
    region: str | None = None
    channel: str | None = None


class MinuteMetric(UtcModel):
    window_start: datetime
    window_end: datetime
    region: str
    channel: str
    order_count: int = Field(ge=0)
    gmv: str
    average_order_value: str
    version: int = Field(ge=0)
    processed_at: datetime


class MinuteMetricsResponse(UtcModel):
    generated_at: datetime
    filters: MetricFilters
    count: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)
    items: list[MinuteMetric]


class MetricSummaryResponse(UtcModel):
    generated_at: datetime
    filters: MetricFilters
    has_data: bool
    order_count: int = Field(ge=0)
    gmv: str
    average_order_value: str
    latest_processed_at: datetime | None = None


TimeBucket = Literal["auto", "1m", "5m", "15m", "1h"]
ResolvedTimeBucket = Literal["1m", "5m", "15m", "1h"]
BreakdownDimension = Literal["region", "channel"]


class TimeSeriesPoint(UtcModel):
    bucket_start: datetime
    order_count: int = Field(ge=0)
    gmv: str
    average_order_value: str


class TimeSeriesResponse(UtcModel):
    generated_at: datetime
    filters: MetricFilters
    bucket: ResolvedTimeBucket
    count: int = Field(ge=0)
    items: list[TimeSeriesPoint]


class BreakdownItem(UtcModel):
    name: str
    order_count: int = Field(ge=0)
    gmv: str
    average_order_value: str


class BreakdownResponse(UtcModel):
    generated_at: datetime
    filters: MetricFilters
    dimension: BreakdownDimension
    count: int = Field(ge=0)
    items: list[BreakdownItem]

