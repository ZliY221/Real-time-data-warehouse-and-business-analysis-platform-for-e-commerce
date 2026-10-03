from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any
import unittest
from urllib.parse import parse_qs, urlparse

from metrics_api.config import ApiSettings
from metrics_api.repository import ClickHouseHttpRepository, MetricsRepositoryError


class FakeResponse:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._payload = "".join(f"{json.dumps(row)}\n" for row in rows).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


class RecordingOpener:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.request: Any = None
        self.timeout: float | None = None

    def __call__(self, request: Any, *, timeout: float) -> FakeResponse:
        self.request = request
        self.timeout = timeout
        return FakeResponse(self.rows)


class ClickHouseHttpRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = ApiSettings(
            clickhouse_url="http://clickhouse.example:8123",
            clickhouse_user="reporter",
            clickhouse_password="secret",
            clickhouse_database="ecommerce",
            clickhouse_timeout_seconds=2.5,
        )

    def test_minute_query_uses_typed_parameters_instead_of_interpolation(self) -> None:
        opener = RecordingOpener([])
        repository = ClickHouseHttpRepository(self.settings, opener=opener)
        suspicious_region = "辽宁' OR 1=1 --"

        repository.fetch_minutes(
            start=datetime(2026, 10, 1, tzinfo=UTC),
            end=datetime(2026, 10, 2, tzinfo=UTC),
            region=suspicious_region,
            channel="app",
            limit=50,
        )

        sql = opener.request.data.decode("utf-8")
        parameters = parse_qs(urlparse(opener.request.full_url).query)
        self.assertIn("region = {region:String}", sql)
        self.assertIn("LIMIT {limit:UInt32}", sql)
        self.assertNotIn(suspicious_region, sql)
        self.assertEqual([suspicious_region], parameters["param_region"])
        self.assertEqual(["50"], parameters["param_limit"])
        self.assertEqual(["ecommerce"], parameters["database"])
        self.assertEqual(2.5, opener.timeout)
        self.assertTrue(opener.request.headers["Authorization"].startswith("Basic "))

    def test_summary_parses_exact_money_strings(self) -> None:
        opener = RecordingOpener(
            [
                {
                    "order_count": 4,
                    "gmv": "123.40",
                    "average_order_value": "30.85",
                    "latest_processed_at": "2026-10-01 00:01:01.000",
                }
            ]
        )
        repository = ClickHouseHttpRepository(self.settings, opener=opener)

        row = repository.fetch_summary(
            start=datetime(2026, 10, 1, tzinfo=UTC),
            end=datetime(2026, 10, 2, tzinfo=UTC),
            region=None,
            channel=None,
        )

        self.assertEqual("123.40", row["gmv"])
        self.assertEqual("30.85", row["average_order_value"])

    def test_invalid_json_is_reported_as_repository_failure(self) -> None:
        class InvalidJsonResponse(FakeResponse):
            def __init__(self) -> None:
                self._payload = b"not-json\n"

        def opener(request: Any, *, timeout: float) -> InvalidJsonResponse:
            del request, timeout
            return InvalidJsonResponse()

        repository = ClickHouseHttpRepository(self.settings, opener=opener)

        with self.assertRaisesRegex(MetricsRepositoryError, "invalid JSONEachRow"):
            repository.ping()

    def test_time_series_bucket_is_selected_from_a_fixed_sql_allowlist(self) -> None:
        opener = RecordingOpener([])
        repository = ClickHouseHttpRepository(self.settings, opener=opener)

        repository.fetch_time_series(
            start=datetime(2026, 10, 1, tzinfo=UTC),
            end=datetime(2026, 10, 2, tzinfo=UTC),
            region=None,
            channel=None,
            bucket="15m",
        )

        sql = opener.request.data.decode("utf-8")
        self.assertIn("INTERVAL 15 MINUTE", sql)
        self.assertIn("GROUP BY bucket_start", sql)
        with self.assertRaisesRegex(ValueError, "Unsupported time bucket"):
            repository.fetch_time_series(
                start=datetime(2026, 10, 1, tzinfo=UTC),
                end=datetime(2026, 10, 2, tzinfo=UTC),
                region=None,
                channel=None,
                bucket="1m); DROP TABLE minute_metrics; --",
            )

    def test_breakdown_dimension_is_selected_from_a_fixed_sql_allowlist(self) -> None:
        opener = RecordingOpener([])
        repository = ClickHouseHttpRepository(self.settings, opener=opener)

        repository.fetch_breakdown(
            start=datetime(2026, 10, 1, tzinfo=UTC),
            end=datetime(2026, 10, 2, tzinfo=UTC),
            region=None,
            channel=None,
            dimension="channel",
            limit=12,
        )

        sql = opener.request.data.decode("utf-8")
        query = parse_qs(urlparse(opener.request.full_url).query)
        self.assertIn("channel AS name", sql)
        self.assertIn("LIMIT {limit:UInt32}", sql)
        self.assertEqual(["12"], query["param_limit"])
        with self.assertRaisesRegex(ValueError, "Unsupported breakdown dimension"):
            repository.fetch_breakdown(
                start=datetime(2026, 10, 1, tzinfo=UTC),
                end=datetime(2026, 10, 2, tzinfo=UTC),
                region=None,
                channel=None,
                dimension="gmv) FROM system.users --",
                limit=12,
            )

    def test_settings_reject_credentials_embedded_in_url(self) -> None:
        settings = ApiSettings(clickhouse_url="http://user:secret@localhost:8123")

        with self.assertRaisesRegex(ValueError, "environment variables"):
            settings.validate()


if __name__ == "__main__":
    unittest.main()
