from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import sqlite3
import tomllib
from threading import Lock
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from data_quality.history import QualityHistoryReader, QualityHistoryStore
from metrics_api.config import ApiSettings
from metrics_api.data_catalog import DataAssetCatalog, DataCatalogError
from metrics_api.models import (
    AnomalyFilters,
    AnomalySummaryItem,
    AnomalySummaryResponse,
    AnomalyType,
    AssetCatalogItem,
    AssetCatalogResponse,
    AssetFreshnessResponse,
    BreakdownDimension,
    BreakdownItem,
    BreakdownResponse,
    ErrorResponse,
    HealthResponse,
    MetricFilters,
    MetricComparisonDelta,
    MetricComparisonResponse,
    MetricSummaryResponse,
    MinuteMetric,
    MinuteMetricsResponse,
    ProductBreakdownItem,
    ProductBreakdownResponse,
    ProductDimension,
    QualityRunItem,
    QualityRunsResponse,
    QualityTrendPoint,
    QualityTrendResponse,
    ResolvedTimeBucket,
    TimeBucket,
    TimeSeriesPoint,
    TimeSeriesResponse,
)
from metrics_api.repository import (
    ClickHouseHttpRepository,
    MetricsRepository,
    MetricsRepositoryError,
)
from metrics_api.product_operations import alert_acknowledgement, campaign_guardrail, campaign_pacing, command_center, compare_product_windows, conversion_funnel, inventory_signal, operating_briefing, product_alerts, product_contribution, promotion_margin_guardrail, resource_plan, shift_handoff

MAX_RANGE = timedelta(days=31)
DEFAULT_RANGE = timedelta(hours=24)
MAX_TIME_SERIES_POINTS = 1500
BUCKET_SECONDS: dict[ResolvedTimeBucket, int] = {
    "1m": 60,
    "5m": 5 * 60,
    "15m": 15 * 60,
    "1h": 60 * 60,
}
DASHBOARD_DIRECTORY = Path(__file__).resolve().parents[2] / "dashboard" / "static"
DEFAULT_ASSET_CATALOG = Path(__file__).resolve().parents[2] / "config" / "data-assets.json"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_VERSION = str(tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"])
DASHBOARD_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self'; "
        "connect-src 'self'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _resolve_range(
    start: datetime | None,
    end: datetime | None,
    *,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    resolved_end = _utc(end) if end is not None else _utc(now or datetime.now(UTC))
    resolved_start = _utc(start) if start is not None else resolved_end - DEFAULT_RANGE
    if resolved_start >= resolved_end:
        raise ValueError("start must be earlier than end")
    if resolved_end - resolved_start > MAX_RANGE:
        raise ValueError("the query range must not exceed 31 days")
    return resolved_start, resolved_end


def _resolve_bucket(
    start: datetime,
    end: datetime,
    bucket: TimeBucket,
) -> ResolvedTimeBucket:
    duration = end - start
    if bucket == "auto":
        if duration <= timedelta(hours=6):
            return "1m"
        if duration <= timedelta(days=1):
            return "5m"
        if duration <= timedelta(days=7):
            return "15m"
        return "1h"

    estimated_points = duration.total_seconds() / BUCKET_SECONDS[bucket]
    if estimated_points > MAX_TIME_SERIES_POINTS:
        raise ValueError(
            f"bucket {bucket} would return too many points; use a coarser bucket"
        )
    return bucket


def get_repository(request: Request) -> MetricsRepository:
    return request.app.state.repository


def get_quality_history(request: Request) -> QualityHistoryReader:
    history = request.app.state.quality_history
    if history is None:
        with request.app.state.quality_history_lock:
            history = request.app.state.quality_history
            if history is None:
                history = QualityHistoryStore(request.app.state.quality_history_path)
                request.app.state.quality_history = history
    return history


def create_app(
    repository: MetricsRepository | None = None,
    *,
    settings: ApiSettings | None = None,
    data_mode: Literal["clickhouse", "preview"] = "clickhouse",
    quality_history: QualityHistoryReader | None = None,
    quality_history_path: Path = Path("build/data-quality/history.db"),
    asset_catalog: DataAssetCatalog | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Ecommerce Realtime Metrics API",
        version=PROJECT_VERSION,
        description="Read-only API for verified minute metrics stored in ClickHouse.",
    )
    app.state.repository = repository or ClickHouseHttpRepository(
        settings or ApiSettings.from_env()
    )
    app.state.data_mode = data_mode
    app.state.quality_history = quality_history
    app.state.quality_history_path = quality_history_path
    app.state.quality_history_lock = Lock()
    app.state.asset_catalog = asset_catalog or DataAssetCatalog.from_file(
        DEFAULT_ASSET_CATALOG
    )
    app.mount(
        "/dashboard/assets",
        StaticFiles(directory=DASHBOARD_DIRECTORY),
        name="dashboard-assets",
    )

    @app.get("/", include_in_schema=False)
    @app.get("/dashboard", include_in_schema=False)
    def dashboard() -> FileResponse:
        return FileResponse(
            DASHBOARD_DIRECTORY / "index.html",
            headers=DASHBOARD_SECURITY_HEADERS,
        )

    @app.exception_handler(MetricsRepositoryError)
    async def repository_error_handler(
        request: Request,
        error: MetricsRepositoryError,
    ) -> JSONResponse:
        del request, error
        return JSONResponse(
            status_code=503,
            content={
                "detail": {
                    "code": "analytics_store_unavailable",
                    "message": "The analytics store is temporarily unavailable.",
                }
            },
        )

    @app.middleware("http")
    async def add_data_mode_header(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/") or request.url.path == "/health":
            response.headers["X-Data-Mode"] = app.state.data_mode
        return response

    @app.get(
        "/health",
        response_model=HealthResponse,
        responses={503: {"model": ErrorResponse}},
        tags=["operations"],
    )
    def health(
        metrics_repository: Annotated[MetricsRepository, Depends(get_repository)],
    ) -> HealthResponse:
        metrics_repository.ping()
        if app.state.data_mode == "preview":
            return HealthResponse(
                status="ok",
                data_source="preview",
                analytics_store="in_memory",
            )
        return HealthResponse(
            status="ok",
            data_source="clickhouse",
            analytics_store="reachable",
        )

    @app.get(
        "/api/v1/metrics/minutes",
        response_model=MinuteMetricsResponse,
        responses={503: {"model": ErrorResponse}},
        tags=["metrics"],
    )
    def minute_metrics(
        metrics_repository: Annotated[MetricsRepository, Depends(get_repository)],
        start: Annotated[datetime | None, Query(description="Inclusive UTC start time")] = None,
        end: Annotated[datetime | None, Query(description="Exclusive UTC end time")] = None,
        region: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
        channel: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> MinuteMetricsResponse:
        try:
            resolved_start, resolved_end = _resolve_range(start, end)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        rows = metrics_repository.fetch_minutes(
            start=resolved_start,
            end=resolved_end,
            region=region,
            channel=channel,
            limit=limit,
        )
        filters = MetricFilters(
            start=resolved_start,
            end=resolved_end,
            region=region,
            channel=channel,
        )
        items = [MinuteMetric.model_validate(row) for row in rows]
        return MinuteMetricsResponse(
            generated_at=datetime.now(UTC),
            filters=filters,
            count=len(items),
            limit=limit,
            items=items,
        )

    @app.get(
        "/api/v1/metrics/summary",
        response_model=MetricSummaryResponse,
        responses={503: {"model": ErrorResponse}},
        tags=["metrics"],
    )
    def metric_summary(
        metrics_repository: Annotated[MetricsRepository, Depends(get_repository)],
        start: Annotated[datetime | None, Query(description="Inclusive UTC start time")] = None,
        end: Annotated[datetime | None, Query(description="Exclusive UTC end time")] = None,
        region: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
        channel: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
    ) -> MetricSummaryResponse:
        try:
            resolved_start, resolved_end = _resolve_range(start, end)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        row = metrics_repository.fetch_summary(
            start=resolved_start,
            end=resolved_end,
            region=region,
            channel=channel,
        )
        order_count = int(row["order_count"])
        return MetricSummaryResponse(
            generated_at=datetime.now(UTC),
            filters=MetricFilters(
                start=resolved_start,
                end=resolved_end,
                region=region,
                channel=channel,
            ),
            has_data=order_count > 0,
            order_count=order_count,
            gmv=str(row["gmv"]),
            average_order_value=str(row["average_order_value"]),
            latest_processed_at=row.get("latest_processed_at"),
        )

    @app.get(
        "/api/v1/metrics/comparison",
        response_model=MetricComparisonResponse,
        responses={503: {"model": ErrorResponse}},
        tags=["metrics"],
    )
    def metric_comparison(
        metrics_repository: Annotated[MetricsRepository, Depends(get_repository)],
        start: Annotated[datetime, Query(description="Current inclusive UTC start time")],
        end: Annotated[datetime, Query(description="Current exclusive UTC end time")],
        baseline_start: Annotated[datetime, Query(description="Baseline inclusive UTC start time")],
        baseline_end: Annotated[datetime, Query(description="Baseline exclusive UTC end time")],
        region: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
        channel: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
    ) -> MetricComparisonResponse:
        try:
            current_start, current_end = _resolve_range(start, end)
            previous_start, previous_end = _resolve_range(baseline_start, baseline_end)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if current_end - current_start != previous_end - previous_start:
            raise HTTPException(status_code=422, detail="current and baseline ranges must have equal duration")

        generated_at = datetime.now(UTC)

        def summary_for(range_start: datetime, range_end: datetime) -> MetricSummaryResponse:
            row = metrics_repository.fetch_summary(
                start=range_start, end=range_end, region=region, channel=channel
            )
            order_count = int(row["order_count"])
            return MetricSummaryResponse(
                generated_at=generated_at,
                filters=MetricFilters(start=range_start, end=range_end, region=region, channel=channel),
                has_data=order_count > 0,
                order_count=order_count,
                gmv=str(row["gmv"]),
                average_order_value=str(row["average_order_value"]),
                latest_processed_at=row.get("latest_processed_at"),
            )

        current = summary_for(current_start, current_end)
        baseline = summary_for(previous_start, previous_end)

        def rate(current_value: Decimal, baseline_value: Decimal) -> float | None:
            if baseline_value == 0:
                return None
            return round(float((current_value - baseline_value) / baseline_value), 6)

        current_gmv, baseline_gmv = Decimal(current.gmv), Decimal(baseline.gmv)
        current_aov = Decimal(current.average_order_value)
        baseline_aov = Decimal(baseline.average_order_value)
        return MetricComparisonResponse(
            generated_at=generated_at,
            current=current,
            baseline=baseline,
            delta=MetricComparisonDelta(
                order_count=current.order_count - baseline.order_count,
                gmv=str((current_gmv - baseline_gmv).quantize(Decimal("0.01"))),
                average_order_value=str((current_aov - baseline_aov).quantize(Decimal("0.01"))),
                order_count_rate=rate(Decimal(current.order_count), Decimal(baseline.order_count)),
                gmv_rate=rate(current_gmv, baseline_gmv),
                average_order_value_rate=rate(current_aov, baseline_aov),
            ),
        )

    @app.get(
        "/api/v1/metrics/timeseries",
        response_model=TimeSeriesResponse,
        responses={503: {"model": ErrorResponse}},
        tags=["metrics"],
    )
    def metric_time_series(
        metrics_repository: Annotated[MetricsRepository, Depends(get_repository)],
        start: Annotated[datetime | None, Query(description="Inclusive UTC start time")] = None,
        end: Annotated[datetime | None, Query(description="Exclusive UTC end time")] = None,
        region: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
        channel: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
        bucket: Annotated[TimeBucket, Query()] = "auto",
    ) -> TimeSeriesResponse:
        try:
            resolved_start, resolved_end = _resolve_range(start, end)
            resolved_bucket = _resolve_bucket(resolved_start, resolved_end, bucket)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        rows = metrics_repository.fetch_time_series(
            start=resolved_start,
            end=resolved_end,
            region=region,
            channel=channel,
            bucket=resolved_bucket,
        )
        items = [TimeSeriesPoint.model_validate(row) for row in rows]
        return TimeSeriesResponse(
            generated_at=datetime.now(UTC),
            filters=MetricFilters(
                start=resolved_start,
                end=resolved_end,
                region=region,
                channel=channel,
            ),
            bucket=resolved_bucket,
            count=len(items),
            items=items,
        )

    @app.get(
        "/api/v1/metrics/breakdown",
        response_model=BreakdownResponse,
        responses={503: {"model": ErrorResponse}},
        tags=["metrics"],
    )
    def metric_breakdown(
        metrics_repository: Annotated[MetricsRepository, Depends(get_repository)],
        dimension: Annotated[BreakdownDimension, Query()],
        start: Annotated[datetime | None, Query(description="Inclusive UTC start time")] = None,
        end: Annotated[datetime | None, Query(description="Exclusive UTC end time")] = None,
        region: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
        channel: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
        limit: Annotated[int, Query(ge=1, le=50)] = 12,
    ) -> BreakdownResponse:
        try:
            resolved_start, resolved_end = _resolve_range(start, end)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        rows = metrics_repository.fetch_breakdown(
            start=resolved_start,
            end=resolved_end,
            region=region,
            channel=channel,
            dimension=dimension,
            limit=limit,
        )
        items = [BreakdownItem.model_validate(row) for row in rows]
        return BreakdownResponse(
            generated_at=datetime.now(UTC),
            filters=MetricFilters(
                start=resolved_start,
                end=resolved_end,
                region=region,
                channel=channel,
            ),
            dimension=dimension,
            count=len(items),
            items=items,
        )

    @app.get(
        "/api/v1/products/breakdown",
        response_model=ProductBreakdownResponse,
        responses={503: {"model": ErrorResponse}},
        tags=["products"],
    )
    def product_breakdown(
        metrics_repository: Annotated[MetricsRepository, Depends(get_repository)],
        dimension: Annotated[ProductDimension, Query()] = "category",
        start: Annotated[datetime | None, Query(description="Inclusive UTC start time")] = None,
        end: Annotated[datetime | None, Query(description="Exclusive UTC end time")] = None,
        category: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
        limit: Annotated[int, Query(ge=1, le=50)] = 12,
    ) -> ProductBreakdownResponse:
        try:
            resolved_start, resolved_end = _resolve_range(start, end)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        rows = metrics_repository.fetch_product_breakdown(
            start=resolved_start,
            end=resolved_end,
            category=category,
            dimension=dimension,
            limit=limit,
        )
        items = [ProductBreakdownItem.model_validate(row) for row in rows]
        return ProductBreakdownResponse(
            generated_at=datetime.now(UTC),
            start=resolved_start,
            end=resolved_end,
            category=category,
            dimension=dimension,
            count=len(items),
            items=items,
        )

    @app.get("/api/v2/products/trends", tags=["products"])
    def product_trends(
        metrics_repository: Annotated[MetricsRepository, Depends(get_repository)],
        dimension: Annotated[ProductDimension, Query()] = "category",
        start: Annotated[datetime | None, Query()] = None,
        end: Annotated[datetime | None, Query()] = None,
        category: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
        limit: Annotated[int, Query(ge=1, le=50)] = 12,
    ) -> dict[str, object]:
        try:
            resolved_start, resolved_end = _resolve_range(start, end)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        duration = resolved_end - resolved_start
        current = metrics_repository.fetch_product_breakdown(start=resolved_start, end=resolved_end, category=category, dimension=dimension, limit=limit)
        baseline = metrics_repository.fetch_product_breakdown(start=resolved_start - duration, end=resolved_start, category=category, dimension=dimension, limit=limit)
        items = compare_product_windows(current, baseline)
        return {"generated_at": datetime.now(UTC), "start": resolved_start, "end": resolved_end, "dimension": dimension, "count": len(items), "items": items}

    @app.get("/api/v2/products/contribution", tags=["products"])
    def product_contributions(
        metrics_repository: Annotated[MetricsRepository, Depends(get_repository)],
        dimension: Annotated[ProductDimension, Query()] = "category",
        start: Annotated[datetime | None, Query()] = None,
        end: Annotated[datetime | None, Query()] = None,
        category: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
        limit: Annotated[int, Query(ge=1, le=50)] = 12,
    ) -> dict[str, object]:
        try:
            resolved_start, resolved_end = _resolve_range(start, end)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        rows = metrics_repository.fetch_product_breakdown(start=resolved_start, end=resolved_end, category=category, dimension=dimension, limit=limit)
        items = product_contribution(rows)
        return {"generated_at": datetime.now(UTC), "dimension": dimension, "count": len(items), "items": items}

    @app.get("/api/v2/products/alerts", tags=["products"])
    def product_alert_feed(
        metrics_repository: Annotated[MetricsRepository, Depends(get_repository)],
        start: Annotated[datetime | None, Query()] = None,
        end: Annotated[datetime | None, Query()] = None,
        rate_threshold: Annotated[float, Query(gt=0, le=5)] = 0.25,
    ) -> dict[str, object]:
        try:
            resolved_start, resolved_end = _resolve_range(start, end)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        duration = resolved_end - resolved_start
        current = metrics_repository.fetch_product_breakdown(start=resolved_start, end=resolved_end, category=None, dimension="sku", limit=50)
        baseline = metrics_repository.fetch_product_breakdown(start=resolved_start - duration, end=resolved_start, category=None, dimension="sku", limit=50)
        items = product_alerts(compare_product_windows(current, baseline), rate_threshold=rate_threshold)
        return {"generated_at": datetime.now(UTC), "alert_count": len(items), "rate_threshold": rate_threshold, "items": items}

    @app.get("/api/v2/operations/resource-plan", tags=["operations"])
    def product_resource_plan(
        metrics_repository: Annotated[MetricsRepository, Depends(get_repository)],
        refresh_seconds: Annotated[int, Query(ge=5, le=3600)] = 15,
    ) -> dict[str, object]:
        end = datetime.now(UTC)
        start = end - DEFAULT_RANGE
        baseline_start = start - DEFAULT_RANGE
        current = metrics_repository.fetch_product_breakdown(start=start, end=end, category=None, dimension="sku", limit=50)
        baseline = metrics_repository.fetch_product_breakdown(start=baseline_start, end=start, category=None, dimension="sku", limit=50)
        alerts = product_alerts(compare_product_windows(current, baseline))
        return {"generated_at": end, **resource_plan(product_count=len(current), alert_count=len(alerts), refresh_seconds=refresh_seconds)}

    @app.get("/api/v3/operations/command-center", tags=["operations"])
    def commerce_command_center(
        metrics_repository: Annotated[MetricsRepository, Depends(get_repository)],
    ) -> dict[str, object]:
        end = datetime.now(UTC)
        start = end - DEFAULT_RANGE
        current = metrics_repository.fetch_product_breakdown(start=start, end=end, category=None, dimension="sku", limit=50)
        baseline = metrics_repository.fetch_product_breakdown(start=start - DEFAULT_RANGE, end=start, category=None, dimension="sku", limit=50)
        return {"generated_at": end, **command_center(current, baseline)}

    @app.get("/api/v3/operations/campaign-pacing", tags=["operations"])
    def commerce_campaign_pacing(
        current_gmv: Annotated[Decimal, Query(ge=0)],
        target_gmv: Annotated[Decimal, Query(gt=0)],
        elapsed_ratio: Annotated[float, Query(gt=0, le=1)],
    ) -> dict[str, object]:
        return campaign_pacing(current_gmv=current_gmv, target_gmv=target_gmv, elapsed_ratio=elapsed_ratio)

    @app.get("/api/v3/operations/inventory-signal", tags=["operations"])
    def commerce_inventory_signal(
        available_units: Annotated[int, Query(ge=0)],
        demand_per_hour: Annotated[float, Query(ge=0)],
        replenishment_hours: Annotated[float, Query(ge=0)],
    ) -> dict[str, object]:
        return inventory_signal(available_units=available_units, demand_per_hour=demand_per_hour, replenishment_hours=replenishment_hours)

    @app.get("/api/v3/operations/briefing", tags=["operations"])
    def commerce_operating_briefing(
        alert_count: Annotated[int, Query(ge=0)] = 0,
        campaign_status: Annotated[Literal["AHEAD", "ON_PACE", "BEHIND"], Query()] = "ON_PACE",
        inventory_status: Annotated[Literal["HEALTHY", "REPLENISH_SOON", "STOCKOUT_RISK", "NO_DEMAND"], Query()] = "HEALTHY",
    ) -> dict[str, object]:
        return operating_briefing(alert_count=alert_count, campaign_status=campaign_status, inventory_status=inventory_status)

    @app.get("/api/v3/operations/conversion-funnel", tags=["operations"])
    def commerce_conversion_funnel(
        views: Annotated[int, Query(ge=0)], carts: Annotated[int, Query(ge=0)],
        orders: Annotated[int, Query(ge=0)],
    ) -> dict[str, object]:
        try:
            return conversion_funnel(views=views, carts=carts, orders=orders)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/api/v3/operations/alert-acknowledgement", tags=["operations"])
    def commerce_alert_acknowledgement(
        alert_count: Annotated[int, Query(ge=0)], owner: Annotated[str, Query(min_length=1, max_length=80)],
        acknowledged_count: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, object]:
        try:
            return alert_acknowledgement(alert_count=alert_count, owner=owner, acknowledged_count=acknowledged_count)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/api/v3/operations/campaign-guardrail", tags=["operations"])
    def commerce_campaign_guardrail(
        discount_rate: Annotated[float, Query(ge=0, le=1)],
        inventory_status: Annotated[Literal["HEALTHY", "REPLENISH_SOON", "STOCKOUT_RISK", "NO_DEMAND"], Query()],
        campaign_status: Annotated[Literal["AHEAD", "ON_PACE", "BEHIND"], Query()],
    ) -> dict[str, object]:
        return campaign_guardrail(discount_rate=discount_rate, inventory_status=inventory_status, campaign_status=campaign_status)

    @app.get("/api/v3/operations/shift-handoff", tags=["operations"])
    def commerce_shift_handoff(
        alert_count: Annotated[int, Query(ge=0)], unacknowledged_count: Annotated[int, Query(ge=0)],
        campaign_status: Annotated[Literal["AHEAD", "ON_PACE", "BEHIND"], Query()],
        inventory_status: Annotated[Literal["HEALTHY", "REPLENISH_SOON", "STOCKOUT_RISK", "NO_DEMAND"], Query()],
    ) -> dict[str, object]:
        try:
            return shift_handoff(alert_count=alert_count, unacknowledged_count=unacknowledged_count, campaign_status=campaign_status, inventory_status=inventory_status)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/api/v3/operations/promotion-margin", tags=["operations"])
    def commerce_promotion_margin(
        selling_price: Annotated[Decimal, Query(gt=0)],
        unit_cost: Annotated[Decimal, Query(ge=0)],
        discount_rate: Annotated[float, Query(ge=0, lt=1)],
        shipping_subsidy: Annotated[Decimal, Query(ge=0)] = Decimal("0"),
        expected_return_rate: Annotated[float, Query(ge=0, lt=1)] = 0,
        minimum_margin_rate: Annotated[float, Query(ge=0, lt=1)] = 0.1,
    ) -> dict[str, object]:
        return promotion_margin_guardrail(
            selling_price=selling_price, unit_cost=unit_cost,
            discount_rate=discount_rate, shipping_subsidy=shipping_subsidy,
            expected_return_rate=expected_return_rate,
            minimum_margin_rate=minimum_margin_rate,
        )

    @app.get(
        "/api/v1/anomalies/summary",
        response_model=AnomalySummaryResponse,
        responses={503: {"model": ErrorResponse}},
        tags=["anomalies"],
    )
    def anomaly_summary(
        metrics_repository: Annotated[MetricsRepository, Depends(get_repository)],
        start: Annotated[datetime | None, Query(description="Inclusive UTC start time")] = None,
        end: Annotated[datetime | None, Query(description="Exclusive UTC end time")] = None,
        anomaly_type: Annotated[AnomalyType | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> AnomalySummaryResponse:
        try:
            resolved_start, resolved_end = _resolve_range(start, end)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        rows = metrics_repository.fetch_anomaly_summary(
            start=resolved_start,
            end=resolved_end,
            anomaly_type=anomaly_type,
            limit=limit,
        )
        items = [AnomalySummaryItem.model_validate(row) for row in rows]
        rejected_count = sum(
            item.anomaly_count for item in items if item.anomaly_type == "rejected"
        )
        late_count = sum(
            item.anomaly_count for item in items if item.anomaly_type == "late"
        )
        return AnomalySummaryResponse(
            generated_at=datetime.now(UTC),
            filters=AnomalyFilters(
                start=resolved_start,
                end=resolved_end,
                anomaly_type=anomaly_type,
            ),
            total_count=rejected_count + late_count,
            rejected_count=rejected_count,
            late_count=late_count,
            count=len(items),
            limit=limit,
            items=items,
        )

    @app.get(
        "/api/v1/operations/assets",
        response_model=AssetCatalogResponse,
        tags=["operations"],
    )
    def asset_catalog() -> AssetCatalogResponse:
        assets = app.state.asset_catalog.list_assets()
        items = [
            AssetCatalogItem(
                asset_id=asset.asset_id,
                asset_name=asset.name,
                asset_kind=asset.kind,
                owner=asset.owner,
                upstream_assets=list(asset.upstreams),
                downstream_assets=list(app.state.asset_catalog.downstream(asset.asset_id)),
                freshness_slo_seconds=asset.freshness_slo_seconds,
            )
            for asset in assets
        ]
        return AssetCatalogResponse(
            generated_at=datetime.now(UTC),
            asset_count=len(items),
            source_count=sum(not item.upstream_assets for item in items),
            monitored_count=sum(item.freshness_slo_seconds is not None for item in items),
            items=items,
        )

    @app.get(
        "/api/v1/operations/assets/health",
        tags=["operations"],
    )
    def asset_health(
        metrics_repository: Annotated[MetricsRepository, Depends(get_repository)],
        evaluated_at: Annotated[
            datetime | None,
            Query(description="Optional UTC evaluation time for reproducible checks"),
        ] = None,
    ) -> dict[str, object]:
        now = _utc(evaluated_at or datetime.now(UTC))
        row = metrics_repository.fetch_summary(
            start=now - DEFAULT_RANGE,
            end=now,
            region=None,
            channel=None,
        )
        observed_at = row.get("latest_processed_at")
        if isinstance(observed_at, str):
            observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        evaluations = [
            app.state.asset_catalog.evaluate_freshness(
                asset.asset_id,
                observed_at=observed_at,
                evaluated_at=now,
            )
            for asset in app.state.asset_catalog.list_assets()
            if asset.freshness_slo_seconds is not None
        ]
        status_counts = {
            status: sum(item.status == status for item in evaluations)
            for status in ("fresh", "stale", "no_data")
        }
        prioritized = sorted(
            evaluations,
            key=lambda item: (-item.priority_score, item.asset.asset_id),
        )
        return {
            "generated_at": now,
            "status": (
                "no_data" if status_counts["no_data"] else
                "stale" if status_counts["stale"] else "fresh"
            ),
            "monitored_count": len(evaluations),
            "status_counts": status_counts,
            "impacted_assets": sorted({
                impacted
                for item in evaluations
                if item.status != "fresh"
                for impacted in item.impacted_assets
            }),
            "priority_count": sum(item.status != "fresh" for item in evaluations),
            "items": [
                {
                    "priority_rank": rank,
                    "priority_score": item.priority_score,
                    "asset_id": item.asset.asset_id,
                    "owner": item.asset.owner,
                    "status": item.status,
                    "freshness_slo_seconds": item.asset.freshness_slo_seconds,
                    "observed_at": item.observed_at,
                    "lag_seconds": item.lag_seconds,
                    "impacted_assets": list(item.impacted_assets),
                }
                for rank, item in enumerate(prioritized, start=1)
            ],
        }

    @app.get(
        "/api/v1/operations/assets/{asset_id}/freshness",
        response_model=AssetFreshnessResponse,
        responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
        tags=["operations"],
    )
    def asset_freshness(
        asset_id: str,
        metrics_repository: Annotated[MetricsRepository, Depends(get_repository)],
        evaluated_at: Annotated[
            datetime | None,
            Query(description="Optional UTC evaluation time for reproducible checks"),
        ] = None,
    ) -> AssetFreshnessResponse:
        now = _utc(evaluated_at or datetime.now(UTC))
        try:
            asset = app.state.asset_catalog.get(asset_id)
            if asset.freshness_slo_seconds is None:
                raise DataCatalogError(f"asset {asset_id} has no freshness SLO")
        except DataCatalogError as error:
            raise HTTPException(
                status_code=404,
                detail={"code": "asset_not_found", "message": str(error)},
            ) from error
        row = metrics_repository.fetch_summary(
            start=now - DEFAULT_RANGE,
            end=now,
            region=None,
            channel=None,
        )
        observed_at = row.get("latest_processed_at")
        if isinstance(observed_at, str):
            observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        evaluation = app.state.asset_catalog.evaluate_freshness(
            asset_id,
            observed_at=observed_at,
            evaluated_at=now,
        )
        return AssetFreshnessResponse(
            generated_at=now,
            asset_id=asset.asset_id,
            asset_name=asset.name,
            asset_kind=asset.kind,
            owner=asset.owner,
            status=evaluation.status,
            freshness_slo_seconds=asset.freshness_slo_seconds,
            observed_at=evaluation.observed_at,
            lag_seconds=evaluation.lag_seconds,
            impacted_assets=list(evaluation.impacted_assets),
        )

    @app.get(
        "/api/v1/quality/runs",
        response_model=QualityRunsResponse,
        responses={503: {"model": ErrorResponse}},
        tags=["data quality"],
    )
    def quality_runs(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=500)] = 20,
        passed: Annotated[bool | None, Query()] = None,
    ) -> QualityRunsResponse:
        try:
            history = get_quality_history(request)
            rows = history.list_runs(limit=limit, passed=passed)
        except (OSError, sqlite3.Error, ValueError) as error:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "quality_history_unavailable",
                    "message": "The quality history is temporarily unavailable.",
                },
            ) from error
        items = [
            QualityRunItem.model_validate(
                {**row.to_dict(), "input_file": Path(row.input_file).name}
            )
            for row in rows
        ]
        return QualityRunsResponse(
            generated_at=datetime.now(UTC),
            count=len(items),
            limit=limit,
            passed=passed,
            items=items,
        )

    @app.get(
        "/api/v1/quality/trend",
        response_model=QualityTrendResponse,
        responses={503: {"model": ErrorResponse}},
        tags=["data quality"],
    )
    def quality_trend(
        request: Request,
        rule_id: Annotated[str, Query(min_length=1, max_length=100)],
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
    ) -> QualityTrendResponse:
        try:
            history = get_quality_history(request)
            rows = history.rule_trend(rule_id, limit=limit)
        except (OSError, sqlite3.Error, ValueError) as error:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "quality_history_unavailable",
                    "message": "The quality history is temporarily unavailable.",
                },
            ) from error
        items = [
            QualityTrendPoint.model_validate(
                {
                    "run_id": row.run_id,
                    "generated_at": row.generated_at,
                    "passed": row.passed,
                    "checked_records": row.checked_records,
                    "violations": row.violations,
                    "metric_name": row.metric_name,
                    "observed_value": row.observed_value,
                    "threshold": row.threshold,
                }
            )
            for row in rows
        ]
        return QualityTrendResponse(
            generated_at=datetime.now(UTC),
            rule_id=rule_id,
            count=len(items),
            limit=limit,
            items=items,
        )

    return app


app = create_app()

