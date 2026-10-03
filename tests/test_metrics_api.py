from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any
import unittest

from fastapi.testclient import TestClient

from metrics_api.app import create_app
from metrics_api.repository import MetricsRepositoryError


class FakeRepository:
    def __init__(self) -> None:
        self.minute_rows: list[dict[str, Any]] = []
        self.summary_row: dict[str, Any] = {
            "order_count": 0,
            "gmv": "0.00",
            "average_order_value": "0.00",
            "latest_processed_at": None,
        }
        self.last_minute_query: dict[str, Any] | None = None
        self.last_summary_query: dict[str, Any] | None = None
        self.error: MetricsRepositoryError | None = None

    def ping(self) -> None:
        if self.error:
            raise self.error

    def fetch_minutes(self, **query: Any) -> list[dict[str, Any]]:
        if self.error:
            raise self.error
        self.last_minute_query = query
        return self.minute_rows

    def fetch_summary(self, **query: Any) -> dict[str, Any]:
        if self.error:
            raise self.error
        self.last_summary_query = query
        return self.summary_row


class MetricsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FakeRepository()
        self.client = TestClient(create_app(self.repository))

    def tearDown(self) -> None:
        self.client.close()

    def test_health_checks_the_analytics_store(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {"status": "ok", "clickhouse": "reachable"},
            response.json(),
        )

    def test_minute_metrics_passes_validated_filters_and_returns_rows(self) -> None:
        self.repository.minute_rows = [
            {
                "window_start": "2026-10-03 08:00:00.000",
                "window_end": "2026-10-03 08:01:00.000",
                "region": "辽宁",
                "channel": "app",
                "order_count": 3,
                "gmv": "199.90",
                "average_order_value": "66.63",
                "version": 7,
                "processed_at": "2026-10-03 08:01:02.000",
            }
        ]

        response = self.client.get(
            "/api/v1/metrics/minutes",
            params={
                "start": "2026-10-03T08:00:00+08:00",
                "end": "2026-10-03T09:00:00+08:00",
                "region": "辽宁",
                "channel": "app",
                "limit": 25,
            },
        )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(1, body["count"])
        self.assertEqual("199.90", body["items"][0]["gmv"])
        self.assertEqual(25, body["limit"])
        self.assertEqual("辽宁", self.repository.last_minute_query["region"])
        self.assertEqual("app", self.repository.last_minute_query["channel"])
        self.assertEqual(
            datetime(2026, 10, 3, 0, 0, tzinfo=UTC),
            self.repository.last_minute_query["start"],
        )

    def test_empty_summary_has_an_explicit_no_data_state(self) -> None:
        response = self.client.get(
            "/api/v1/metrics/summary",
            params={
                "start": "2026-10-01T00:00:00Z",
                "end": "2026-10-02T00:00:00Z",
            },
        )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertFalse(body["has_data"])
        self.assertEqual(0, body["order_count"])
        self.assertEqual("0.00", body["gmv"])
        self.assertIsNone(body["latest_processed_at"])

    def test_invalid_or_excessive_time_ranges_are_rejected(self) -> None:
        reversed_response = self.client.get(
            "/api/v1/metrics/minutes",
            params={
                "start": "2026-10-02T00:00:00Z",
                "end": "2026-10-01T00:00:00Z",
            },
        )
        excessive_response = self.client.get(
            "/api/v1/metrics/summary",
            params={
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-03-01T00:00:00Z",
            },
        )

        self.assertEqual(422, reversed_response.status_code)
        self.assertIn("earlier", reversed_response.json()["detail"])
        self.assertEqual(422, excessive_response.status_code)
        self.assertIn("31 days", excessive_response.json()["detail"])

    def test_limit_and_dimension_validation_are_exposed_by_fastapi(self) -> None:
        response = self.client.get(
            "/api/v1/metrics/minutes",
            params={"limit": 501, "region": ""},
        )

        self.assertEqual(422, response.status_code)
        self.assertGreaterEqual(len(response.json()["detail"]), 2)

    def test_repository_failures_use_a_stable_public_error(self) -> None:
        self.repository.error = MetricsRepositoryError("internal database detail")

        response = self.client.get("/health")

        self.assertEqual(503, response.status_code)
        self.assertEqual(
            {
                "detail": {
                    "code": "analytics_store_unavailable",
                    "message": "The analytics store is temporarily unavailable.",
                }
            },
            response.json(),
        )
        self.assertNotIn("internal database detail", response.text)

    def test_openapi_describes_both_metric_endpoints(self) -> None:
        document = self.client.get("/openapi.json").json()

        self.assertIn("/api/v1/metrics/minutes", document["paths"])
        self.assertIn("/api/v1/metrics/summary", document["paths"])
        self.assertIn("MinuteMetricsResponse", document["components"]["schemas"])


if __name__ == "__main__":
    unittest.main()
