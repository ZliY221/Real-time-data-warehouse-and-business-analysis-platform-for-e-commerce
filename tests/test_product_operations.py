import unittest

from decimal import Decimal

from metrics_api.product_operations import alert_acknowledgement, campaign_guardrail, campaign_pacing, command_center, compare_product_windows, conversion_funnel, inventory_signal, operating_briefing, product_alerts, product_contribution, promotion_margin_guardrail, resource_plan, return_capacity_signal, shift_handoff


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

    def test_inventory_signal_detects_stockout_risk(self):
        signal = inventory_signal(available_units=20, demand_per_hour=10, replenishment_hours=5)
        self.assertEqual("STOCKOUT_RISK", signal["status"])
        self.assertEqual(2.0, signal["coverage_hours"])

    def test_briefing_orders_stockout_before_campaign(self):
        briefing = operating_briefing(alert_count=2, campaign_status="BEHIND", inventory_status="STOCKOUT_RISK")
        self.assertEqual("P0", briefing["actions"][0]["priority"])
        self.assertEqual("ACTION_REQUIRED", briefing["briefing_status"])

    def test_conversion_funnel_identifies_largest_loss(self):
        funnel = conversion_funnel(views=1000, carts=200, orders=100)
        self.assertEqual("VIEW_TO_CART", funnel["largest_loss_stage"])
        self.assertEqual(0.5, funnel["cart_to_order_rate"])

    def test_alert_acknowledgement_tracks_remaining_work(self):
        result = alert_acknowledgement(alert_count=5, owner="commerce-oncall", acknowledged_count=2)
        self.assertEqual(3, result["remaining_count"])
        self.assertEqual("IN_PROGRESS", result["status"])

    def test_campaign_guardrail_blocks_stockout_risk(self):
        result = campaign_guardrail(discount_rate=0.2, inventory_status="STOCKOUT_RISK", campaign_status="ON_PACE")
        self.assertEqual("BLOCKED", result["launch_status"])
        self.assertEqual(1, len(result["blockers"]))

    def test_shift_handoff_combines_pending_actions(self):
        result = shift_handoff(alert_count=4, unacknowledged_count=2, campaign_status="BEHIND", inventory_status="REPLENISH_SOON")
        self.assertEqual("ACTION_REQUIRED", result["handoff_status"])
        self.assertEqual(3, len(result["actions"]))

    def test_promotion_margin_blocks_unprofitable_discount(self):
        result = promotion_margin_guardrail(
            selling_price=Decimal("100"), unit_cost=Decimal("62"),
            discount_rate=0.30, shipping_subsidy=Decimal("5"),
            expected_return_rate=0.10, minimum_margin_rate=0.10,
        )
        self.assertEqual("BLOCKED", result["status"])
        self.assertLess(result["maximum_safe_discount_rate"], 0.30)
        self.assertEqual(1, len(result["reasons"]))

    def test_return_capacity_exposes_surge_and_backlog(self):
        result = return_capacity_signal(
            orders=1000, return_requests=200, processed_returns=20,
            existing_backlog=100, handling_rate_per_hour=20, horizon_hours=8,
        )
        self.assertEqual("SURGE_CAPACITY_GAP", result["status"])
        self.assertEqual(120, result["forecast_backlog"])
        self.assertEqual(15, result["recommended_additional_capacity_per_hour"])
