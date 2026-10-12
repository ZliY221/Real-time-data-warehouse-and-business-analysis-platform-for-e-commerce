from __future__ import annotations

import unittest

from load_testing.delivery_receipts import reconcile_delivery_receipts
from load_testing.notifications import plan_notifications


OUTBOX = {
    "outbox_version": "1.0",
    "events": [
        {
            "event_id": "evt-one",
            "channels": ["ops-dashboard", "pager"],
        }
    ],
}


def receipt(channel: str, status: str = "DELIVERED") -> dict:
    return {
        "event_id": "evt-one",
        "channel": channel,
        "status": status,
        "attempted_at": "2026-10-12T01:00:00Z",
    }


class DeliveryReceiptTests(unittest.TestCase):
    def test_all_routes_complete_the_event(self) -> None:
        ledger, report = reconcile_delivery_receipts(
            OUTBOX,
            {"receipt_version": "1.0", "receipts": [receipt("pager"), receipt("ops-dashboard")]},
        )
        self.assertEqual("COMPLETE", report["status"])
        self.assertEqual(["evt-one"], ledger["delivered_event_ids"])
        self.assertEqual(2, len(ledger["delivered_routes"]))

    def test_partial_delivery_keeps_only_the_remaining_route_in_next_outbox(self) -> None:
        ledger, report = reconcile_delivery_receipts(
            OUTBOX,
            {"receipt_version": "1.0", "receipts": [receipt("pager")]},
        )
        self.assertEqual("PARTIAL", report["status"])
        incident_state = {
            "state_version": "1.0",
            "incidents": [
                {
                    "incident_id": "incident-one",
                    "alert_id": "alert-one",
                    "tier": "high",
                    "rule_id": "rule-one",
                    "severity": "critical",
                    "status": "OPEN",
                    "first_seen_at": "2026-10-12T00:00:00Z",
                }
            ],
        }
        policy = {
            "policy_version": "1.0",
            "severity_routes": {"critical": ["ops-dashboard", "pager"]},
        }
        stable_id = plan_notifications(incident_state, policy)["events"][0]["event_id"]
        ledger["delivered_routes"][0]["event_id"] = stable_id
        retried = plan_notifications(incident_state, policy, ledger)
        self.assertEqual(["ops-dashboard"], retried["events"][0]["channels"])

    def test_failed_route_never_marks_event_delivered(self) -> None:
        ledger, report = reconcile_delivery_receipts(
            OUTBOX,
            {"receipt_version": "1.0", "receipts": [receipt("pager", "FAILED")]},
        )
        self.assertEqual("PARTIAL", report["status"])
        self.assertEqual("FAILED", report["events"][0]["status"])
        self.assertEqual([], ledger["delivered_event_ids"])

    def test_unknown_or_duplicate_receipts_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not match"):
            reconcile_delivery_receipts(
                OUTBOX,
                {"receipt_version": "1.0", "receipts": [receipt("email")]},
            )
        with self.assertRaisesRegex(ValueError, "must be unique"):
            reconcile_delivery_receipts(
                OUTBOX,
                {"receipt_version": "1.0", "receipts": [receipt("pager"), receipt("pager")]},
            )


if __name__ == "__main__":
    unittest.main()
