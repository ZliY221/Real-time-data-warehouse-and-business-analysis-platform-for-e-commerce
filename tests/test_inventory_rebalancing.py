import unittest

from metrics_api.product_operations import InventoryNode, plan_inventory_rebalancing


class InventoryRebalancingTests(unittest.TestCase):
    def test_plans_transfer_with_safety_stock_and_capacity(self):
        result = plan_inventory_rebalancing([
            InventoryNode("north", 120, 40, 20, 50, 0),
            InventoryNode("south", 10, 50, 10, 0, 30),
        ])
        self.assertEqual("PARTIAL", result["status"])
        self.assertEqual(30, result["planned_transfer_units"])
        self.assertEqual(20, result["residual_deficit_units"])
        self.assertEqual("north", result["transfers"][0]["from_node"])
        self.assertFalse(result["transfer_started"])

    def test_returns_no_transfer_when_all_nodes_are_healthy(self):
        result = plan_inventory_rebalancing([
            InventoryNode("east", 80, 50, 20, 10, 10),
        ])
        self.assertEqual("NO_TRANSFER_NEEDED", result["status"])
        self.assertEqual([], result["transfers"])

    def test_duplicate_node_is_rejected(self):
        with self.assertRaises(ValueError):
            plan_inventory_rebalancing([
                InventoryNode("east", 10, 10, 1, 1, 1),
                InventoryNode("east", 10, 10, 1, 1, 1),
            ])
