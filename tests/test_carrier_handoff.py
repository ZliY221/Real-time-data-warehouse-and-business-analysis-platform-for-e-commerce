import unittest

from metrics_api.product_operations import (
    CarrierHandoffShipment,
    CarrierPickupSlot,
    reserve_carrier_handoffs,
)


class CarrierHandoffTests(unittest.TestCase):
    def test_reserves_earliest_feasible_slot_by_priority(self):
        result = reserve_carrier_handoffs([
            CarrierHandoffShipment("normal", 10, 80, 50),
            CarrierHandoffShipment("express", 10, 50, 100),
        ], [
            CarrierPickupSlot("slot-1", 30, 1),
            CarrierPickupSlot("slot-2", 60, 1),
        ])
        self.assertEqual("READY", result["status"])
        self.assertEqual("express", result["reservations"][0]["shipment_id"])
        self.assertEqual("slot-1", result["reservations"][0]["slot_id"])
        self.assertFalse(result["carrier_booking_started"])

    def test_reports_unassigned_when_no_slot_meets_cutoff(self):
        result = reserve_carrier_handoffs([
            CarrierHandoffShipment("late", 40, 50, 90),
        ], [CarrierPickupSlot("slot", 60, 2)])
        self.assertEqual("PARTIAL", result["status"])
        self.assertEqual(1, result["unassigned_count"])

    def test_rejects_duplicate_slot_id(self):
        with self.assertRaises(ValueError):
            reserve_carrier_handoffs([
                CarrierHandoffShipment("s", 1, 20, 50),
            ], [CarrierPickupSlot("x", 10, 1), CarrierPickupSlot("x", 20, 1)])
