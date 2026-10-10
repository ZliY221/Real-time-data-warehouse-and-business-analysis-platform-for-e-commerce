"""Collect a bounded, sanitized snapshot from the Apache Flink REST API."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import math
import re
from typing import Any, Callable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


JOB_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")
VERTEX_METRICS = (
    "numRecordsIn",
    "numRecordsOut",
    "numRecordsInPerSecond",
    "numRecordsOutPerSecond",
    "backPressuredTimeMsPerSecond",
    "idleTimeMsPerSecond",
    "busyTimeMsPerSecond",
)
JOB_METRICS = ("numRestarts", "uptime", "downtime")


class FlinkRestError(RuntimeError):
    """Raised when runtime evidence cannot be collected unambiguously."""


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must include timezone information")
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _validate_base_url(base_url: str, *, allow_remote: bool) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Flink REST URL must use http or https")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Flink REST URL must contain a host and no credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("Flink REST URL must not contain a query or fragment")
    if not allow_remote and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("remote Flink REST hosts require allow_remote=True")
    return base_url.rstrip("/")


def _metric_value(raw_value: Any) -> int | float | None:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    if value.is_integer():
        return int(value)
    return round(value, 6)


def _metric_map(rows: Any) -> dict[str, int | float | None]:
    if not isinstance(rows, list):
        raise FlinkRestError("Flink metric response must be a list")
    metrics: dict[str, int | float | None] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise FlinkRestError("Flink metric response contains an invalid row")
        metrics[row["id"]] = _metric_value(row.get("value"))
    return metrics


def _metric_ids(rows: Any) -> tuple[str, ...]:
    if not isinstance(rows, list):
        raise FlinkRestError("Flink metric discovery response must be a list")
    identifiers: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise FlinkRestError("Flink metric discovery contains an invalid row")
        identifiers.append(row["id"])
    return tuple(identifiers)


def _aggregate_vertex_metrics(
    rows: Any,
    selected_ids: dict[str, tuple[str, ...]],
) -> dict[str, int | float | None]:
    values_by_id = _metric_map(rows)
    aggregated: dict[str, int | float | None] = {}
    max_metrics = {
        "backPressuredTimeMsPerSecond",
        "idleTimeMsPerSecond",
        "busyTimeMsPerSecond",
    }
    for name in VERTEX_METRICS:
        values = [
            values_by_id[identifier]
            for identifier in selected_ids.get(name, ())
            if values_by_id.get(identifier) is not None
        ]
        if not values:
            aggregated[name] = None
        elif name in max_metrics:
            aggregated[name] = max(values)
        else:
            total = sum(values)
            aggregated[name] = int(total) if float(total).is_integer() else round(total, 6)
    return aggregated


def _derived_backpressure(metrics: dict[str, int | float | None]) -> dict[str, Any]:
    milliseconds = metrics.get("backPressuredTimeMsPerSecond")
    if milliseconds is None:
        return {"level": None, "ratio": None}
    ratio = min(max(float(milliseconds) / 1000.0, 0.0), 1.0)
    if ratio <= 0.10:
        level = "ok"
    elif ratio <= 0.50:
        level = "low"
    else:
        level = "high"
    return {"level": level, "ratio": round(ratio, 6)}


class FlinkRestClient:
    """Minimal read-only client with a local-only default for safer evidence runs."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8081",
        *,
        timeout_seconds: float = 10.0,
        allow_remote: bool = False,
        fetch_json: Callable[[str], Any] | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self.base_url = _validate_base_url(base_url, allow_remote=allow_remote)
        self.timeout_seconds = timeout_seconds
        self._fetch_json = fetch_json or self._request_json

    def _request_json(self, url: str) -> Any:
        request = Request(url, headers={"Accept": "application/json"}, method="GET")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.load(response)
        except Exception as error:
            raise FlinkRestError(f"Flink REST request failed: {type(error).__name__}") from error

    def get_json(self, path: str, query: dict[str, str] | None = None) -> Any:
        if not path.startswith("/") or ".." in path:
            raise ValueError("Flink REST path must be absolute and may not contain traversal")
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        return self._fetch_json(url)

    def job(self, job_id: str) -> dict[str, Any]:
        _validate_job_id(job_id)
        document = self.get_json(f"/jobs/{job_id}")
        if not isinstance(document, dict):
            raise FlinkRestError("Flink job response must be an object")
        return document

    def metrics(self, path: str, names: tuple[str, ...]) -> dict[str, int | float | None]:
        return _metric_map(self.get_json(path, {"get": ",".join(names)}))

    def vertex_metrics(self, path: str) -> tuple[dict[str, int | float | None], dict[str, int]]:
        available_ids = _metric_ids(self.get_json(path))
        selected_ids = {
            name: tuple(
                identifier
                for identifier in available_ids
                if identifier == name or identifier.endswith(f".{name}")
            )
            for name in VERTEX_METRICS
        }
        requested_ids = tuple(
            identifier
            for name in VERTEX_METRICS
            for identifier in selected_ids[name]
        )
        rows = self.get_json(path, {"get": ",".join(requested_ids)}) if requested_ids else []
        return (
            _aggregate_vertex_metrics(rows, selected_ids),
            {name: len(selected_ids[name]) for name in VERTEX_METRICS},
        )


def _validate_job_id(job_id: str) -> None:
    if not JOB_ID_PATTERN.fullmatch(job_id):
        raise ValueError("Flink job ID must contain exactly 32 hexadecimal characters")


def _checkpoint_summary(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise FlinkRestError("Flink checkpoint response must be an object")
    counts = document.get("counts")
    if not isinstance(counts, dict):
        raise FlinkRestError("Flink checkpoint response is missing counts")
    safe_counts = {
        name: int(counts.get(name, 0))
        for name in ("total", "in_progress", "completed", "failed", "restored")
    }
    latest_completed = (document.get("latest") or {}).get("completed") or {}
    latest = None
    if isinstance(latest_completed, dict) and latest_completed:
        latest = {
            "id": latest_completed.get("id"),
            "status": latest_completed.get("status"),
            "duration_ms": latest_completed.get("end_to_end_duration"),
            "checkpointed_size_bytes": latest_completed.get("checkpointed_size"),
            "processed_data_bytes": latest_completed.get("processed_data"),
            "persisted_data_bytes": latest_completed.get("persisted_data"),
            "acknowledged_subtasks": latest_completed.get("num_acknowledged_subtasks"),
            "subtasks": latest_completed.get("num_subtasks"),
        }
    return {"counts": safe_counts, "latest_completed": latest}


def _backpressure_summary(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise FlinkRestError("Flink backpressure response must be an object")
    subtasks = document.get("subtasks") or []
    if not isinstance(subtasks, list):
        raise FlinkRestError("Flink backpressure subtasks must be a list")
    return {
        "status": document.get("status"),
        "level": document.get("backpressure-level", document.get("backpressureLevel")),
        "max_backpressure_ratio": max(
            (
                float(item.get("ratio", 0.0))
                for item in subtasks
                if isinstance(item, dict)
            ),
            default=0.0,
        ),
        "subtask_count": len(subtasks),
    }


def collect_runtime_snapshot(
    client: FlinkRestClient,
    job_id: str,
    *,
    collected_at: datetime | None = None,
) -> dict[str, Any]:
    """Collect one bounded snapshot without logs, exception text, or event payloads."""

    _validate_job_id(job_id)
    timestamp = collected_at or datetime.now(UTC)
    job = client.job(job_id)
    raw_vertices = job.get("vertices")
    if not isinstance(raw_vertices, list):
        raise FlinkRestError("Flink job response is missing vertices")

    vertices: list[dict[str, Any]] = []
    for raw_vertex in raw_vertices:
        if not isinstance(raw_vertex, dict) or not isinstance(raw_vertex.get("id"), str):
            raise FlinkRestError("Flink job response contains an invalid vertex")
        vertex_id = raw_vertex["id"]
        metrics, metric_series = client.vertex_metrics(
            f"/jobs/{job_id}/vertices/{vertex_id}/metrics"
        )
        backpressure = _backpressure_summary(
            client.get_json(f"/jobs/{job_id}/vertices/{vertex_id}/backpressure")
        )
        derived_backpressure = _derived_backpressure(metrics)
        if backpressure["status"] == "deprecated" or backpressure["level"] is None:
            backpressure["level"] = derived_backpressure["level"]
            backpressure["max_backpressure_ratio"] = derived_backpressure["ratio"]
            backpressure["source"] = "task_metric"
        else:
            backpressure["source"] = "vertex_endpoint"
        vertices.append(
            {
                "id": vertex_id,
                "name": raw_vertex.get("name"),
                "status": raw_vertex.get("status"),
                "parallelism": raw_vertex.get("parallelism"),
                "metrics": {name: metrics.get(name) for name in VERTEX_METRICS},
                "metric_series": metric_series,
                "backpressure": backpressure,
            }
        )

    return {
        "report_version": "1.0",
        "collected_at": _utc_text(timestamp),
        "source": client.base_url,
        "job": {
            "id": job_id.lower(),
            "name": job.get("name"),
            "state": job.get("state"),
            "duration_ms": job.get("duration"),
            "metrics": client.metrics(f"/jobs/{job_id}/metrics", JOB_METRICS),
        },
        "checkpoints": _checkpoint_summary(client.get_json(f"/jobs/{job_id}/checkpoints")),
        "vertices": vertices,
        "privacy": {
            "contains_event_payloads": False,
            "contains_exception_messages": False,
        },
    }
