from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from data_quality.engine import (
    QualityConfigurationError,
    evaluate_ndjson,
    load_quality_config,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "data-quality-rules.json"
VALID_PATH = ROOT / "data" / "sample" / "order_events.ndjson"
INVALID_PATH = ROOT / "data" / "quality" / "order_events_with_quality_issues.ndjson"
FIXED_TIME = datetime(2026, 10, 3, 3, 0, tzinfo=UTC)


class DataQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_quality_config(CONFIG_PATH)

    @staticmethod
    def evaluate(path: Path):
        with path.open("r", encoding="utf-8-sig") as stream:
            return evaluate_ndjson(
                stream,
                DataQualityTests.config,
                input_file=path.relative_to(ROOT).as_posix(),
                generated_at=FIXED_TIME,
            )

    def test_config_loads_all_supported_rule_types(self) -> None:
        self.assertEqual(self.config["version"], 1)
        self.assertEqual(
            {rule["type"] for rule in self.config["rules"]},
            {
                "contract",
                "completeness",
                "uniqueness",
                "range",
                "timeliness",
                "distribution",
            },
        )

    def test_reference_sample_passes_every_quality_rule(self) -> None:
        report = self.evaluate(VALID_PATH)

        self.assertTrue(report.passed)
        self.assertEqual(report.total_records, 20)
        self.assertEqual(report.parsed_records, 20)
        self.assertTrue(all(rule.passed for rule in report.rules))
        self.assertEqual(report.invalid_json_records, 0)
        self.assertEqual(report.invalid_contract_records, 0)
        self.assertEqual(report.duplicate_records, 0)
        self.assertEqual(report.late_records, 0)

    def test_issue_fixture_triggers_every_quality_rule_type(self) -> None:
        report = self.evaluate(INVALID_PATH)

        self.assertFalse(report.passed)
        self.assertEqual(report.total_records, 12)
        self.assertEqual(report.parsed_records, 11)
        self.assertEqual(report.invalid_json_records, 1)
        self.assertEqual(report.invalid_contract_records, 1)
        self.assertEqual(report.duplicate_records, 1)
        self.assertEqual(report.late_records, 1)
        self.assertEqual(
            {rule.rule_type for rule in report.rules if not rule.passed},
            {
                "contract",
                "completeness",
                "uniqueness",
                "range",
                "timeliness",
                "distribution",
            },
        )

    def test_reports_are_deterministic_and_do_not_embed_event_payloads(self) -> None:
        report = self.evaluate(INVALID_PATH)
        document = report.to_dict()
        markdown = report.to_markdown()

        self.assertEqual(document["generated_at"], "2026-10-03T03:00:00.000Z")
        self.assertEqual(document["summary"]["failed_rules"], 6)
        self.assertIn("# Data quality report", markdown)
        self.assertIn("channel-share-drift", markdown)
        self.assertNotIn("usr_quality_", json.dumps(document, ensure_ascii=False))
        self.assertNotIn("usr_quality_", markdown)

    def test_unsafe_or_ambiguous_configs_are_rejected(self) -> None:
        invalid_documents = [
            {"version": 2, "rules": []},
            {
                "version": 1,
                "rules": [
                    {"id": "same", "type": "contract", "max_invalid_rate": 0},
                    {"id": "same", "type": "contract", "max_invalid_rate": 0},
                ],
            },
            {
                "version": 1,
                "rules": [
                    {
                        "id": "bad-distribution",
                        "type": "distribution",
                        "field": "payload.channel",
                        "expected": {"app": 0.4, "web": 0.4},
                        "max_absolute_deviation": 0.1,
                    }
                ],
            },
            {
                "version": 1,
                "rules": [{"id": "sql", "type": "arbitrary_sql", "max_invalid_rate": 0}],
            },
            {
                "version": 1,
                "rules": [
                    {
                        "id": "nan-range",
                        "type": "range",
                        "field": "payload.total_amount",
                        "min": "NaN",
                        "max": "100.00",
                        "max_out_of_range_rate": 0,
                    }
                ],
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            for index, document in enumerate(invalid_documents):
                with self.subTest(index=index):
                    path = Path(directory) / f"config-{index}.json"
                    path.write_text(json.dumps(document), encoding="utf-8")
                    with self.assertRaises(QualityConfigurationError):
                        load_quality_config(path)

    def test_report_timestamp_must_include_timezone(self) -> None:
        with VALID_PATH.open("r", encoding="utf-8-sig") as stream:
            with self.assertRaisesRegex(ValueError, "timezone"):
                evaluate_ndjson(
                    stream,
                    self.config,
                    input_file="sample.ndjson",
                    generated_at=datetime(2026, 10, 3, 3, 0),
                )

    def test_cli_writes_reports_and_uses_exit_code_as_a_quality_gate(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            common = [
                sys.executable,
                "-m",
                "data_quality.cli",
                "--config",
                str(CONFIG_PATH),
                "--json-output",
                str(output / "report.json"),
                "--markdown-output",
                str(output / "report.md"),
            ]
            passing = subprocess.run(
                [*common, "--input", str(VALID_PATH)],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(passing.returncode, 0, passing.stderr)
            self.assertIn("data quality PASS", passing.stdout)
            self.assertTrue((output / "report.json").is_file())
            self.assertTrue((output / "report.md").is_file())

            failing = subprocess.run(
                [*common, "--input", str(INVALID_PATH)],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(failing.returncode, 1, failing.stderr)
            self.assertIn("data quality FAIL", failing.stdout)


if __name__ == "__main__":
    unittest.main()
