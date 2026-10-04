from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from event_generator.generator import generate_order_events
from reconciliation.engine import (
    ReconciliationInputError,
    build_batch_baseline,
    load_late_event_ids,
    load_metric_rows,
    reconcile_metrics,
)
from reconciliation.models import MinuteMetric


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PATH = ROOT / "data" / "sample" / "order_events.ndjson"
FIXED_TIME = datetime(2026, 10, 3, 8, 0, tzinfo=UTC)


def event_lines(count: int = 4) -> list[str]:
    return [json.dumps(event, ensure_ascii=False) for event in generate_order_events(count)]


class ReconciliationTests(unittest.TestCase):
    def test_reference_events_produce_exact_decimal_minute_metrics(self) -> None:
        with SAMPLE_PATH.open("r", encoding="utf-8") as stream:
            baseline = build_batch_baseline(stream)

        source_events = [
            json.loads(line)
            for line in SAMPLE_PATH.read_text(encoding="utf-8").splitlines()
        ]
        expected_gmv = sum(
            (Decimal(event["payload"]["total_amount"]) for event in source_events),
            Decimal("0.00"),
        )
        self.assertEqual(baseline.total_records, 20)
        self.assertEqual(baseline.accepted_records, 20)
        self.assertEqual(sum(metric.gmv for metric in baseline.metrics), expected_gmv)
        self.assertTrue(all(metric.window_end - metric.window_start == timedelta(minutes=1)
                            for metric in baseline.metrics))

    def test_invalid_duplicate_and_late_events_follow_flink_stage_order(self) -> None:
        events = generate_order_events(3)
        duplicate = json.loads(json.dumps(events[0]))
        invalid = json.loads(json.dumps(events[1]))
        invalid["payload"]["total_amount"] = "0.00"
        lines = [
            json.dumps(events[0], ensure_ascii=False),
            json.dumps(duplicate, ensure_ascii=False),
            "not-json",
            json.dumps(invalid, ensure_ascii=False),
            json.dumps(events[1], ensure_ascii=False),
            json.dumps(events[2], ensure_ascii=False),
        ]

        baseline = build_batch_baseline(lines, late_event_ids={events[2]["event_id"]})

        self.assertEqual(baseline.total_records, 6)
        self.assertEqual(baseline.parsed_records, 5)
        self.assertEqual(baseline.invalid_json_records, 1)
        self.assertEqual(baseline.invalid_contract_records, 1)
        self.assertEqual(baseline.duplicate_records, 1)
        self.assertEqual(baseline.excluded_late_records, 1)
        self.assertEqual(baseline.accepted_records, 2)

    def test_late_event_export_requires_non_empty_event_ids(self) -> None:
        self.assertEqual(
            load_late_event_ids(['{"event_id":"evt-1"}', '{"event_id":"evt-1"}']),
            {"evt-1"},
        )
        with self.assertRaisesRegex(ReconciliationInputError, "event_id"):
            load_late_event_ids(['{"event_id":""}'])

    def test_acceptance_trigger_advances_watermark_past_the_business_window(self) -> None:
        business_events = generate_order_events(20)
        trigger_events = generate_order_events(
            3,
            seed=9090,
            start_time=datetime(2026, 10, 2, 10, 1, 15, tzinfo=UTC),
        )
        business_timestamps = [
            datetime.fromisoformat(event["event_time"].replace("Z", "+00:00"))
            for event in business_events
        ]
        trigger_timestamps = [
            datetime.fromisoformat(event["event_time"].replace("Z", "+00:00"))
            for event in trigger_events
        ]
        window_end = datetime(2026, 10, 2, 10, 1, tzinfo=UTC)

        self.assertLess(max(business_timestamps) - timedelta(seconds=10), window_end)
        self.assertGreater(max(trigger_timestamps) - timedelta(seconds=10), window_end)

    def test_matching_metrics_pass_with_deterministic_safe_report(self) -> None:
        baseline = build_batch_baseline(event_lines())
        report = reconcile_metrics(
            baseline,
            reversed(baseline.metrics),
            generated_at=FIXED_TIME,
            events_input="data/sample.ndjson",
            actual_input="build/actual.ndjson",
        )

        self.assertTrue(report.passed)
        self.assertEqual(report.matched_metric_keys, len(baseline.metrics))
        self.assertEqual(report.to_dict()["generated_at"], "2026-10-03T08:00:00.000Z")
        self.assertEqual(report.to_dict()["differences"], [])
        self.assertNotIn("user_id", json.dumps(report.to_dict()))

    def test_reconciliation_distinguishes_missing_unexpected_and_value_differences(self) -> None:
        baseline = build_batch_baseline(event_lines(20))
        first, second, *remaining = baseline.metrics
        changed = MinuteMetric(
            first.window_start,
            first.window_end,
            first.region,
            first.channel,
            first.order_count + 1,
            first.gmv + Decimal("1.00"),
        )
        unexpected = MinuteMetric(
            first.window_start + timedelta(minutes=5),
            first.window_end + timedelta(minutes=5),
            "辽宁",
            "app",
            1,
            Decimal("9.99"),
        )

        report = reconcile_metrics(
            baseline,
            [changed, *remaining, unexpected],
            generated_at=FIXED_TIME,
            events_input="events.ndjson",
            actual_input="actual.ndjson",
        )

        self.assertFalse(report.passed)
        self.assertEqual(
            {difference.status for difference in report.differences},
            {"order_count_and_gmv_mismatch", "missing_actual", "unexpected_actual"},
        )
        self.assertIn("## Differences", report.to_markdown())
        self.assertIn(second.region, report.to_markdown())

    def test_actual_metric_loader_rejects_ambiguous_rows(self) -> None:
        valid = {
            "window_start": "2026-10-02T10:00:00Z",
            "window_end": "2026-10-02T10:01:00Z",
            "region": "辽宁",
            "channel": "app",
            "order_count": 1,
            "gmv": "10.00",
        }
        row = json.dumps(valid, ensure_ascii=False)
        self.assertEqual(len(load_metric_rows([row])), 1)
        numeric_decimal_row = row.replace('"gmv": "10.00"', '"gmv": 10.00')
        self.assertEqual(len(load_metric_rows([numeric_decimal_row])), 1)

        with self.assertRaisesRegex(ReconciliationInputError, "duplicates"):
            load_metric_rows([row, row])
        for field, value, message in (
            ("window_start", "2026-10-02T10:00:00", "timezone"),
            ("window_start", "2026-10-02T10:00:30Z", "minute-aligned"),
            ("window_end", "2026-10-02T10:02:00Z", "one minute"),
            ("gmv", "10.0", "two decimals"),
            ("order_count", True, "non-negative integer"),
        ):
            with self.subTest(field=field):
                invalid = dict(valid)
                invalid[field] = value
                with self.assertRaisesRegex(ReconciliationInputError, message):
                    load_metric_rows([json.dumps(invalid, ensure_ascii=False)])

    def test_cli_builds_baseline_and_uses_exit_codes_for_comparison(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            expected = output / "expected.ndjson"
            baseline = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "reconciliation.cli",
                    "baseline",
                    "--events",
                    str(SAMPLE_PATH),
                    "--output",
                    str(expected),
                ],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(baseline.returncode, 0, baseline.stderr)
            self.assertIn("batch baseline PASS", baseline.stdout)

            passing_report = output / "passing.json"
            passing = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "reconciliation.cli",
                    "compare",
                    "--events",
                    str(SAMPLE_PATH),
                    "--actual",
                    str(expected),
                    "--json-output",
                    str(passing_report),
                ],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(passing.returncode, 0, passing.stderr)
            report_document = json.loads(passing_report.read_text(encoding="utf-8"))
            self.assertTrue(report_document["summary"]["passed"])

            rows = expected.read_text(encoding="utf-8").splitlines()
            changed = json.loads(rows[0])
            changed["gmv"] = "0.00"
            rows[0] = json.dumps(changed, ensure_ascii=False)
            actual = output / "actual.ndjson"
            actual.write_text("\n".join(rows) + "\n", encoding="utf-8")
            failing = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "reconciliation.cli",
                    "compare",
                    "--events",
                    str(SAMPLE_PATH),
                    "--actual",
                    str(actual),
                ],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(failing.returncode, 1, failing.stderr)
            self.assertIn("metric reconciliation FAIL", failing.stdout)


if __name__ == "__main__":
    unittest.main()
