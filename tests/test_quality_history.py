from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from data_quality.engine import evaluate_ndjson, load_quality_config
from data_quality.history import QualityHistoryStore


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_quality_config(ROOT / "config" / "data-quality-rules.json")
VALID_PATH = ROOT / "data" / "sample" / "order_events.ndjson"
INVALID_PATH = ROOT / "data" / "quality" / "order_events_with_quality_issues.ndjson"
BASE_TIME = datetime(2026, 10, 3, 4, 0, tzinfo=UTC)


def report_for(path: Path, generated_at: datetime):
    with path.open("r", encoding="utf-8-sig") as stream:
        return evaluate_ndjson(
            stream,
            CONFIG,
            input_file=path.relative_to(ROOT).as_posix(),
            generated_at=generated_at,
        )


class QualityHistoryTests(unittest.TestCase):
    def test_save_is_idempotent_and_preserves_rule_details(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "history.db"
            store = QualityHistoryStore(database)
            report = report_for(INVALID_PATH, BASE_TIME)

            run_id, inserted = store.save(report)
            repeated_id, repeated_inserted = store.save(report)

            self.assertTrue(inserted)
            self.assertFalse(repeated_inserted)
            self.assertEqual(run_id, repeated_id)
            self.assertEqual(len(run_id), 24)
            self.assertEqual(len(store.list_runs()), 1)
            rules = store.list_rule_results(run_id)
            self.assertEqual(len(rules), 6)
            duplicate = next(rule for rule in rules if rule.rule_id == "event-id-unique")
            self.assertFalse(duplicate.passed)
            self.assertEqual(duplicate.violations, 1)
            self.assertIn("duplicates line 1", duplicate.samples[0])

            connection = sqlite3.connect(database)
            try:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                event_columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(quality_rule_results)")
                }
            finally:
                connection.close()
            self.assertEqual(version, 1)
            self.assertNotIn("event_payload", event_columns)

    def test_run_history_filters_and_orders_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = QualityHistoryStore(Path(directory) / "history.db")
            older = report_for(VALID_PATH, BASE_TIME)
            newer = report_for(INVALID_PATH, BASE_TIME + timedelta(minutes=5))
            store.save(older)
            store.save(newer)

            runs = store.list_runs()
            self.assertEqual([run.passed for run in runs], [False, True])
            self.assertEqual(runs[0].failed_rules, 6)
            self.assertEqual(runs[0].invalid_json_records, 1)
            self.assertEqual(len(store.list_runs(passed=True)), 1)
            self.assertEqual(len(store.list_runs(passed=False)), 1)

    def test_rule_trend_is_chronological_and_keeps_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = QualityHistoryStore(Path(directory) / "history.db")
            for offset, path in enumerate((VALID_PATH, INVALID_PATH, VALID_PATH)):
                report = report_for(path, BASE_TIME + timedelta(minutes=offset))
                if offset == 2:
                    report = replace(report, input_file="data/sample/replayed-order-events.ndjson")
                store.save(report)

            trend = store.rule_trend("channel-share-drift", limit=2)
            self.assertEqual(len(trend), 2)
            self.assertLess(trend[0].generated_at, trend[1].generated_at)
            self.assertFalse(trend[0].passed)
            self.assertTrue(trend[1].passed)
            self.assertEqual(trend[0].threshold, 0.2)
            self.assertEqual(trend[0].metrics["record_counts"]["app"], 11)

    def test_history_query_rejects_unbounded_or_blank_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = QualityHistoryStore(Path(directory) / "history.db")
            for invalid_limit in (0, 501, True):
                with self.subTest(limit=invalid_limit):
                    with self.assertRaisesRegex(ValueError, "between 1 and 500"):
                        store.list_runs(limit=invalid_limit)
            with self.assertRaisesRegex(ValueError, "must not be blank"):
                store.rule_trend("   ")

    def test_cli_persists_pass_and_failure_then_exports_history(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            database = output / "history.db"
            common = [
                sys.executable,
                "-m",
                "data_quality.cli",
                "--config",
                str(ROOT / "config" / "data-quality-rules.json"),
                "--history-db",
                str(database),
            ]
            passing = subprocess.run(
                [*common, "--input", str(VALID_PATH)],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            failing = subprocess.run(
                [*common, "--input", str(INVALID_PATH)],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(passing.returncode, 0, passing.stderr)
            self.assertEqual(failing.returncode, 1, failing.stderr)
            self.assertIn("history run", passing.stdout)
            self.assertEqual(len(QualityHistoryStore(database).list_runs()), 2)

            json_output = output / "history.json"
            markdown_output = output / "history.md"
            exported = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "data_quality.history_cli",
                    "--database",
                    str(database),
                    "--rule-id",
                    "channel-share-drift",
                    "--json-output",
                    str(json_output),
                    "--markdown-output",
                    str(markdown_output),
                ],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(exported.returncode, 0, exported.stderr)
            document = json.loads(json_output.read_text(encoding="utf-8"))
            self.assertEqual(document["run_count"], 2)
            self.assertEqual(len(document["trend"]), 2)
            self.assertIn("Rule trend: channel-share-drift", markdown_output.read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
