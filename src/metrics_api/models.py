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


class MetricComparisonDelta(UtcModel):
    order_count: int
    gmv: str
    average_order_value: str
    order_count_rate: float | None = None
    gmv_rate: float | None = None
    average_order_value_rate: float | None = None


class MetricComparisonResponse(UtcModel):
    generated_at: datetime
    current: MetricSummaryResponse
    baseline: MetricSummaryResponse
    delta: MetricComparisonDelta


TimeBucket = Literal["auto", "1m", "5m", "15m", "1h"]
ResolvedTimeBucket = Literal["1m", "5m", "15m", "1h"]
BreakdownDimension = Literal["region", "channel"]
AnomalyType = Literal["rejected", "late"]


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


class AnomalyFilters(UtcModel):
    start: datetime
    end: datetime
    anomaly_type: AnomalyType | None = None


class AnomalySummaryItem(UtcModel):
    anomaly_type: AnomalyType
    reason: str
    anomaly_count: int = Field(ge=0)
    latest_at: datetime


class AnomalySummaryResponse(UtcModel):
    generated_at: datetime
    filters: AnomalyFilters
    total_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    late_count: int = Field(ge=0)
    count: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    items: list[AnomalySummaryItem]


class QualityRunItem(UtcModel):
    run_id: str
    generated_at: datetime
    input_file: str
    passed: bool
    total_records: int = Field(ge=0)
    parsed_records: int = Field(ge=0)
    invalid_json_records: int = Field(ge=0)
    invalid_contract_records: int = Field(ge=0)
    duplicate_records: int = Field(ge=0)
    late_records: int = Field(ge=0)
    passed_rules: int = Field(ge=0)
    failed_rules: int = Field(ge=0)


class QualityRunsResponse(UtcModel):
    generated_at: datetime
    count: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)
    passed: bool | None = None
    items: list[QualityRunItem]


class QualityTrendPoint(UtcModel):
    run_id: str
    generated_at: datetime
    passed: bool
    checked_records: int = Field(ge=0)
    violations: int = Field(ge=0)
    metric_name: str
    observed_value: float
    threshold: float


class QualityTrendResponse(UtcModel):
    generated_at: datetime
    rule_id: str
    count: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)
    items: list[QualityTrendPoint]


class AssetFreshnessResponse(UtcModel):
    generated_at: datetime
    asset_id: str
    asset_name: str
    asset_kind: str
    owner: str
    status: Literal["fresh", "stale", "no_data"]
    freshness_slo_seconds: int = Field(gt=0)
    observed_at: datetime | None = None
    lag_seconds: int | None = Field(default=None, ge=0)
    impacted_assets: list[str]


class AssetCatalogItem(UtcModel):
    asset_id: str
    asset_name: str
    asset_kind: str
    owner: str
    upstream_assets: list[str]
    downstream_assets: list[str]
    freshness_slo_seconds: int | None = Field(default=None, gt=0)


class AssetCatalogResponse(UtcModel):
    generated_at: datetime
    asset_count: int = Field(ge=0)
    source_count: int = Field(ge=0)
    monitored_count: int = Field(ge=0)
    items: list[AssetCatalogItem]

