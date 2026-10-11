from __future__ import annotations

import unittest

from load_testing.incidents import reconcile_incidents
from load_testing.notifications import plan_notifications


ALERT = {
    "alert_id": "high:SLO-FAILED-CHECKPOINTS",
    "tier": "high",
    "rule_id": "SLO-FAILED-CHECKPOINTS",
    "severity": "critical",
    "observed": 2,
    "operator": "<=",
    "threshold": 0,
}
POLICY = {
    "policy_version": "1.0",
    "severity_routes": {"critical": ["pager", "ops-dashboard"], "warning": ["ops-dashboard"]},
}


def report(*alerts: dict) -> dict:
    return {
        "report_version": "1.0",
        "status": "ALERT" if alerts else "PASS",
        "policy_version": "1.0",
        "alerts": list(alerts),
    }


class NotificationOutboxTests(unittest.TestCase):
    def test_open_incident_produces_one_stable_routed_event(self) -> None:
        state = reconcile_incidents(report(ALERT), None, "2026-10-11T01:00:00Z")
        first = plan_notifications(state, POLICY)
        second = plan_notifications(state, POLICY)
        self.assertEqual(first, second)
        self.assertEqual("PENDING", first["status"])
        self.assertEqual("INCIDENT_OPENED", first["events"][0]["event_type"])
        self.assertEqual(["ops-dashboard", "pager"], first["events"][0]["channels"])

    def test_delivery_ledger_filters_already_delivered_events(self) -> None:
        state = reconcile_incidents(report(ALERT), None, "2026-10-11T01:00:00Z")
        event_id = plan_notifications(state, POLICY)["events"][0]["event_id"]
        outbox = plan_notifications(
            state,
            POLICY,
            {"ledger_version": "1.0", "delivered_event_ids": [event_id]},
        )
        self.assertEqual("EMPTY", outbox["status"])
        self.assertEqual([], outbox["events"])

    def test_resolved_incident_has_open_and_resolution_events(self) -> None:
        opened = reconcile_incidents(report(ALERT), None, "2026-10-11T01:00:00Z")
        resolved = reconcile_incidents(report(), opened, "2026-10-11T01:10:00Z")
        events = plan_notifications(resolved, POLICY)["events"]
        self.assertEqual(
            ["INCIDENT_OPENED", "INCIDENT_RESOLVED"],
            [row["event_type"] for row in events],
        )
        self.assertNotEqual(events[0]["event_id"], events[1]["event_id"])

    def test_missing_severity_route_is_rejected(self) -> None:
        state = reconcile_incidents(report(ALERT), None, "2026-10-11T01:00:00Z")
        with self.assertRaisesRegex(ValueError, "no notification route"):
            plan_notifications(
                state,
                {"policy_version": "1.0", "severity_routes": {"warning": ["ops"]}},
            )


if __name__ == "__main__":
    unittest.main()
