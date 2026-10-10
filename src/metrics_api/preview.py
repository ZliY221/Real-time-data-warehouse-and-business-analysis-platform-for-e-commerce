from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from data_quality.history import StoredRuleResult, StoredRun
from metrics_api.app import create_app


class PreviewMetricsRepository:
    """Deterministic in-memory metrics for UI preview only."""

    REGIONS = ("辽宁", "北京", "上海", "广东")
    CHANNELS = ("app", "mini_program", "web")
    BUCKET_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}

    def __init__(self, now: datetime | None = None) -> None:
        self.now = (now or datetime.now(UTC)).replace(second=0, microsecond=0)
        self.rows = self._generate_rows()

    def _generate_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for interval in range(288):
            window_start = self.now - timedelta(minutes=5 * (287 - interval))
            for region_index, region in enumerate(self.REGIONS):
                for channel_index, channel in enumerate(self.CHANNELS):
                    order_count = 2 + (interval * 3 + region_index * 5 + channel_index * 7) % 9
                    unit_amount = Decimal("72.50") + Decimal(
                        (region_index * 11 + channel_index * 17 + interval % 13) * 3
                    )
                    rows.append(
                        {
                            "window_start": window_start,
                            "window_end": window_start + timedelta(minutes=5),
                            "region": region,
                            "channel": channel,
                            "order_count": order_count,
                            "gmv": unit_amount * order_count,
                            "version": interval + 1,
                            "processed_at": self.now - timedelta(seconds=18),
                        }
                    )
        return rows

    def ping(self) -> None:
        return None

    def _filtered(
        self,
        *,
        start: datetime,
        end: datetime,
        region: str | None,
        channel: str | None,
        **unused: Any,
    ) -> list[dict[str, Any]]:
        del unused
        return [
            row
            for row in self.rows
            if start <= row["window_start"] < end
            and (region is None or row["region"] == region)
            and (channel is None or row["channel"] == channel)
        ]

    @staticmethod
    def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        order_count = sum(row["order_count"] for row in rows)
        gmv = sum((row["gmv"] for row in rows), Decimal("0.00"))
        average = gmv / order_count if order_count else Decimal("0.00")
        return {
            "order_count": order_count,
            "gmv": f"{gmv:.2f}",
            "average_order_value": f"{average:.2f}",
        }

    def fetch_summary(self, **query: Any) -> dict[str, Any]:
        rows = self._filtered(**query)
        summary = self._summary(rows)
        summary["latest_processed_at"] = (
            max(row["processed_at"] for row in rows).isoformat() if rows else None
        )
        return summary

    def fetch_minutes(self, *, limit: int, **query: Any) -> list[dict[str, Any]]:
        rows = sorted(
            self._filtered(**query),
            key=lambda row: (row["window_start"], row["region"], row["channel"]),
            reverse=True,
        )[:limit]
        return [
            {
                **row,
                "window_start": row["window_start"].isoformat(),
                "window_end": row["window_end"].isoformat(),
                "gmv": f"{row['gmv']:.2f}",
                "average_order_value": f"{row['gmv'] / row['order_count']:.2f}",
                "processed_at": row["processed_at"].isoformat(),
            }
            for row in rows
        ]

    def fetch_time_series(self, *, bucket: str, **query: Any) -> list[dict[str, Any]]:
        minutes = self.BUCKET_MINUTES[bucket]
        grouped: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
        for row in self._filtered(**query):
            minute = (row["window_start"].minute // minutes) * minutes
            bucket_start = row["window_start"].replace(minute=minute)
            grouped[bucket_start].append(row)
        return [
            {"bucket_start": bucket_start.isoformat(), **self._summary(rows)}
            for bucket_start, rows in sorted(grouped.items())
        ]

    def fetch_breakdown(
        self,
        *,
        dimension: str,
        limit: int,
        **query: Any,
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in self._filtered(**query):
            grouped[row[dimension]].append(row)
        items = [{"name": name, **self._summary(rows)} for name, rows in grouped.items()]
        return sorted(items, key=lambda item: Decimal(item["gmv"]), reverse=True)[:limit]


class PreviewQualityHistory:
    """Deterministic quality-history sample for the ecommerce preview."""

    def __init__(self, now: datetime | None = None) -> None:
        self.now = (now or datetime.now(UTC)).replace(second=0, microsecond=0)
        observed_values = (0.08, 0.12, 0.16, 0.11, 0.19, 0.23, 0.57, 0.18)
        self.runs: list[StoredRun] = []
        self.trend: list[StoredRuleResult] = []
        for index, observed_value in enumerate(observed_values):
            generated_at = self.now - timedelta(hours=7 - index)
            passed = observed_value <= 0.35
            run_id = f"preview-quality-{index + 1:02d}"
            self.runs.append(
                StoredRun(
                    run_id=run_id,
                    generated_at=generated_at.isoformat(),
                    input_file="data/sample/order_events.ndjson",
                    passed=passed,
                    total_records=120 + index * 8,
                    parsed_records=120 + index * 8,
                    invalid_json_records=0,
                    invalid_contract_records=0,
                    duplicate_records=1 if index == 6 else 0,
                    late_records=2 if index == 6 else index % 2,
                    passed_rules=5 if index == 6 else 6,
                    failed_rules=1 if index == 6 else 0,
                )
            )
            self.trend.append(
                StoredRuleResult(
                    run_id=run_id,
                    generated_at=generated_at.isoformat(),
                    rule_id="channel-share-drift",
                    rule_type="distribution",
                    passed=passed,
                    checked_records=120 + index * 8,
                    violations=1 if index == 6 else 0,
                    metric_name="max_channel_share_drift",
                    observed_value=observed_value,
                    threshold=0.35,
                    message=(
                        "channel share drift is within threshold"
                        if passed
                        else "channel share drift exceeds threshold"
                    ),
                    samples=(),
                    metrics={"observed_share_drift": observed_value},
                )
            )

    @staticmethod
    def _check_limit(limit: int) -> None:
        if isinstance(limit, bool) or not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")

    def list_runs(
        self,
        *,
        limit: int = 50,
        passed: bool | None = None,
    ) -> list[StoredRun]:
        self._check_limit(limit)
        rows = [row for row in self.runs if passed is None or row.passed is passed]
        return list(reversed(rows))[:limit]

    def rule_trend(
        self,
        rule_id: str,
        *,
        limit: int = 50,
    ) -> list[StoredRuleResult]:
        self._check_limit(limit)
        if not rule_id.strip():
            raise ValueError("rule_id must not be blank")
        rows = [row for row in self.trend if row.rule_id == rule_id]
        return rows[-limit:]


app = create_app(
    PreviewMetricsRepository(),
    quality_history=PreviewQualityHistory(),
    data_mode="preview",
)
