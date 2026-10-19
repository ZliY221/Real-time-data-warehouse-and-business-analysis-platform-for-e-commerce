import unittest

from metrics_api.product_operations import compare_product_windows


class ProductOperationsTests(unittest.TestCase):
    def test_comparison_sorts_by_absolute_change(self):
        current = [{"name": "sku-a", "category": "digital", "gmv": "150.00"}, {"name": "sku-b", "category": "home", "gmv": "70.00"}]
        baseline = [{"name": "sku-a", "gmv": "100.00"}, {"name": "sku-b", "gmv": "80.00"}]
        items = compare_product_windows(current, baseline)
        self.assertEqual(["sku-a", "sku-b"], [item["name"] for item in items])
        self.assertEqual("UP", items[0]["trend"])
        self.assertEqual(-0.125, items[1]["gmv_rate"])
