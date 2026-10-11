from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from load_testing.incidents import reconcile_incidents, update_incident_state


def report(*alerts: dict) -> dict:
    return {
        "report_version": "1.0",
        "status": "ALERT" if alerts else "PASS",
        "policy_version": "2026-10-11",
        "alerts": list(alerts),
    }


ALERT = {
    "alert_id": "high:SLO-BACKPRESSURE-RATIO",
    "tier": "high",
    "rule_id": "SLO-BACKPRESSURE-RATIO",
    "severity": "warning",
    "observed": 0.4,
    "operator": "<=",
    "threshold": 0.2,
}


class IncidentLifecycleTests(unittest.TestCase):
    def test_alert_opens_and_repeated_alert_updates_one_incident(self) -> None:
        first = reconcile_incidents(report(ALERT), None, "2026-10-11T01:00:00Z")
        second = reconcile_incidents(report({**ALERT, "observed": 0.5}), first, "2026-10-11T01:05:00Z")
        self.assertEqual(1, second["active_incident_count"])
        self.assertEqual(1, len(second["incidents"]))
        self.assertEqual(2, second["incidents"][0]["occurrence_count"])
        self.assertEqual(0.5, second["incidents"][0]["latest_observation"]["observed"])

    def test_missing_alert_resolves_and_recurrence_opens_new_incident(self) -> None:
        opened = reconcile_incidents(report(ALERT), None, "2026-10-11T01:00:00Z")
        resolved = reconcile_incidents(report(), opened, "2026-10-11T01:10:00Z")
        reopened = reconcile_incidents(report(ALERT), resolved, "2026-10-11T02:00:00Z")
        self.assertEqual(1, reopened["active_incident_count"])
        self.assertEqual(1, reopened["resolved_incident_count"])
        self.assertEqual(2, len(reopened["incidents"]))
        self.assertNotEqual(
            reopened["incidents"][0]["incident_id"], reopened["incidents"][1]["incident_id"]
        )

    def test_invalid_or_out_of_order_inputs_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate alert_id"):
            reconcile_incidents(report(ALERT, ALERT), None, "2026-10-11T01:00:00Z")
        opened = reconcile_incidents(report(ALERT), None, "2026-10-11T01:00:00Z")
        with self.assertRaisesRegex(ValueError, "backwards"):
            reconcile_incidents(report(ALERT), opened, "2026-10-11T00:59:00Z")
        normalized = reconcile_incidents(report(ALERT), None, "2026-10-11T09:00:00+08:00")
        self.assertEqual("2026-10-11T01:00:00Z", normalized["updated_at"])

    def test_state_file_is_updated_atomically_and_contains_no_event_payload(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "slo.json"
            state_path = root / "incidents.json"
            report_path.write_text(json.dumps(report(ALERT)), encoding="utf-8")
            saved = update_incident_state(report_path, state_path, "2026-10-11T01:00:00Z")
            self.assertEqual(saved, json.loads(state_path.read_text(encoding="utf-8")))
            self.assertNotIn("event", state_path.read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
