"""ClickHouse sink-completion polling and end-to-end timing reports."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import json
import re
import time
from typing import Any
from urllib import parse, request

DATABASE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


class ClickHouseCountClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8123", database: str = "ecommerce"):
        parsed = parse.urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("ClickHouse URL must use HTTP(S) on a local host")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("ClickHouse URL must not contain credentials, query, or fragment")
        if not DATABASE_PATTERN.fullmatch(database):
            raise ValueError("database has an invalid format")
        self.base_url = base_url.rstrip("/")
        self.database = database

    def count_orders(self, start: datetime, end: datetime) -> int:
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("start and end must be timezone-aware and increasing")
        query = f"""
SELECT coalesce(sum(order_count), 0)
FROM {self.database}.minute_metrics_latest
WHERE window_start >= {{start:DateTime64(3, 'UTC')}}
  AND window_start < {{end:DateTime64(3, 'UTC')}}
FORMAT TabSeparatedRaw
""".strip()
        parameters = parse.urlencode(
            {
                "param_start": start.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                "param_end": end.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            }
        )
        http_request = request.Request(
            f"{self.base_url}/?{parameters}",
            data=query.encode("utf-8"),
            method="POST",
        )
        with request.urlopen(http_request, timeout=10) as response:
            value = response.read().decode("utf-8").strip()
        count = int(value)
        if count < 0:
            raise ValueError("ClickHouse returned a negative order count")
        return count


def wait_for_sink_completion(
    fetch_count: Callable[[], int],
    *,
    expected_records: int,
    timeout_seconds: float,
    poll_interval_seconds: float,
    started_at: datetime,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if expected_records < 1:
        raise ValueError("expected_records must be greater than zero")
    if timeout_seconds <= 0 or poll_interval_seconds <= 0:
        raise ValueError("timeout and poll interval must be greater than zero")
    if started_at.tzinfo is None:
        raise ValueError("started_at must include a timezone")

    started_clock = monotonic()
    attempts = 0
    observed = 0
    status = "TIMEOUT"
    while True:
        attempts += 1
        observed = fetch_count()
        if observed >= expected_records:
            status = "COMPLETE"
            break
        elapsed = monotonic() - started_clock
        if elapsed >= timeout_seconds:
            break
        sleeper(min(poll_interval_seconds, timeout_seconds - elapsed))
    elapsed_seconds = max(0.0, monotonic() - started_clock)
    completed_at = started_at.astimezone(UTC) + timedelta(seconds=elapsed_seconds)
    return {
        "report_version": "1.0",
        "status": status,
        "started_at": started_at.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "completed_at": completed_at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "elapsed_seconds": round(elapsed_seconds, 6),
        "expected_records": expected_records,
        "observed_records": observed,
        "poll_attempts": attempts,
        "end_to_end_throughput_per_second": (
            round(expected_records / elapsed_seconds, 3)
            if status == "COMPLETE" and elapsed_seconds > 0
            else None
        ),
        "claims": {
            "sink_completion_verified": status == "COMPLETE",
            "measured_pipeline_throughput": status == "COMPLETE" and elapsed_seconds > 0,
        },
    }
