import unittest

from metrics_api.promotion_guard import PromotionMetric, evaluate_promotion_guard


class PromotionGuardTests(unittest.TestCase):
    def test_guard_distinguishes_healthy_observe_and_hold_campaigns(self) -> None:
        result = evaluate_promotion_guard([
            PromotionMetric("healthy", 0.12, 0.13, 0.03, 0.03, 120, 125, 500, 1),
            PromotionMetric("observe", 0.12, 0.12, 0.03, 0.03, 120, 120, 50, 1),
            PromotionMetric("hold", 0.12, 0.08, 0.03, 0.06, 120, 110, 500, 1),
        ])
        self.assertEqual("PROMOTION_GUARD_HOLD", result["status"])
        self.assertEqual({"healthy": 1, "observe": 1, "hold": 1}, result["counts"])
        self.assertIn("CONVERSION_DROP", result["campaigns"][2]["blockers"])
        self.assertFalse(result["automatic_campaign_change_started"])

    def test_stale_data_blocks_an_otherwise_healthy_campaign(self) -> None:
        result = evaluate_promotion_guard([
            PromotionMetric("late", 0.12, 0.13, 0.03, 0.03, 120, 125, 500, 8)
        ])
        self.assertEqual(["DATA_STALE"], result["campaigns"][0]["blockers"])

    def test_duplicate_campaigns_are_rejected(self) -> None:
        metric = PromotionMetric("same", 0.1, 0.1, 0.02, 0.02, 100, 100, 300, 1)
        with self.assertRaises(ValueError):
            evaluate_promotion_guard([metric, metric])
