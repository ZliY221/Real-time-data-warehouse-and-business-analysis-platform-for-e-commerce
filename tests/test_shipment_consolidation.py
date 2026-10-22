import unittest

from metrics_api.product_operations import ShipmentCandidate, plan_shipment_consolidation


class ShipmentConsolidationTests(unittest.TestCase):
    def test_waits_when_pending_item_arrives_before_safe_window(self):
        result = plan_shipment_consolidation([
            ShipmentCandidate("o-1", 2, 1, 40, 180, 3),
        ], maximum_wait_minutes=60)
        self.assertEqual("CONSOLIDATE", result["orders"][0]["action"])
        self.assertEqual(1, result["packages_avoided"])
        self.assertFalse(result["shipment_changes_started"])

    def test_ships_now_when_wait_would_miss_cutoff(self):
        result = plan_shipment_consolidation([
            ShipmentCandidate("o-1", 2, 1, 50, 60, 20),
        ], maximum_wait_minutes=60)
        self.assertEqual("SHIP_AVAILABLE_NOW", result["orders"][0]["action"])

    def test_rejects_duplicate_order(self):
        with self.assertRaises(ValueError):
            plan_shipment_consolidation([
                ShipmentCandidate("o", 1, 1, 0, 60, 5),
                ShipmentCandidate("o", 1, 1, 0, 60, 5),
            ], maximum_wait_minutes=10)
