from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal


def utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def money_text(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.2f}"


@dataclass(frozen=True, order=True)
class MetricKey:
    window_start: datetime
    region: str
    channel: str


@dataclass(frozen=True)
class MinuteMetric:
    window_start: datetime
    window_end: datetime
    region: str
    channel: str
    order_count: int
    gmv: Decimal

    @property
    def key(self) -> MetricKey:
        return MetricKey(self.window_start, self.region, self.channel)

    def to_dict(self) -> dict[str, object]:
        return {
            "window_start": utc_text(self.window_start),
            "window_end": utc_text(self.window_end),
            "region": self.region,
            "channel": self.channel,
            "order_count": self.order_count,
            "gmv": money_text(self.gmv),
        }


@dataclass(frozen=True)
class BatchBaseline:
    total_records: int
    parsed_records: int
    invalid_json_records: int
    invalid_contract_records: int
    duplicate_records: int
    excluded_late_records: int
    metrics: tuple[MinuteMetric, ...]

    @property
    def accepted_records(self) -> int:
        return sum(metric.order_count for metric in self.metrics)

    def summary_dict(self) -> dict[str, int]:
        return {
            "total_records": self.total_records,
            "parsed_records": self.parsed_records,
            "invalid_json_records": self.invalid_json_records,
            "invalid_contract_records": self.invalid_contract_records,
            "duplicate_records": self.duplicate_records,
            "excluded_late_records": self.excluded_late_records,
            "accepted_records": self.accepted_records,
            "metric_keys": len(self.metrics),
        }


DifferenceStatus = Literal[
    "missing_actual",
    "unexpected_actual",
    "order_count_mismatch",
    "gmv_mismatch",
    "order_count_and_gmv_mismatch",
]


@dataclass(frozen=True)
class MetricDifference:
    key: MetricKey
    status: DifferenceStatus
    expected_order_count: int | None
    actual_order_count: int | None
    expected_gmv: Decimal | None
    actual_gmv: Decimal | None

    def to_dict(self) -> dict[str, object]:
        return {
            "window_start": utc_text(self.key.window_start),
            "region": self.key.region,
            "channel": self.key.channel,
            "status": self.status,
            "expected_order_count": self.expected_order_count,
            "actual_order_count": self.actual_order_count,
            "expected_gmv": money_text(self.expected_gmv),
            "actual_gmv": money_text(self.actual_gmv),
        }


@dataclass(frozen=True)
class ReconciliationReport:
    generated_at: datetime
    events_input: str
    actual_input: str
    baseline: BatchBaseline
    actual_metric_keys: int
    matched_metric_keys: int
    differences: tuple[MetricDifference, ...]

    @property
    def passed(self) -> bool:
        return not self.differences

    def to_dict(self) -> dict[str, object]:
        return {
            "report_version": "1.0",
            "generated_at": utc_text(self.generated_at),
            "inputs": {
                "events": Path(self.events_input).as_posix(),
                "actual_metrics": Path(self.actual_input).as_posix(),
            },
            "baseline": self.baseline.summary_dict(),
            "summary": {
                "passed": self.passed,
                "expected_metric_keys": len(self.baseline.metrics),
                "actual_metric_keys": self.actual_metric_keys,
                "matched_metric_keys": self.matched_metric_keys,
                "mismatched_metric_keys": len(self.differences),
            },
            "differences": [difference.to_dict() for difference in self.differences],
        }

    def to_markdown(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [
            "# Batch/stream metric reconciliation",
            "",
            f"- Status: **{status}**",
            f"- Events: `{Path(self.events_input).as_posix()}`",
            f"- Actual metrics: `{Path(self.actual_input).as_posix()}`",
            f"- Generated at: `{utc_text(self.generated_at)}`",
            f"- Accepted events: {self.baseline.accepted_records}",
            f"- Metric keys: {len(self.baseline.metrics)} expected, "
            f"{self.actual_metric_keys} actual, {self.matched_metric_keys} matched",
        ]
        if self.differences:
            lines.extend(
                [
                    "",
                    "## Differences",
                    "",
                    "| Window | Region | Channel | Status | Expected count | "
                    "Actual count | Expected GMV | Actual GMV |",
                    "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
                ]
            )
            for item in self.differences:
                expected_count = (
                    item.expected_order_count
                    if item.expected_order_count is not None
                    else "-"
                )
                actual_count = (
                    item.actual_order_count if item.actual_order_count is not None else "-"
                )
                lines.append(
                    f"| {utc_text(item.key.window_start)} | {item.key.region} | "
                    f"{item.key.channel} | {item.status} | "
                    f"{expected_count} | {actual_count} | "
                    f"{money_text(item.expected_gmv) or '-'} | "
                    f"{money_text(item.actual_gmv) or '-'} |"
                )
        return "\n".join(lines).rstrip() + "\n"
