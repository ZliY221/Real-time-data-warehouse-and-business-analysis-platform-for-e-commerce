from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from load_testing.slo import evaluate_slos, write_slo_report


def summary() -> dict:
    return {
        "status": "COMPLETE",
        "plan_version": "1.0",
        "tiers": [
            {
                "name": "low",
                "target_publish_rate_per_second": 100,
                "end_to_end_throughput_per_second": 95,
                "runtime": {
                    "job_states": ["RUNNING"],
                    "max_backpressure_ratio": 0.05,
                    "max_failed_checkpoint_count": 0,
                },
            },
            {
                "name": "high",
                "target_publish_rate_per_second": 1000,
                "end_to_end_throughput_per_second": 880,
                "runtime": {
                    "job_states": ["FINISHED"],
                    "max_backpressure_ratio": 0.25,
                    "max_failed_checkpoint_count": 0,
                },
            },
        ],
    }


def policy() -> dict:
    return {
        "policy_version": "1.0",
        "defaults": {
            "min_throughput_ratio": 0.9,
            "max_backpressure_ratio": 0.2,
            "max_failed_checkpoints": 0,
            "allowed_job_states": ["RUNNING", "FINISHED"],
        },
        "tier_overrides": {"high": {"min_throughput_ratio": 0.85, "max_backpressure_ratio": 0.3}},
    }


class LoadSloTests(unittest.TestCase):
    def test_passes_with_tier_specific_thresholds(self) -> None:
        report = evaluate_slos(summary(), policy())
        self.assertEqual("PASS", report["status"])
        self.assertEqual([], report["alerts"])
        self.assertFalse(report["claims"]["production_slo_certified"])

    def test_emits_stable_alerts_for_each_breached_rule(self) -> None:
        document = summary()
        document["tiers"][0]["end_to_end_throughput_per_second"] = 80
        document["tiers"][0]["runtime"]["max_failed_checkpoint_count"] = 1
        report = evaluate_slos(document, policy())
        self.assertEqual("ALERT", report["status"])
        self.assertEqual(
            ["low:SLO-THROUGHPUT-RATIO", "low:SLO-FAILED-CHECKPOINTS"],
            [alert["alert_id"] for alert in report["alerts"]],
        )

    def test_rejects_incomplete_or_malformed_evidence(self) -> None:
        document = summary()
        document["status"] = "INCOMPLETE"
        with self.assertRaisesRegex(ValueError, "must be COMPLETE"):
            evaluate_slos(document, policy())
        document = summary()
        document["tiers"][0]["runtime"]["job_states"] = "RUNNING"
        with self.assertRaisesRegex(ValueError, "job states must be lists"):
            evaluate_slos(document, policy())

    def test_writes_machine_readable_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary_path = root / "summary.json"
            policy_path = root / "policy.json"
            output_path = root / "slo-report.json"
            summary_path.write_text(json.dumps(summary()), encoding="utf-8")
            policy_path.write_text(json.dumps(policy()), encoding="utf-8")
            report = write_slo_report(summary_path, policy_path, output_path)
            self.assertEqual(report, json.loads(output_path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
