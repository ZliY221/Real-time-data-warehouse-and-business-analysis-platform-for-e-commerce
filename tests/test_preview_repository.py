from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import unittest

from fastapi.testclient import TestClient

from metrics_api.app import create_app
from metrics_api.preview import PreviewMetricsRepository, PreviewQualityHistory


class PreviewMetricsRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 10, 3, 8, 0, tzinfo=UTC)
        self.repository = PreviewMetricsRepository(self.now)
        self.query = {
            "start": self.now - timedelta(hours=6),
            "end": self.now + timedelta(minutes=1),
            "region": None,
            "channel": None,
        }

    def test_preview_data_is_repeatable_for_an_injected_clock(self) -> None:
        other = PreviewMetricsRepository(self.now)

        self.assertEqual(self.repository.rows, other.rows)
        self.assertEqual(288 * 4 * 3, len(self.repository.rows))

    def test_filters_change_summary_without_using_external_services(self) -> None:
        overall = self.repository.fetch_summary(**self.query)
        region = self.repository.fetch_summary(**{**self.query, "region": "辽宁"})

        self.assertGreater(overall["order_count"], region["order_count"])
        self.assertGreater(Decimal(overall["gmv"]), Decimal(region["gmv"]))
        self.assertIsNotNone(overall["latest_processed_at"])

    def test_time_series_and_breakdown_are_sorted_for_dashboard_use(self) -> None:
        series = self.repository.fetch_time_series(bucket="15m", **self.query)
        breakdown = self.repository.fetch_breakdown(
            dimension="channel",
            limit=12,
            **self.query,
        )

        self.assertGreater(len(series), 1)
        self.assertEqual(
            sorted(item["bucket_start"] for item in series),
            [item["bucket_start"] for item in series],
        )
        gmv_values = [Decimal(item["gmv"]) for item in breakdown]
        self.assertEqual(sorted(gmv_values, reverse=True), gmv_values)

    def test_preview_app_identifies_in_memory_data_source(self) -> None:
        quality_history = PreviewQualityHistory(self.now)
        with TestClient(
            create_app(
                self.repository,
                quality_history=quality_history,
                data_mode="preview",
            )
        ) as client:
            response = client.get("/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {
                "status": "ok",
                "data_source": "preview",
                "analytics_store": "in_memory",
            },
            response.json(),
        )
        self.assertEqual("preview", response.headers["x-data-mode"])

    def test_preview_quality_history_contains_a_visible_failure_and_recovery(self) -> None:
        history = PreviewQualityHistory(self.now)

        runs = history.list_runs(limit=20)
        trend = history.rule_trend("channel-share-drift", limit=20)

        self.assertEqual(8, len(runs))
        self.assertTrue(runs[0].passed)
        self.assertTrue(any(not run.passed for run in runs))
        self.assertGreater(max(point.observed_value for point in trend), 0.35)
        self.assertTrue(trend[-1].passed)

    def test_preview_app_serves_quality_endpoints_without_sqlite(self) -> None:
        with TestClient(
            create_app(
                self.repository,
                quality_history=PreviewQualityHistory(self.now),
                data_mode="preview",
            )
        ) as client:
            runs_response = client.get("/api/v1/quality/runs")
            trend_response = client.get(
                "/api/v1/quality/trend",
                params={"rule_id": "channel-share-drift"},
            )

        self.assertEqual(200, runs_response.status_code)
        self.assertEqual(8, runs_response.json()["count"])
        self.assertEqual(200, trend_response.status_code)
        self.assertEqual(8, trend_response.json()["count"])
        self.assertEqual("preview", trend_response.headers["x-data-mode"])


if __name__ == "__main__":
    unittest.main()
