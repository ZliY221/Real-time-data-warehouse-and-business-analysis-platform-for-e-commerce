from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import urlparse

from load_testing.flink_runtime import FlinkRestClient, collect_runtime_snapshot
from load_testing.load_dataset import generate_load_dataset
from load_testing.report import runtime_snapshot_markdown


JOB_ID = "0123456789abcdef0123456789abcdef"
VERTEX_ID = "fedcba9876543210fedcba9876543210"


class LoadDatasetTests(unittest.TestCase):
    def test_dataset_and_manifest_are_deterministic_and_honest(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = generate_load_dataset(
                root / "first.ndjson",
                root / "first.json",
                count=8,
                seed=7,
                start_time=datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc),
                event_time_rate=4,
                profile="small-baseline",
                generated_at=datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc),
            )
            second = generate_load_dataset(
                root / "second.ndjson",
                root / "second.json",
                count=8,
                seed=7,
                start_time=datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc),
                event_time_rate=4,
                profile="small-baseline",
                generated_at=datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc),
            )
            self.assertEqual(
                (root / "first.ndjson").read_bytes(),
                (root / "second.ndjson").read_bytes(),
            )
            self.assertEqual(first["dataset"]["sha256"], second["dataset"]["sha256"])
            self.assertEqual(1750, first["generator"]["event_time_span_ms"])
            self.assertFalse(first["claims"]["measured_publish_rate"])
            self.assertFalse(first["claims"]["measured_pipeline_throughput"])
            self.assertEqual("first.ndjson", first["dataset"]["path"])
            self.assertNotIn(str(root), json.dumps(first))

    def test_dataset_bounds_are_enforced(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                generate_load_dataset(
                    root / "events.ndjson",
                    root / "manifest.json",
                    count=0,
                    seed=1,
                    start_time=datetime.now(timezone.utc),
                    event_time_rate=1,
                    profile="invalid",
                )


class FlinkRuntimeSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.seen_urls: list[str] = []

    def fetch_json(self, url: str) -> object:
        self.seen_urls.append(url)
        parsed = urlparse(url)
        if parsed.path == f"/jobs/{JOB_ID}":
            return {
                "name": "ecommerce-order-metrics",
                "state": "RUNNING",
                "duration": 15000,
                "vertices": [
                    {
                        "id": VERTEX_ID,
                        "name": "Kafka Source",
                        "status": "RUNNING",
                        "parallelism": 1,
                    }
                ],
            }
        if parsed.path == f"/jobs/{JOB_ID}/metrics":
            return [
                {"id": "numRestarts", "value": "1"},
                {"id": "uptime", "value": "12000"},
                {"id": "downtime", "value": "0"},
            ]
        if parsed.path == f"/jobs/{JOB_ID}/vertices/{VERTEX_ID}/subtasks/0/metrics":
            if not parsed.query:
                return [
                    {"id": f"0.{name}"}
                    for name in (
                        "numRecordsIn",
                        "numRecordsOut",
                        "numRecordsInPerSecond",
                        "numRecordsOutPerSecond",
                        "backPressuredTimeMsPerSecond",
                        "idleTimeMsPerSecond",
                        "busyTimeMsPerSecond",
                    )
                ]
            return [
                {"id": "0.numRecordsIn", "value": "20000"},
                {"id": "0.numRecordsOut", "value": "19999"},
                {"id": "0.numRecordsInPerSecond", "value": "950.5"},
                {"id": "0.numRecordsOutPerSecond", "value": "949.25"},
                {"id": "0.backPressuredTimeMsPerSecond", "value": "10"},
                {"id": "0.idleTimeMsPerSecond", "value": "90"},
                {"id": "0.busyTimeMsPerSecond", "value": "900"},
            ]
        if parsed.path == f"/jobs/{JOB_ID}/vertices/{VERTEX_ID}/backpressure":
            return {
                "status": "ok",
                "backpressure-level": "low",
                "subtasks": [
                    {"subtask": 0, "ratio": 0.2, "busyRatio": 0.7, "idleRatio": 0.1}
                ],
            }
        if parsed.path == f"/jobs/{JOB_ID}/checkpoints":
            return {
                "counts": {
                    "total": 3,
                    "in_progress": 0,
                    "completed": 2,
                    "failed": 1,
                    "restored": 1,
                },
                "latest": {
                    "completed": {
                        "id": 3,
                        "status": "COMPLETED",
                        "end_to_end_duration": 42,
                        "checkpointed_size": 2048,
                        "processed_data": 1024,
                        "persisted_data": 512,
                        "num_acknowledged_subtasks": 1,
                        "num_subtasks": 1,
                        "external_path": "/secret/checkpoint/path",
                    },
                    "failed": {"failure_message": "sensitive internal failure"},
                },
            }
        raise AssertionError(f"unexpected URL: {url}")

    def test_snapshot_collects_bounded_runtime_evidence(self) -> None:
        client = FlinkRestClient(fetch_json=self.fetch_json)
        snapshot = collect_runtime_snapshot(
            client,
            JOB_ID,
            collected_at=datetime(2026, 10, 10, 1, 2, 3, tzinfo=timezone.utc),
        )
        self.assertEqual("RUNNING", snapshot["job"]["state"])
        self.assertEqual(1, snapshot["job"]["metrics"]["numRestarts"])
        self.assertEqual(2, snapshot["checkpoints"]["counts"]["completed"])
        self.assertEqual(0.2, snapshot["vertices"][0]["backpressure"]["max_backpressure_ratio"])
        self.assertEqual(950.5, snapshot["vertices"][0]["metrics"]["numRecordsInPerSecond"])
        discovery = snapshot["vertices"][0]["metric_discovery"]
        self.assertEqual(7, discovery["available_count"])
        self.assertEqual(1, discovery["queried_subtasks"])
        self.assertEqual(1, discovery["selected_series"]["numRecordsIn"])
        self.assertIn("0.numRecordsIn", discovery["relevant_candidates"])
        serialized = json.dumps(snapshot)
        self.assertNotIn("sensitive internal failure", serialized)
        self.assertNotIn("/secret/checkpoint/path", serialized)
        self.assertFalse(snapshot["privacy"]["contains_event_payloads"])
        self.assertTrue(any("get=" in url for url in self.seen_urls))
        self.assertTrue(any("/subtasks/0/metrics" in url for url in self.seen_urls))

    def test_deprecated_backpressure_endpoint_falls_back_to_task_metric(self) -> None:
        original_fetch = self.fetch_json

        def fetch_with_deprecated_backpressure(url: str) -> object:
            parsed = urlparse(url)
            if parsed.path.endswith("/backpressure"):
                return {"status": "deprecated"}
            return original_fetch(url)

        snapshot = collect_runtime_snapshot(
            FlinkRestClient(fetch_json=fetch_with_deprecated_backpressure),
            JOB_ID,
        )
        backpressure = snapshot["vertices"][0]["backpressure"]
        self.assertEqual("task_metric", backpressure["source"])
        self.assertEqual("ok", backpressure["level"])
        self.assertEqual(0.01, backpressure["max_backpressure_ratio"])

    def test_vertex_metrics_aggregate_equal_ids_across_subtasks(self) -> None:
        def fetch_two_subtasks(url: str) -> object:
            parsed = urlparse(url)
            if "/subtasks/" in parsed.path and parsed.path.endswith("/metrics"):
                if not parsed.query:
                    return [{"id": "numRecordsInPerSecond"}, {"id": "busyTimeMsPerSecond"}]
                subtask = int(parsed.path.split("/subtasks/")[1].split("/")[0])
                return [
                    {"id": "numRecordsInPerSecond", "value": str(100 + subtask)},
                    {"id": "busyTimeMsPerSecond", "value": str(800 + 50 * subtask)},
                ]
            raise AssertionError(f"unexpected URL: {url}")

        metrics, discovery = FlinkRestClient(fetch_json=fetch_two_subtasks).vertex_metrics(
            (
                f"/jobs/{JOB_ID}/vertices/{VERTEX_ID}/subtasks/0/metrics",
                f"/jobs/{JOB_ID}/vertices/{VERTEX_ID}/subtasks/1/metrics",
            )
        )
        self.assertEqual(201, metrics["numRecordsInPerSecond"])
        self.assertEqual(850, metrics["busyTimeMsPerSecond"])
        self.assertEqual(2, discovery["selected_series"]["numRecordsInPerSecond"])

    def test_vertex_metric_discovery_waits_for_flink_refresh(self) -> None:
        current_time = [0.0]
        discovery_calls = [0]

        def clock() -> float:
            return current_time[0]

        def sleeper(seconds: float) -> None:
            current_time[0] += seconds

        def delayed_fetch(url: str) -> object:
            parsed = urlparse(url)
            if parsed.query:
                return [{"id": "numRecordsIn", "value": "20"}]
            discovery_calls[0] += 1
            return [] if discovery_calls[0] == 1 else [{"id": "numRecordsIn"}]

        metrics, discovery = FlinkRestClient(
            fetch_json=delayed_fetch,
            clock=clock,
            sleeper=sleeper,
        ).vertex_metrics(
            (f"/jobs/{JOB_ID}/vertices/{VERTEX_ID}/subtasks/0/metrics",),
            wait_seconds=5,
        )
        self.assertEqual(20, metrics["numRecordsIn"])
        self.assertEqual(2, discovery["discovery_attempts"])
        self.assertEqual(1.0, current_time[0])

    def test_markdown_contains_operational_summary_without_sensitive_fields(self) -> None:
        snapshot = collect_runtime_snapshot(FlinkRestClient(fetch_json=self.fetch_json), JOB_ID)
        markdown = runtime_snapshot_markdown(snapshot)
        self.assertIn("2 completed, 1 failed", markdown)
        self.assertIn("Kafka Source", markdown)
        self.assertIn("950.5", markdown)
        self.assertNotIn("failure_message", markdown)
        self.assertNotIn("external_path", markdown)

    def test_client_rejects_remote_hosts_and_invalid_job_ids_by_default(self) -> None:
        with self.assertRaises(ValueError):
            FlinkRestClient("http://flink.internal:8081")
        client = FlinkRestClient(fetch_json=self.fetch_json)
        with self.assertRaises(ValueError):
            client.job("not-a-job-id")


if __name__ == "__main__":
    unittest.main()
