from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
from typing import Any, Iterable

from event_generator.generator import CHANNELS, REGIONS
from event_generator.validation import validate_order_event

from .models import (
    BatchBaseline,
    MetricDifference,
    MetricKey,
    MinuteMetric,
    ReconciliationReport,
)


class ReconciliationInputError(ValueError):
    """Raised when an exported metric or late-event file is ambiguous or malformed."""


def _parse_json_line(raw_line: str, line_number: int, input_name: str) -> Any:
    try:
        return json.loads(raw_line, parse_float=Decimal)
    except json.JSONDecodeError as error:
        raise ReconciliationInputError(
            f"{input_name} line {line_number} is invalid JSON: {error.msg}"
        ) from error


def _parse_utc(value: Any, field: str, line_number: int) -> datetime:
    if not isinstance(value, str):
        raise ReconciliationInputError(f"actual metrics line {line_number} {field} must be text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ReconciliationInputError(
            f"actual metrics line {line_number} {field} is not ISO 8601"
        ) from error
    if parsed.tzinfo is None:
        raise ReconciliationInputError(
            f"actual metrics line {line_number} {field} must include a timezone"
        )
    return parsed.astimezone(UTC)


def _parse_non_negative_int(value: Any, field: str, line_number: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ReconciliationInputError(
            f"actual metrics line {line_number} {field} must be a non-negative integer"
        )
    return value


def _parse_money(value: Any, line_number: int) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ReconciliationInputError(
            f"actual metrics line {line_number} gmv must be a decimal value"
        )
    try:
        amount = Decimal(str(value))
    except InvalidOperation as error:
        raise ReconciliationInputError(
            f"actual metrics line {line_number} gmv must be a decimal value"
        ) from error
    if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
        raise ReconciliationInputError(
            f"actual metrics line {line_number} gmv must be non-negative with at most two decimals"
        )
    try:
        return amount.quantize(Decimal("0.01"))
    except InvalidOperation as error:
        raise ReconciliationInputError(
            f"actual metrics line {line_number} gmv is outside the supported decimal range"
        ) from error


def build_batch_baseline(
    lines: Iterable[str],
    *,
    late_event_ids: set[str] | frozenset[str] = frozenset(),
) -> BatchBaseline:
    total_records = 0
    parsed_records = 0
    invalid_json_records = 0
    invalid_contract_records = 0
    duplicate_records = 0
    excluded_late_records = 0
    seen_event_ids: set[str] = set()
    aggregates: dict[MetricKey, list[int | Decimal]] = defaultdict(
        lambda: [0, Decimal("0.00")]
    )

    for raw_line in lines:
        total_records += 1
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            invalid_json_records += 1
            continue
        parsed_records += 1
        if validate_order_event(event):
            invalid_contract_records += 1
            continue

        event_id = event["event_id"]
        if event_id in seen_event_ids:
            duplicate_records += 1
            continue
        seen_event_ids.add(event_id)
        if event_id in late_event_ids:
            excluded_late_records += 1
            continue

        event_time = datetime.fromisoformat(event["event_time"].replace("Z", "+00:00"))
        window_start = event_time.astimezone(UTC).replace(second=0, microsecond=0)
        payload = event["payload"]
        key = MetricKey(window_start, payload["region"], payload["channel"])
        aggregate = aggregates[key]
        aggregate[0] = int(aggregate[0]) + 1
        aggregate[1] = Decimal(aggregate[1]) + Decimal(payload["total_amount"])

    metrics = tuple(
        MinuteMetric(
            key.window_start,
            key.window_start + timedelta(minutes=1),
            key.region,
            key.channel,
            int(value[0]),
            Decimal(value[1]),
        )
        for key, value in sorted(aggregates.items())
    )
    return BatchBaseline(
        total_records,
        parsed_records,
        invalid_json_records,
        invalid_contract_records,
        duplicate_records,
        excluded_late_records,
        metrics,
    )


def load_late_event_ids(lines: Iterable[str]) -> set[str]:
    event_ids: set[str] = set()
    for line_number, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        document = _parse_json_line(raw_line, line_number, "late events")
        if not isinstance(document, dict):
            raise ReconciliationInputError(
                f"late events line {line_number} must be a JSON object"
            )
        event_id = document.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise ReconciliationInputError(
                f"late events line {line_number} event_id must be non-empty text"
            )
        event_ids.add(event_id)
    return event_ids


def load_metric_rows(lines: Iterable[str]) -> tuple[MinuteMetric, ...]:
    metrics: list[MinuteMetric] = []
    seen_keys: set[MetricKey] = set()
    for line_number, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        document = _parse_json_line(raw_line, line_number, "actual metrics")
        if not isinstance(document, dict):
            raise ReconciliationInputError(
                f"actual metrics line {line_number} must be a JSON object"
            )
        window_start = _parse_utc(document.get("window_start"), "window_start", line_number)
        window_end = _parse_utc(document.get("window_end"), "window_end", line_number)
        if window_start.second != 0 or window_start.microsecond != 0:
            raise ReconciliationInputError(
                f"actual metrics line {line_number} window_start must be minute-aligned"
            )
        if window_end != window_start + timedelta(minutes=1):
            raise ReconciliationInputError(
                f"actual metrics line {line_number} window must be exactly one minute"
            )
        region = document.get("region")
        channel = document.get("channel")
        if region not in REGIONS:
            raise ReconciliationInputError(
                f"actual metrics line {line_number} region is not supported"
            )
        if channel not in CHANNELS:
            raise ReconciliationInputError(
                f"actual metrics line {line_number} channel is not supported"
            )
        metric = MinuteMetric(
            window_start,
            window_end,
            region,
            channel,
            _parse_non_negative_int(document.get("order_count"), "order_count", line_number),
            _parse_money(document.get("gmv"), line_number),
        )
        if metric.key in seen_keys:
            raise ReconciliationInputError(
                f"actual metrics line {line_number} duplicates an earlier metric key"
            )
        seen_keys.add(metric.key)
        metrics.append(metric)
    return tuple(sorted(metrics, key=lambda metric: metric.key))


def reconcile_metrics(
    baseline: BatchBaseline,
    actual_metrics: Iterable[MinuteMetric],
    *,
    generated_at: datetime | None = None,
    events_input: str,
    actual_input: str,
) -> ReconciliationReport:
    timestamp = generated_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ValueError("generated_at must include timezone information")

    expected_by_key = {metric.key: metric for metric in baseline.metrics}
    actual_by_key: dict[MetricKey, MinuteMetric] = {}
    for metric in actual_metrics:
        if metric.key in actual_by_key:
            raise ReconciliationInputError("actual metrics contain a duplicate metric key")
        actual_by_key[metric.key] = metric

    differences: list[MetricDifference] = []
    matched = 0
    for key in sorted(expected_by_key.keys() | actual_by_key.keys()):
        expected = expected_by_key.get(key)
        actual = actual_by_key.get(key)
        if expected is None:
            differences.append(
                MetricDifference(
                    key,
                    "unexpected_actual",
                    None,
                    actual.order_count,
                    None,
                    actual.gmv,
                )
            )
            continue
        if actual is None:
            differences.append(
                MetricDifference(
                    key,
                    "missing_actual",
                    expected.order_count,
                    None,
                    expected.gmv,
                    None,
                )
            )
            continue
        count_mismatch = expected.order_count != actual.order_count
        gmv_mismatch = expected.gmv != actual.gmv
        if not count_mismatch and not gmv_mismatch:
            matched += 1
            continue
        if count_mismatch and gmv_mismatch:
            difference_status = "order_count_and_gmv_mismatch"
        elif count_mismatch:
            difference_status = "order_count_mismatch"
        else:
            difference_status = "gmv_mismatch"
        differences.append(
            MetricDifference(
                key,
                difference_status,
                expected.order_count,
                actual.order_count,
                expected.gmv,
                actual.gmv,
            )
        )

    return ReconciliationReport(
        timestamp.astimezone(UTC),
        events_input,
        actual_input,
        baseline,
        len(actual_by_key),
        matched,
        tuple(differences),
    )
