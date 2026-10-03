from __future__ import annotations

from base64 import b64encode
from collections.abc import Callable
from datetime import datetime
import json
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from metrics_api.config import ApiSettings


class MetricsRepositoryError(RuntimeError):
    """Raised when the analytics store cannot serve a query."""


class MetricsRepository(Protocol):
    def ping(self) -> None: ...

    def fetch_minutes(
        self,
        *,
        start: datetime,
        end: datetime,
        region: str | None,
        channel: str | None,
        limit: int,
    ) -> list[dict[str, Any]]: ...

    def fetch_summary(
        self,
        *,
        start: datetime,
        end: datetime,
        region: str | None,
        channel: str | None,
    ) -> dict[str, Any]: ...

    def fetch_time_series(
        self,
        *,
        start: datetime,
        end: datetime,
        region: str | None,
        channel: str | None,
        bucket: str,
    ) -> list[dict[str, Any]]: ...

    def fetch_breakdown(
        self,
        *,
        start: datetime,
        end: datetime,
        region: str | None,
        channel: str | None,
        dimension: str,
        limit: int,
    ) -> list[dict[str, Any]]: ...


class ClickHouseHttpRepository:
    def __init__(
        self,
        settings: ApiSettings,
        *,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        settings.validate()
        self._settings = settings
        self._opener = opener

    def ping(self) -> None:
        rows = self._execute("SELECT 1 AS ok FORMAT JSONEachRow")
        if rows != [{"ok": 1}]:
            raise MetricsRepositoryError("ClickHouse returned an unexpected health response")

    def fetch_minutes(
        self,
        *,
        start: datetime,
        end: datetime,
        region: str | None,
        channel: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        where_sql, parameters = self._build_filters(start, end, region, channel)
        parameters["limit"] = str(limit)
        sql = f"""
SELECT
    toString(window_start) AS window_start,
    toString(window_end) AS window_end,
    region,
    channel,
    order_count,
    toString(gmv) AS gmv,
    toString(average_order_value) AS average_order_value,
    version,
    toString(processed_at) AS processed_at
FROM minute_metrics_latest
WHERE {where_sql}
ORDER BY window_start DESC, region ASC, channel ASC
LIMIT {{limit:UInt32}}
FORMAT JSONEachRow
""".strip()
        return self._execute(sql, parameters)

    def fetch_summary(
        self,
        *,
        start: datetime,
        end: datetime,
        region: str | None,
        channel: str | None,
    ) -> dict[str, Any]:
        where_sql, parameters = self._build_filters(start, end, region, channel)
        sql = f"""
SELECT
    sum(order_count) AS order_count,
    toString(sum(gmv)) AS gmv,
    if(sum(order_count) = 0, '0.00', toString(round(sum(gmv) / sum(order_count), 2)))
        AS average_order_value,
    if(count() = 0, NULL, toString(max(processed_at))) AS latest_processed_at
FROM minute_metrics_latest
WHERE {where_sql}
FORMAT JSONEachRow
""".strip()
        rows = self._execute(sql, parameters)
        if len(rows) != 1:
            raise MetricsRepositoryError("ClickHouse returned an unexpected summary response")
        return rows[0]

    def fetch_time_series(
        self,
        *,
        start: datetime,
        end: datetime,
        region: str | None,
        channel: str | None,
        bucket: str,
    ) -> list[dict[str, Any]]:
        bucket_sql = {
            "1m": "toStartOfMinute(window_start)",
            "5m": "toStartOfInterval(window_start, INTERVAL 5 MINUTE)",
            "15m": "toStartOfInterval(window_start, INTERVAL 15 MINUTE)",
            "1h": "toStartOfHour(window_start)",
        }.get(bucket)
        if bucket_sql is None:
            raise ValueError(f"Unsupported time bucket: {bucket}")

        where_sql, parameters = self._build_filters(start, end, region, channel)
        sql = f"""
SELECT
    toString({bucket_sql}) AS bucket_start,
    sum(order_count) AS order_count,
    toString(sum(gmv)) AS gmv,
    if(sum(order_count) = 0, '0.00', toString(round(sum(gmv) / sum(order_count), 2)))
        AS average_order_value
FROM minute_metrics_latest
WHERE {where_sql}
GROUP BY bucket_start
ORDER BY bucket_start ASC
FORMAT JSONEachRow
""".strip()
        return self._execute(sql, parameters)

    def fetch_breakdown(
        self,
        *,
        start: datetime,
        end: datetime,
        region: str | None,
        channel: str | None,
        dimension: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        dimension_sql = {"region": "region", "channel": "channel"}.get(dimension)
        if dimension_sql is None:
            raise ValueError(f"Unsupported breakdown dimension: {dimension}")

        where_sql, parameters = self._build_filters(start, end, region, channel)
        parameters["limit"] = str(limit)
        sql = f"""
SELECT
    {dimension_sql} AS name,
    sum(order_count) AS order_count,
    toString(sum(gmv)) AS gmv,
    if(sum(order_count) = 0, '0.00', toString(round(sum(gmv) / sum(order_count), 2)))
        AS average_order_value
FROM minute_metrics_latest
WHERE {where_sql}
GROUP BY name
ORDER BY sum(gmv) DESC, name ASC
LIMIT {{limit:UInt32}}
FORMAT JSONEachRow
""".strip()
        return self._execute(sql, parameters)

    @staticmethod
    def _build_filters(
        start: datetime,
        end: datetime,
        region: str | None,
        channel: str | None,
    ) -> tuple[str, dict[str, str]]:
        clauses = [
            "window_start >= {start:DateTime64(3, 'UTC')}",
            "window_start < {end:DateTime64(3, 'UTC')}",
        ]
        parameters = {
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        if region is not None:
            clauses.append("region = {region:String}")
            parameters["region"] = region
        if channel is not None:
            clauses.append("channel = {channel:String}")
            parameters["channel"] = channel
        return " AND ".join(clauses), parameters

    def _execute(
        self,
        sql: str,
        parameters: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        query_parameters = {
            "database": self._settings.clickhouse_database,
            "default_format": "JSONEachRow",
            "wait_end_of_query": "1",
        }
        for name, value in (parameters or {}).items():
            query_parameters[f"param_{name}"] = value

        url = f"{self._settings.clickhouse_url.rstrip('/')}/?{urlencode(query_parameters)}"
        credentials = f"{self._settings.clickhouse_user}:{self._settings.clickhouse_password}"
        authorization = b64encode(credentials.encode("utf-8")).decode("ascii")
        request = Request(
            url,
            data=sql.encode("utf-8"),
            method="POST",
            headers={
                "Accept": "application/x-ndjson",
                "Authorization": f"Basic {authorization}",
                "Content-Type": "text/plain; charset=utf-8",
            },
        )

        try:
            with self._opener(
                request,
                timeout=self._settings.clickhouse_timeout_seconds,
            ) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace").strip()
            raise MetricsRepositoryError(
                f"ClickHouse rejected the query with HTTP {error.code}: {detail[:200]}"
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise MetricsRepositoryError("ClickHouse is unavailable") from error

        try:
            return [json.loads(line) for line in payload.splitlines() if line.strip()]
        except json.JSONDecodeError as error:
            raise MetricsRepositoryError("ClickHouse returned invalid JSONEachRow data") from error

