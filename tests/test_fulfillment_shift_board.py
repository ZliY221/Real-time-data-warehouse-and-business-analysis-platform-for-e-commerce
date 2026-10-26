import unittest

from metrics_api.fulfillment_shift_board import build_fulfillment_shift_board
from metrics_api.operator_journey import FulfillmentOperatorJourney


def sample_journeys() -> list[FulfillmentOperatorJourney]:
    return [FulfillmentOperatorJourney(
        journey_id=f"fulfillment-{index + 1:03d}",
        inventory_ready=index % 6 != 1,
        packing_capacity=0 if index % 6 == 2 else 4,
        carrier_slot_available=index % 6 != 3,
        data_age_minutes=12 if index % 6 == 0 else 2,
        cutoff_minutes=20 if index % 6 == 4 else 120,
        priority=100 - index % 50,
    ) for index in range(100)]


class FulfillmentShiftBoardTests(unittest.TestCase):
    def test_shift_board_prioritises_stale_data_before_warehouse_decisions(self):
        result = build_fulfillment_shift_board(sample_journeys(), visible_limit=10)
        self.assertEqual("FULFILLMENT_SHIFT_BOARD_READY", result["status"])
        self.assertEqual(100, result["journey_count"])
        self.assertEqual(10, result["visible_count"])
        self.assertTrue(all(item["status"] == "BLOCKED" for item in result["focus_items"]))
        self.assertFalse(result["warehouse_commands_started"])

    def test_shift_board_exposes_lanes_and_resume_keys(self):
        result = build_fulfillment_shift_board(sample_journeys())
        self.assertEqual(100, sum(result["lane_counts"].values()))
        self.assertEqual(len(result["focus_items"]), len({
            item["resume_key"] for item in result["focus_items"]
        }))
        self.assertTrue(all(item["lane"] for item in result["focus_items"]))

    def test_visible_limit_is_bounded(self):
        with self.assertRaises(ValueError):
            build_fulfillment_shift_board(sample_journeys(), visible_limit=26)
