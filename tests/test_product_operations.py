import unittest

from decimal import Decimal

from metrics_api.product_operations import campaign_pacing, command_center, compare_product_windows, product_alerts, product_contribution, resource_plan


class ProductOperationsTests(unittest.TestCase):
    def test_comparison_sorts_by_absolute_change(self):
        current = [{"name": "sku-a", "category": "digital", "gmv": "150.00"}, {"name": "sku-b", "category": "home", "gmv": "70.00"}]
        baseline = [{"name": "sku-a", "gmv": "100.00"}, {"name": "sku-b", "gmv": "80.00"}]
        items = compare_product_windows(current, baseline)
        self.assertEqual(["sku-a", "sku-b"], [item["name"] for item in items])
        self.assertEqual("UP", items[0]["trend"])
        self.assertEqual(-0.125, items[1]["gmv_rate"])

    def test_contribution_calculates_gmv_and_order_shares(self):
        items = product_contribution([{"name": "a", "gmv": "75", "order_count": 3}, {"name": "b", "gmv": "25", "order_count": 1}])
        self.assertEqual(0.75, items[0]["gmv_share"])
        self.assertEqual(0.75, items[0]["order_share"])

    def test_alerts_keep_only_material_movements(self):
        items = product_alerts([{"name": "a", "gmv_rate": 0.7, "trend": "UP"}, {"name": "b", "gmv_rate": 0.1, "trend": "UP"}], rate_threshold=0.25)
        self.assertEqual(1, len(items))
        self.assertEqual("HIGH", items[0]["severity"])

    def test_resource_plan_throttles_high_pressure_queries(self):
        plan = resource_plan(product_count=80, alert_count=6, refresh_seconds=10)
        self.assertEqual("PROTECT", plan["mode"])
        self.assertEqual(60, plan["recommended_refresh_seconds"])
        self.assertEqual(2, plan["max_concurrent_queries"])

    def test_command_center_combines_value_and_alerts(self):
        snapshot = command_center([{"name": "a", "gmv": "150", "order_count": 3}], [{"name": "a", "gmv": "100"}])
        self.assertEqual("150.00", snapshot["total_gmv"])
        self.assertEqual("ATTENTION", snapshot["operating_status"])

    def test_campaign_pacing_highlights_behind_target(self):
        pace = campaign_pacing(current_gmv=Decimal("400"), target_gmv=Decimal("1000"), elapsed_ratio=0.6)
        self.assertEqual("BEHIND", pace["status"])
        self.assertAlmostEqual(-0.2, pace["pace_gap"])
