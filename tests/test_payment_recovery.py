import unittest

from metrics_api.payment_recovery import PaymentFailureObservation, plan_payment_recovery


class PaymentRecoveryTests(unittest.TestCase):
    def test_plan_separates_recoverable_review_and_expired_orders(self) -> None:
        result = plan_payment_recovery([
            PaymentFailureObservation("o-1", "gateway_timeout", 0, 5, True, True, 199.0),
            PaymentFailureObservation("o-2", "card_declined", 0, 3, True, True, 299.0),
            PaymentFailureObservation("o-3", "gateway_timeout", 1, 40, True, False, 99.0),
        ])
        self.assertEqual("PAYMENT_RECOVERY_ATTENTION", result["status"])
        self.assertEqual({"review": 1, "expired": 1, "recoverable": 1, "closed": 0}, result["counts"])
        self.assertEqual(199.0, result["recoverable_value"])
        self.assertFalse(result["automatic_payment_started"])
        self.assertFalse(result["automatic_inventory_change_started"])

    def test_retry_limit_requires_support_review(self) -> None:
        result = plan_payment_recovery([
            PaymentFailureObservation("o-1", "gateway_timeout", 2, 5, True, False, 88.0)
        ])
        self.assertEqual("ESCALATE_PAYMENT_SUPPORT", result["items"][0]["recommended_action"])

    def test_duplicate_order_is_rejected(self) -> None:
        item = PaymentFailureObservation("same", "timeout", 0, 1, True, True, 10.0)
        with self.assertRaises(ValueError):
            plan_payment_recovery([item, item])
