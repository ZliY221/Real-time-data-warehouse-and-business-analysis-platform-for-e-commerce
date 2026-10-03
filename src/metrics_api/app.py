from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3
from threading import Lock
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from data_quality.history import QualityHistoryReader, QualityHistoryStore
from metrics_api.config import ApiSettings
from metrics_api.models import (
    BreakdownDimension,
    BreakdownItem,
    BreakdownResponse,
    ErrorResponse,
    HealthResponse,
    MetricFilters,
    MetricSummaryResponse,
    MinuteMetric,
    MinuteMetricsResponse,
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
) -> FastAPI:
    app = FastAPI(
        title="Ecommerce Realtime Metrics API",
        version="1.0.0",
        description="Read-only API for verified minute metrics stored in ClickHouse.",
    )
    app.state.repository = repository or ClickHouseHttpRepository(
        settings or ApiSettings.from_env()
    )
    app.state.data_mode = data_mode
    app.state.quality_history = quality_history
    app.state.quality_history_path = quality_history_path
    app.state.quality_history_lock = Lock()
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

