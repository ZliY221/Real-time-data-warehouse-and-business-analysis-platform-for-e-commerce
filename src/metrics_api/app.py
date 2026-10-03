from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from metrics_api.config import ApiSettings
from metrics_api.models import (
    ErrorResponse,
    HealthResponse,
    MetricFilters,
    MetricSummaryResponse,
    MinuteMetric,
    MinuteMetricsResponse,
)
from metrics_api.repository import (
    ClickHouseHttpRepository,
    MetricsRepository,
    MetricsRepositoryError,
)

MAX_RANGE = timedelta(days=31)
DEFAULT_RANGE = timedelta(hours=24)


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


def get_repository(request: Request) -> MetricsRepository:
    return request.app.state.repository


def create_app(
    repository: MetricsRepository | None = None,
    *,
    settings: ApiSettings | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Ecommerce Realtime Metrics API",
        version="1.0.0",
        description="Read-only API for verified minute metrics stored in ClickHouse.",
    )
    app.state.repository = repository or ClickHouseHttpRepository(
        settings or ApiSettings.from_env()
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
        return HealthResponse(status="ok", clickhouse="reachable")

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

    return app


app = create_app()

