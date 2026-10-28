"""Plan safe recovery actions for failed ecommerce payments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PaymentFailureObservation:
    order_id: str
    failure_code: str
    retry_count: int
    payment_age_minutes: int
    inventory_reserved: bool
    customer_session_active: bool
    order_amount: float


def plan_payment_recovery(
    observations: list[PaymentFailureObservation],
    *,
    maximum_retries: int = 2,
    reservation_timeout_minutes: int = 30,
) -> dict[str, Any]:
    """Return recovery guidance without charging customers or changing inventory."""
    if not observations or maximum_retries < 0 or reservation_timeout_minutes < 1:
        raise ValueError("observations and recovery thresholds must be valid")
    order_ids = [item.order_id.strip() for item in observations]
    if any(not order_id for order_id in order_ids) or len(order_ids) != len(set(order_ids)):
        raise ValueError("order ids must be non-empty and unique")

    items = []
    manual_codes = {"FRAUD_REVIEW", "CARD_DECLINED", "ACCOUNT_RESTRICTED"}
    for item in observations:
        code = item.failure_code.strip().upper()
        if not code or item.retry_count < 0 or item.payment_age_minutes < 0 or item.order_amount <= 0:
            raise ValueError("payment observation is invalid")
        if code in manual_codes:
            status, action, reason = "REVIEW", "MANUAL_PAYMENT_REVIEW", "PAYMENT_REQUIRES_REVIEW"
        elif not item.inventory_reserved:
            status, action, reason = "CLOSED", "REQUEST_NEW_CHECKOUT", "INVENTORY_NOT_RESERVED"
        elif item.payment_age_minutes >= reservation_timeout_minutes:
            status, action, reason = "EXPIRED", "RELEASE_RESERVATION_AFTER_CONFIRMATION", "RESERVATION_TIMEOUT"
        elif item.retry_count >= maximum_retries:
            status, action, reason = "REVIEW", "ESCALATE_PAYMENT_SUPPORT", "RETRY_LIMIT_REACHED"
        elif item.customer_session_active:
            status, action, reason = "RECOVERABLE", "OFFER_ALTERNATIVE_PAYMENT", "ACTIVE_CHECKOUT_SESSION"
        else:
            status, action, reason = "RECOVERABLE", "QUEUE_CUSTOMER_INITIATED_RETRY", "SAFE_RETRY_WINDOW"
        items.append({
            **asdict(item),
            "order_id": item.order_id.strip(),
            "failure_code": code,
            "status": status,
            "recommended_action": action,
            "reason": reason,
            "recoverable_value": round(item.order_amount, 2) if status == "RECOVERABLE" else 0.0,
            "requires_confirmation": status != "RECOVERABLE",
        })

    order = {"REVIEW": 0, "EXPIRED": 1, "RECOVERABLE": 2, "CLOSED": 3}
    items.sort(key=lambda item: (order[item["status"]], -item["order_amount"], item["order_id"]))
    counts = {
        status.lower(): sum(item["status"] == status for item in items)
        for status in order
    }
    return {
        "status": "PAYMENT_RECOVERY_ATTENTION" if counts["review"] or counts["expired"] else "PAYMENT_RECOVERY_READY",
        "order_count": len(items),
        "counts": counts,
        "recoverable_value": round(sum(item["recoverable_value"] for item in items), 2),
        "items": items,
        "automatic_payment_started": False,
        "automatic_inventory_change_started": False,
    }
