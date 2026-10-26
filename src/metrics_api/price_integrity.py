"""Protect checkout traffic from stale or inconsistent promotional prices."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PriceIntegrityObservation:
    sku: str
    catalog_price: float
    checkout_price: float
    approved_discount_percent: float
    observed_discount_percent: float
    sample_orders: int
    data_age_minutes: int


def assess_price_integrity(
    observations: list[PriceIntegrityObservation],
    *,
    minimum_sample_orders: int = 20,
    maximum_data_age_minutes: int = 5,
    price_tolerance: float = 0.01,
) -> dict[str, Any]:
    """Return SKU-level integrity decisions without changing prices."""
    if not observations:
        raise ValueError("at least one price observation is required")
    if minimum_sample_orders < 1 or maximum_data_age_minutes < 0 or price_tolerance < 0:
        raise ValueError("price integrity thresholds are invalid")
    skus = [item.sku.strip() for item in observations]
    if any(not sku for sku in skus) or len(skus) != len(set(skus)):
        raise ValueError("sku values must be non-empty and unique")

    items = []
    for item in observations:
        if item.catalog_price <= 0 or item.checkout_price < 0:
            raise ValueError("catalog and checkout prices are invalid")
        if not 0 <= item.approved_discount_percent <= 100:
            raise ValueError("approved discount must be between 0 and 100")
        if not 0 <= item.observed_discount_percent <= 100:
            raise ValueError("observed discount must be between 0 and 100")
        if item.sample_orders < 0 or item.data_age_minutes < 0:
            raise ValueError("sample orders and data age are invalid")

        expected_price = item.catalog_price * (1 - item.observed_discount_percent / 100)
        difference = item.checkout_price - expected_price
        blockers = []
        if item.data_age_minutes > maximum_data_age_minutes:
            blockers.append("PRICE_DATA_STALE")
        if item.observed_discount_percent > item.approved_discount_percent:
            blockers.append("DISCOUNT_EXCEEDS_APPROVAL")
        if abs(difference) > price_tolerance:
            blockers.append("CHECKOUT_PRICE_MISMATCH")

        if blockers:
            status, action = "HOLD", "STOP_PRICE_EXPANSION_AND_REVIEW"
        elif item.sample_orders < minimum_sample_orders:
            status, action = "OBSERVE", "COLLECT_MORE_CHECKOUT_SAMPLES"
        else:
            status, action = "VERIFIED", "KEEP_CURRENT_PRICE"
        items.append({
            **asdict(item),
            "sku": item.sku.strip(),
            "expected_checkout_price": round(expected_price, 2),
            "checkout_difference": round(difference, 2),
            "status": status,
            "recommended_action": action,
            "blockers": blockers,
        })

    counts = {
        status.lower(): sum(item["status"] == status for item in items)
        for status in ("VERIFIED", "OBSERVE", "HOLD")
    }
    overall = "HOLD" if counts["hold"] else "OBSERVE" if counts["observe"] else "VERIFIED"
    return {
        "status": f"PRICE_INTEGRITY_{overall}",
        "sku_count": len(items),
        "counts": counts,
        "items": items,
        "automatic_price_change_started": False,
    }
