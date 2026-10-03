from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

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


app = create_app(PreviewMetricsRepository(), data_mode="preview")
