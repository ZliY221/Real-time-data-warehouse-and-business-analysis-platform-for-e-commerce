import unittest

from metrics_api.product_operations import PackingWaveOrder, plan_packing_waves


class PackingWavePlanTests(unittest.TestCase):
    def test_assigns_earliest_cutoff_across_stations(self):
        result = plan_packing_waves([
            PackingWaveOrder("late-cutoff", 20, 80, 90),
            PackingWaveOrder("early-a", 30, 40, 50),
            PackingWaveOrder("early-b", 20, 40, 80),
        ], station_count=2)
        self.assertEqual("READY", result["status"])
        self.assertEqual(["early-b", "early-a", "late-cutoff"],
                         [row["order_id"] for row in result["assignments"]])
        self.assertFalse(result["packing_tasks_dispatched"])

    def test_marks_order_at_risk_when_capacity_misses_cutoff(self):
        result = plan_packing_waves([
            PackingWaveOrder("a", 30, 20, 100),
        ], station_count=1)
        self.assertEqual("AT_RISK", result["status"])
        self.assertEqual(-10, result["assignments"][0]["slack_minutes"])

    def test_rejects_duplicate_order(self):
        with self.assertRaises(ValueError):
            plan_packing_waves([
                PackingWaveOrder("a", 10, 20, 50),
                PackingWaveOrder("a", 10, 30, 50),
            ], station_count=1)
