from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"]
    clickhouse: Literal["reachable"]


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorDetail


class MetricFilters(BaseModel):
    start: datetime
    end: datetime
    region: str | None = None
    channel: str | None = None


class MinuteMetric(BaseModel):
    window_start: datetime
    window_end: datetime
    region: str
    channel: str
    order_count: int = Field(ge=0)
    gmv: str
    average_order_value: str
    version: int = Field(ge=0)
    processed_at: datetime


class MinuteMetricsResponse(BaseModel):
    generated_at: datetime
    filters: MetricFilters
    count: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)
    items: list[MinuteMetric]


class MetricSummaryResponse(BaseModel):
    generated_at: datetime
    filters: MetricFilters
    has_data: bool
    order_count: int = Field(ge=0)
    gmv: str
    average_order_value: str
    latest_processed_at: datetime | None = None

