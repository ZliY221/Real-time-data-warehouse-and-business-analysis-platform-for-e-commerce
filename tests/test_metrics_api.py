from __future__ import annotations

from datetime import UTC, datetime
import json
import sqlite3
from typing import Any
import unittest

from fastapi.testclient import TestClient

from data_quality.history import StoredRuleResult, StoredRun
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
        self.summary_rows: list[dict[str, Any]] = []
        self.time_series_rows: list[dict[str, Any]] = []
        self.breakdown_rows: list[dict[str, Any]] = []
        self.anomaly_rows: list[dict[str, Any]] = []
        self.product_rows: list[dict[str, Any]] = []
        self.last_minute_query: dict[str, Any] | None = None
        self.last_summary_query: dict[str, Any] | None = None
        self.last_time_series_query: dict[str, Any] | None = None
        self.last_breakdown_query: dict[str, Any] | None = None
        self.last_anomaly_query: dict[str, Any] | None = None
        self.last_product_query: dict[str, Any] | None = None
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
        return self.summary_rows.pop(0) if self.summary_rows else self.summary_row

    def fetch_time_series(self, **query: Any) -> list[dict[str, Any]]:
        if self.error:
            raise self.error
        self.last_time_series_query = query
        return self.time_series_rows

    def fetch_breakdown(self, **query: Any) -> list[dict[str, Any]]:
        if self.error:
            raise self.error
        self.last_breakdown_query = query
        return self.breakdown_rows

    def fetch_anomaly_summary(self, **query: Any) -> list[dict[str, Any]]:
        if self.error:
            raise self.error
        self.last_anomaly_query = query
        return self.anomaly_rows

    def fetch_product_breakdown(self, **query: Any) -> list[dict[str, Any]]:
        if self.error:
            raise self.error
        self.last_product_query = query
        return self.product_rows


class FakeQualityHistory:
    def __init__(self) -> None:
        self.runs = [
            StoredRun(
                run_id="quality-pass",
                generated_at="2026-10-03T08:00:00Z",
                input_file="data/sample/order_events.ndjson",
                passed=True,
                total_records=12,
                parsed_records=12,
                invalid_json_records=0,
                invalid_contract_records=0,
                duplicate_records=0,
                late_records=0,
                passed_rules=6,
                failed_rules=0,
            ),
            StoredRun(
                run_id="quality-fail",
                generated_at="2026-10-03T09:00:00Z",
                input_file="C:/private/workspace/data/quality/issues.ndjson",
                passed=False,
                total_records=10,
                parsed_records=9,
                invalid_json_records=1,
                invalid_contract_records=2,
                duplicate_records=1,
                late_records=3,
                passed_rules=2,
                failed_rules=4,
            ),
        ]
        self.trend = [
            StoredRuleResult(
                run_id="quality-pass",
                generated_at="2026-10-03T08:00:00Z",
                rule_id="channel-share-drift",
                rule_type="distribution",
                passed=True,
                checked_records=12,
                violations=0,
                metric_name="max_channel_share_drift",
                observed_value=0.12,
                threshold=0.35,
                message="within threshold",
                samples=(),
                metrics={},
            ),
            StoredRuleResult(
                run_id="quality-fail",
                generated_at="2026-10-03T09:00:00Z",
                rule_id="channel-share-drift",
                rule_type="distribution",
                passed=False,
                checked_records=9,
                violations=1,
                metric_name="max_channel_share_drift",
                observed_value=0.62,
                threshold=0.35,
                message="threshold exceeded",
                samples=(),
                metrics={},
            ),
        ]
        self.error: sqlite3.Error | None = None
        self.last_runs_query: dict[str, Any] | None = None
        self.last_trend_query: dict[str, Any] | None = None

    def list_runs(self, *, limit: int, passed: bool | None = None) -> list[StoredRun]:
        if self.error:
            raise self.error
        self.last_runs_query = {"limit": limit, "passed": passed}
        rows = [row for row in reversed(self.runs) if passed is None or row.passed is passed]
        return rows[:limit]

    def rule_trend(self, rule_id: str, *, limit: int) -> list[StoredRuleResult]:
        if self.error:
            raise self.error
        self.last_trend_query = {"rule_id": rule_id, "limit": limit}
        return [row for row in self.trend if row.rule_id == rule_id][-limit:]


class MetricsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FakeRepository()
        self.quality_history = FakeQualityHistory()
        self.client = TestClient(
            create_app(self.repository, quality_history=self.quality_history)
        )

    def tearDown(self) -> None:
        self.client.close()

    def test_health_checks_the_analytics_store(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {
                "status": "ok",
                "data_source": "clickhouse",
                "analytics_store": "reachable",
            },
            response.json(),
        )
        self.assertEqual("clickhouse", response.headers["x-data-mode"])

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
        self.assertTrue(body["items"][0]["window_start"].endswith("Z"))
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

    def test_comparison_reports_exact_deltas_and_growth_rates(self) -> None:
        self.repository.summary_rows = [
            {"order_count": 120, "gmv": "1500.50", "average_order_value": "12.50", "latest_processed_at": "2026-10-15T02:00:00Z"},
            {"order_count": 100, "gmv": "1200.25", "average_order_value": "12.00", "latest_processed_at": "2026-10-14T02:00:00Z"},
        ]
        response = self.client.get("/api/v1/metrics/comparison", params={
            "start": "2026-10-15T00:00:00Z", "end": "2026-10-15T02:00:00Z",
            "baseline_start": "2026-10-14T00:00:00Z", "baseline_end": "2026-10-14T02:00:00Z",
            "region": "辽宁", "channel": "app",
        })
        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(20, body["delta"]["order_count"])
        self.assertEqual("300.25", body["delta"]["gmv"])
        self.assertEqual(0.2, body["delta"]["order_count_rate"])
        self.assertEqual(0.250156, body["delta"]["gmv_rate"])
        self.assertEqual("辽宁", body["current"]["filters"]["region"])

    def test_comparison_rejects_unequal_ranges_and_handles_zero_baseline(self) -> None:
        invalid = self.client.get("/api/v1/metrics/comparison", params={
            "start": "2026-10-15T00:00:00Z", "end": "2026-10-15T02:00:00Z",
            "baseline_start": "2026-10-14T00:00:00Z", "baseline_end": "2026-10-14T01:00:00Z",
        })
        self.assertEqual(422, invalid.status_code)
        self.repository.summary_rows = [
            {"order_count": 1, "gmv": "10.00", "average_order_value": "10.00", "latest_processed_at": None},
            {"order_count": 0, "gmv": "0.00", "average_order_value": "0.00", "latest_processed_at": None},
        ]
        valid = self.client.get("/api/v1/metrics/comparison", params={
            "start": "2026-10-15T00:00:00Z", "end": "2026-10-15T01:00:00Z",
            "baseline_start": "2026-10-14T00:00:00Z", "baseline_end": "2026-10-14T01:00:00Z",
        })
        self.assertIsNone(valid.json()["delta"]["gmv_rate"])

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

    def test_time_series_selects_a_bounded_automatic_bucket(self) -> None:
        self.repository.time_series_rows = [
            {
                "bucket_start": "2026-10-03 00:00:00.000",
                "order_count": 8,
                "gmv": "520.00",
                "average_order_value": "65.00",
            }
        ]

        response = self.client.get(
            "/api/v1/metrics/timeseries",
            params={
                "start": "2026-10-02T00:00:00Z",
                "end": "2026-10-03T00:00:00Z",
                "bucket": "auto",
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("5m", response.json()["bucket"])
        self.assertEqual("5m", self.repository.last_time_series_query["bucket"])
        self.assertEqual("520.00", response.json()["items"][0]["gmv"])

    def test_overly_fine_explicit_time_bucket_is_rejected(self) -> None:
        response = self.client.get(
            "/api/v1/metrics/timeseries",
            params={
                "start": "2026-09-01T00:00:00Z",
                "end": "2026-10-01T00:00:00Z",
                "bucket": "1m",
            },
        )

        self.assertEqual(422, response.status_code)
        self.assertIn("coarser bucket", response.json()["detail"])
        self.assertIsNone(self.repository.last_time_series_query)

    def test_breakdown_uses_an_allowlisted_dimension(self) -> None:
        self.repository.breakdown_rows = [
            {
                "name": "辽宁",
                "order_count": 10,
                "gmv": "880.00",
                "average_order_value": "88.00",
            }
        ]

        response = self.client.get(
            "/api/v1/metrics/breakdown",
            params={"dimension": "region", "limit": 8},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("region", response.json()["dimension"])
        self.assertEqual("辽宁", response.json()["items"][0]["name"])
        self.assertEqual("region", self.repository.last_breakdown_query["dimension"])
        self.assertEqual(8, self.repository.last_breakdown_query["limit"])

    def test_unknown_breakdown_dimension_is_rejected_by_fastapi(self) -> None:
        response = self.client.get(
            "/api/v1/metrics/breakdown",
            params={"dimension": "gmv) FROM system.users --"},
        )

        self.assertEqual(422, response.status_code)
        self.assertIsNone(self.repository.last_breakdown_query)

    def test_product_breakdown_supports_category_and_sku_drilldown(self) -> None:
        self.repository.product_rows = [{
            "name": "sku-phone", "category": "digital", "order_count": 8,
            "unit_quantity": 11, "gmv": "2399.00", "average_unit_price": "218.09",
        }]
        response = self.client.get("/api/v1/products/breakdown", params={
            "start": "2026-10-03T00:00:00Z", "end": "2026-10-04T00:00:00Z",
            "dimension": "sku", "category": "digital", "limit": 10,
        })
        self.assertEqual(200, response.status_code)
        self.assertEqual("sku", response.json()["dimension"])
        self.assertEqual(11, response.json()["items"][0]["unit_quantity"])
        self.assertEqual("digital", self.repository.last_product_query["category"])
        self.assertEqual(10, self.repository.last_product_query["limit"])

    def test_quality_runs_are_newest_first_and_support_pass_filtering(self) -> None:
        response = self.client.get(
            "/api/v1/quality/runs",
            params={"limit": 7, "passed": "false"},
        )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(1, body["count"])
        self.assertFalse(body["passed"])
        self.assertEqual("quality-fail", body["items"][0]["run_id"])
        self.assertEqual(4, body["items"][0]["failed_rules"])
        self.assertEqual("issues.ndjson", body["items"][0]["input_file"])
        self.assertNotIn("private", response.text)
        self.assertEqual(
            {"limit": 7, "passed": False},
            self.quality_history.last_runs_query,
        )
        self.assertEqual("clickhouse", response.headers["x-data-mode"])

    def test_anomaly_summary_aggregates_counts_and_validates_type(self) -> None:
        self.repository.anomaly_rows = [
            {
                "anomaly_type": "rejected",
                "reason": "invalid_field",
                "anomaly_count": 3,
                "latest_at": "2026-10-03 08:05:00.000",
            },
            {
                "anomaly_type": "late",
                "reason": "window_late",
                "anomaly_count": 5,
                "latest_at": "2026-10-03 08:06:00.000",
            },
        ]

        response = self.client.get(
            "/api/v1/anomalies/summary",
            params={
                "start": "2026-10-03T08:00:00Z",
                "end": "2026-10-03T09:00:00Z",
                "limit": 10,
            },
        )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(8, body["total_count"])
        self.assertEqual(3, body["rejected_count"])
        self.assertEqual(5, body["late_count"])
        self.assertEqual(2, body["count"])
        self.assertTrue(body["items"][0]["latest_at"].endswith("Z"))
        self.assertEqual(10, self.repository.last_anomaly_query["limit"])

        invalid = self.client.get(
            "/api/v1/anomalies/summary",
            params={"anomaly_type": "unknown"},
        )
        self.assertEqual(422, invalid.status_code)

    def test_asset_freshness_exposes_lineage_impact(self) -> None:
        self.repository.summary_row = {
            "order_count": 12,
            "gmv": "800.00",
            "average_order_value": "66.67",
            "latest_processed_at": "2026-10-13T08:00:10Z",
        }
        response = self.client.get(
            "/api/v1/operations/assets/clickhouse.minute-metrics/freshness",
            params={"evaluated_at": "2026-10-13T08:02:15Z"},
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual("stale", response.json()["status"])
        self.assertEqual(125, response.json()["lag_seconds"])
        self.assertEqual(
            ["api.metrics", "dashboard.operations"],
            response.json()["impacted_assets"],
        )

    def test_asset_catalog_exposes_ownership_and_lineage(self) -> None:
        response = self.client.get("/api/v1/operations/assets")

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(5, body["asset_count"])
        self.assertEqual(1, body["source_count"])
        self.assertEqual(1, body["monitored_count"])
        clickhouse = next(
            item for item in body["items"]
            if item["asset_id"] == "clickhouse.minute-metrics"
        )
        self.assertEqual("realtime-warehouse", clickhouse["owner"])
        self.assertEqual(["flink.minute-metrics"], clickhouse["upstream_assets"])
        self.assertEqual(
            ["api.metrics", "dashboard.operations"],
            clickhouse["downstream_assets"],
        )

    def test_asset_health_rolls_up_monitored_assets_and_impact(self) -> None:
        self.repository.summary_row = {
            "order_count": 12,
            "gmv": "800.00",
            "average_order_value": "66.67",
            "latest_processed_at": "2026-10-13T08:00:10Z",
        }
        response = self.client.get(
            "/api/v1/operations/assets/health",
            params={"evaluated_at": "2026-10-13T08:02:15Z"},
        )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("stale", body["status"])
        self.assertEqual({"fresh": 0, "stale": 1, "no_data": 0}, body["status_counts"])
        self.assertEqual(["api.metrics", "dashboard.operations"], body["impacted_assets"])
        self.assertEqual("realtime-warehouse", body["items"][0]["owner"])
        self.assertEqual(1, body["priority_count"])
        self.assertEqual(1, body["items"][0]["priority_rank"])
        self.assertEqual(141, body["items"][0]["priority_score"])

    def test_asset_freshness_rejects_unknown_assets(self) -> None:
        response = self.client.get(
            "/api/v1/operations/assets/unknown/freshness"
        )
        self.assertEqual(404, response.status_code)
        self.assertEqual("asset_not_found", response.json()["detail"]["code"])

    def test_quality_trend_returns_only_dashboard_safe_metrics(self) -> None:
        response = self.client.get(
            "/api/v1/quality/trend",
            params={"rule_id": "channel-share-drift", "limit": 10},
        )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(2, body["count"])
        self.assertEqual(0.62, body["items"][1]["observed_value"])
        self.assertNotIn("samples", body["items"][1])
        self.assertNotIn("message", body["items"][1])
        self.assertEqual(
            {"rule_id": "channel-share-drift", "limit": 10},
            self.quality_history.last_trend_query,
        )

    def test_quality_endpoint_validation_is_bounded(self) -> None:
        missing_rule = self.client.get("/api/v1/quality/trend")
        excessive_limit = self.client.get(
            "/api/v1/quality/runs",
            params={"limit": 501},
        )

        self.assertEqual(422, missing_rule.status_code)
        self.assertEqual(422, excessive_limit.status_code)

    def test_quality_store_failures_use_a_stable_public_error(self) -> None:
        self.quality_history.error = sqlite3.OperationalError(
            "database path and internal table details"
        )

        response = self.client.get("/api/v1/quality/runs")

        self.assertEqual(503, response.status_code)
        self.assertEqual(
            {
                "detail": {
                    "code": "quality_history_unavailable",
                    "message": "The quality history is temporarily unavailable.",
                }
            },
            response.json(),
        )
        self.assertNotIn("database path", response.text)

    def test_openapi_describes_metric_and_quality_endpoints(self) -> None:
        document = self.client.get("/openapi.json").json()

        self.assertIn("/api/v1/metrics/minutes", document["paths"])
        self.assertIn("/api/v1/metrics/summary", document["paths"])
        self.assertIn("/api/v1/metrics/comparison", document["paths"])
        self.assertIn("/api/v1/metrics/timeseries", document["paths"])
        self.assertIn("/api/v1/metrics/breakdown", document["paths"])
        self.assertIn("/api/v1/quality/runs", document["paths"])
        self.assertIn("/api/v1/quality/trend", document["paths"])
        self.assertIn("/api/v1/anomalies/summary", document["paths"])
        self.assertIn(
            "/api/v1/operations/assets",
            document["paths"],
        )
        self.assertIn(
            "/api/v1/operations/assets/{asset_id}/freshness",
            document["paths"],
        )
        self.assertIn("MinuteMetricsResponse", document["components"]["schemas"])
        self.assertIn("QualityRunsResponse", document["components"]["schemas"])
        self.assertIn("AnomalySummaryResponse", document["components"]["schemas"])
        self.assertIn("MetricComparisonResponse", document["components"]["schemas"])
        self.assertIn("AssetFreshnessResponse", document["components"]["schemas"])
        self.assertIn("AssetCatalogResponse", document["components"]["schemas"])

    def test_dashboard_and_assets_are_served_with_security_headers(self) -> None:
        page = self.client.get("/dashboard")
        script = self.client.get("/dashboard/assets/app.js")

        self.assertEqual(200, page.status_code)
        self.assertIn("实时经营脉搏", page.text)
        self.assertIn("echarts@6.1.0", page.text)
        self.assertIn("default-src 'self'", page.headers["content-security-policy"])
        self.assertIn("https://cdn.jsdelivr.net", page.headers["content-security-policy"])
        self.assertEqual("nosniff", page.headers["x-content-type-options"])
        self.assertEqual(200, script.status_code)
        self.assertIn("refreshDashboard", script.text)
        self.assertIn("auto-refresh-interval", page.text)
        self.assertIn("setAutoRefresh", script.text)
        self.assertIn("live-refresh-toggle", page.text)
        self.assertIn("autoRefreshCountdown", script.text)

    def test_promotion_margin_guardrail_is_exposed(self) -> None:
        response = self.client.get("/api/v3/operations/promotion-margin", params={
            "selling_price": "100", "unit_cost": "62", "discount_rate": "0.30",
            "shipping_subsidy": "5", "expected_return_rate": "0.10",
            "minimum_margin_rate": "0.10",
        })
        self.assertEqual(200, response.status_code)
        self.assertEqual("BLOCKED", response.json()["status"])
        self.assertLess(response.json()["maximum_safe_discount_rate"], 0.30)

    def test_return_capacity_signal_is_exposed(self) -> None:
        response = self.client.get("/api/v3/operations/return-capacity", params={
            "orders": 1000, "return_requests": 200, "processed_returns": 20,
            "existing_backlog": 100, "handling_rate_per_hour": 20,
            "horizon_hours": 8,
        })
        self.assertEqual(200, response.status_code)
        self.assertEqual("SURGE_CAPACITY_GAP", response.json()["status"])
        self.assertEqual(120, response.json()["forecast_backlog"])

    def test_fulfillment_promise_signal_is_exposed(self) -> None:
        response = self.client.get("/api/v3/operations/fulfillment-promise", params={
            "orders_due_today": 500, "already_shipped": 100,
            "packing_backlog": 450, "packing_rate_per_hour": 100,
            "carrier_remaining_capacity": 250, "hours_to_cutoff": 0.5,
        })
        self.assertEqual(200, response.status_code)
        self.assertEqual("CUTOFF_RISK", response.json()["status"])
        self.assertEqual(350, response.json()["promise_shortfall"])

    def test_v4_fulfillment_allocation_is_exposed(self) -> None:
        response = self.client.post("/api/v4/operations/fulfillment-allocation", json={
            "order_count": 220,
            "nodes": [
                {"node": "north", "available_units": 200,
                 "packing_rate_per_hour": 100, "carrier_capacity": 150,
                 "hours_to_cutoff": 2},
                {"node": "south", "available_units": 100,
                 "packing_rate_per_hour": 30, "carrier_capacity": 80,
                 "hours_to_cutoff": 2},
            ],
        })
        self.assertEqual(200, response.status_code)
        self.assertEqual("PARTIAL", response.json()["status"])
        self.assertEqual(10, response.json()["unallocated_orders"])

    def test_v4_inventory_rebalancing_is_exposed(self) -> None:
        response = self.client.post("/api/v4/operations/inventory-rebalancing", json={
            "nodes": [
                {"node": "north", "available_units": 120, "forecast_demand": 40,
                 "safety_stock": 20, "outbound_transfer_capacity": 50,
                 "inbound_transfer_capacity": 0},
                {"node": "south", "available_units": 10, "forecast_demand": 50,
                 "safety_stock": 10, "outbound_transfer_capacity": 0,
                 "inbound_transfer_capacity": 30},
            ],
        })
        self.assertEqual(200, response.status_code)
        self.assertEqual("PARTIAL", response.json()["status"])
        self.assertEqual(30, response.json()["planned_transfer_units"])
        self.assertFalse(response.json()["transfer_started"])

    def test_v4_shipment_consolidation_is_exposed(self) -> None:
        response = self.client.post("/api/v4/operations/shipment-consolidation", json={
            "maximum_wait_minutes": 60,
            "orders": [
                {"order_id": "order-1", "total_items": 3, "available_items": 2,
                 "next_item_ready_minutes": 30, "carrier_cutoff_minutes": 180,
                 "packing_minutes": 20},
            ],
        })
        self.assertEqual(200, response.status_code)
        self.assertEqual("CONSOLIDATE", response.json()["orders"][0]["action"])
        self.assertEqual(1, response.json()["packages_avoided"])
        self.assertFalse(response.json()["shipment_changes_started"])

    def test_v4_packing_wave_plan_is_exposed(self) -> None:
        response = self.client.post("/api/v4/operations/packing-wave-plan", json={
            "station_count": 2,
            "orders": [
                {"order_id": "order-1", "packing_minutes": 30,
                 "cutoff_minutes": 20, "priority": 100},
                {"order_id": "order-2", "packing_minutes": 10,
                 "cutoff_minutes": 60, "priority": 50},
            ],
        })
        self.assertEqual(200, response.status_code)
        self.assertEqual("AT_RISK", response.json()["status"])
        self.assertEqual(1, response.json()["at_risk_order_count"])
        self.assertFalse(response.json()["packing_tasks_dispatched"])

    def test_v4_carrier_handoff_is_exposed(self) -> None:
        response = self.client.post("/api/v4/operations/carrier-handoff", json={
            "shipments": [
                {"shipment_id": "shipment-1", "ready_minute": 10,
                 "delivery_cutoff_minute": 60, "priority": 90},
            ],
            "slots": [
                {"slot_id": "pickup-1", "pickup_minute": 30, "capacity": 1},
            ],
        })
        self.assertEqual(200, response.status_code)
        self.assertEqual("READY", response.json()["status"])
        self.assertEqual("pickup-1", response.json()["reservations"][0]["slot_id"])
        self.assertFalse(response.json()["carrier_booking_started"])

    def test_v4_operator_rehearsal_covers_one_hundred_journeys(self) -> None:
        journeys = []
        for index in range(100):
            case = index % 6
            journeys.append({
                "journey_id": f"journey-{index + 1:03d}",
                "inventory_ready": case != 1,
                "packing_capacity": 0 if case == 2 else 4,
                "carrier_slot_available": case != 3,
                "data_age_minutes": 10 if case == 0 else 1,
                "cutoff_minutes": 20 if case == 4 else 90,
                "priority": 100 - index % 50,
            })
        response = self.client.post(
            "/api/v4/operations/operator-rehearsal", json={"journeys": journeys}
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual(100, response.json()["journey_count"])
        self.assertEqual(0, response.json()["unresolved_count"])
        self.assertFalse(response.json()["warehouse_commands_started"])

    def test_v4_fulfillment_shift_board_prioritises_stale_data(self) -> None:
        journeys = []
        for index in range(100):
            case = index % 6
            journeys.append({
                "journey_id": f"shift-{index + 1:03d}",
                "inventory_ready": case != 1,
                "packing_capacity": 0 if case == 2 else 4,
                "carrier_slot_available": case != 3,
                "data_age_minutes": 10 if case == 0 else 1,
                "cutoff_minutes": 20 if case == 4 else 90,
                "priority": 100 - index % 50,
            })
        response = self.client.post("/api/v4/operations/fulfillment-shift-board", json={
            "journeys": journeys, "visible_limit": 10,
        })
        self.assertEqual(200, response.status_code)
        self.assertEqual("FULFILLMENT_SHIFT_BOARD_READY", response.json()["status"])
        self.assertEqual(10, response.json()["visible_count"])
        self.assertEqual("BLOCKED", response.json()["focus_items"][0]["status"])
        self.assertFalse(response.json()["warehouse_commands_started"])


if __name__ == "__main__":
    unittest.main()
