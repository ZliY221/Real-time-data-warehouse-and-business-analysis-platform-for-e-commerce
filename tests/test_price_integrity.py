import unittest

from metrics_api.price_integrity import PriceIntegrityObservation, assess_price_integrity


class PriceIntegrityTests(unittest.TestCase):
    def test_guard_distinguishes_verified_observe_and_hold_prices(self) -> None:
        result = assess_price_integrity([
            PriceIntegrityObservation("sku-1", 100, 90, 10, 10, 50, 1),
            PriceIntegrityObservation("sku-2", 100, 90, 10, 10, 5, 1),
            PriceIntegrityObservation("sku-3", 100, 80, 10, 20, 50, 1),
        ])
        self.assertEqual("PRICE_INTEGRITY_HOLD", result["status"])
        self.assertEqual({"verified": 1, "observe": 1, "hold": 1}, result["counts"])
        self.assertIn("DISCOUNT_EXCEEDS_APPROVAL", result["items"][2]["blockers"])
        self.assertFalse(result["automatic_price_change_started"])

    def test_checkout_mismatch_is_blocked(self) -> None:
        result = assess_price_integrity([
            PriceIntegrityObservation("sku-1", 100, 88, 10, 10, 50, 1)
        ])
        self.assertEqual(["CHECKOUT_PRICE_MISMATCH"], result["items"][0]["blockers"])

    def test_duplicate_sku_is_rejected(self) -> None:
        item = PriceIntegrityObservation("sku-1", 100, 90, 10, 10, 50, 1)
        with self.assertRaises(ValueError):
            assess_price_integrity([item, item])
