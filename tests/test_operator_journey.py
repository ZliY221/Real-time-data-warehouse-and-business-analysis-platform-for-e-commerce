import unittest

from metrics_api.operator_journey import (
    FulfillmentOperatorJourney,
    rehearse_fulfillment_journeys,
)


def sample_journeys() -> list[FulfillmentOperatorJourney]:
    rows = []
    for index in range(100):
        case = index % 6
        rows.append(FulfillmentOperatorJourney(
            journey_id=f"fulfillment-{index + 1:03d}",
            inventory_ready=case != 1,
            packing_capacity=0 if case == 2 else 4,
            carrier_slot_available=case != 3,
            data_age_minutes=12 if case == 0 else 2,
            cutoff_minutes=20 if case == 4 else 120,
            priority=100 - index % 50,
        ))
    return rows


class FulfillmentOperatorJourneyTests(unittest.TestCase):
    def test_one_hundred_journeys_all_have_guided_actions(self):
        result = rehearse_fulfillment_journeys(sample_journeys())
        self.assertEqual("USABILITY_REHEARSAL_PASSED", result["status"])
        self.assertEqual(100, result["journey_count"])
        self.assertEqual(0, result["unresolved_count"])
        self.assertTrue(all(row["primary_action"] for row in result["journeys"]))
        self.assertFalse(result["warehouse_commands_started"])

    def test_stale_data_blocks_operational_decisions(self):
        result = rehearse_fulfillment_journeys(sample_journeys())
        stale = next(row for row in result["journeys"] if row["journey_id"] == "fulfillment-001")
        self.assertEqual("BLOCKED", stale["status"])
        self.assertEqual("REFRESH_OPERATING_METRICS", stale["primary_action"])

    def test_rejects_incomplete_rehearsal(self):
        with self.assertRaises(ValueError):
            rehearse_fulfillment_journeys(sample_journeys()[:99])
