"""Evaluate live promotion health before operators change campaign traffic."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PromotionMetric:
    campaign_id: str
    baseline_conversion_rate: float
    live_conversion_rate: float
    baseline_refund_rate: float
    live_refund_rate: float
    baseline_average_order_value: float
    live_average_order_value: float
    sample_orders: int
    data_age_minutes: int


def evaluate_promotion_guard(
    campaigns: list[PromotionMetric],
    *,
    minimum_sample_orders: int = 200,
    maximum_data_age_minutes: int = 5,
    maximum_conversion_drop_points: float = 0.03,
    maximum_refund_increase_points: float = 0.02,
) -> dict[str, Any]:
    """Classify promotions as continue, observe, or hold for manual review."""
    if not campaigns:
        raise ValueError("at least one campaign is required")
    if minimum_sample_orders < 1 or maximum_data_age_minutes < 0:
        raise ValueError("sample and freshness thresholds are invalid")
    if maximum_conversion_drop_points < 0 or maximum_refund_increase_points < 0:
        raise ValueError("guard thresholds must be non-negative")
    ids = [item.campaign_id.strip() for item in campaigns]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("campaign ids must be non-empty and unique")

    results = []
    for item in campaigns:
        rates = (
            item.baseline_conversion_rate,
            item.live_conversion_rate,
            item.baseline_refund_rate,
            item.live_refund_rate,
        )
        if any(value < 0 or value > 1 for value in rates):
            raise ValueError("conversion and refund rates must be between 0 and 1")
        if item.baseline_average_order_value <= 0 or item.live_average_order_value < 0:
            raise ValueError("average order values are invalid")
        if item.sample_orders < 0 or item.data_age_minutes < 0:
            raise ValueError("sample orders and data age are invalid")

        conversion_change = item.live_conversion_rate - item.baseline_conversion_rate
        refund_change = item.live_refund_rate - item.baseline_refund_rate
        aov_change_percent = (
            (item.live_average_order_value - item.baseline_average_order_value)
            / item.baseline_average_order_value * 100
        )
        blockers = []
        if item.data_age_minutes > maximum_data_age_minutes:
            blockers.append("DATA_STALE")
        if conversion_change < -maximum_conversion_drop_points:
            blockers.append("CONVERSION_DROP")
        if refund_change > maximum_refund_increase_points:
            blockers.append("REFUND_RATE_INCREASE")

        if blockers:
            status, action = "HOLD", "PAUSE_EXPANSION_AND_REVIEW"
        elif item.sample_orders < minimum_sample_orders:
            status, action = "OBSERVE", "COLLECT_MORE_ORDERS"
        else:
            status, action = "HEALTHY", "CONTINUE_CURRENT_TRAFFIC"
        results.append({
            **asdict(item),
            "campaign_id": item.campaign_id.strip(),
            "conversion_change_points": round(conversion_change, 4),
            "refund_change_points": round(refund_change, 4),
            "average_order_value_change_percent": round(aov_change_percent, 2),
            "status": status,
            "recommended_action": action,
            "blockers": blockers,
        })

    counts = {
        status.lower(): sum(item["status"] == status for item in results)
        for status in ("HEALTHY", "OBSERVE", "HOLD")
    }
    overall = "HOLD" if counts["hold"] else "OBSERVE" if counts["observe"] else "HEALTHY"
    return {
        "status": f"PROMOTION_GUARD_{overall}",
        "campaign_count": len(results),
        "counts": counts,
        "campaigns": results,
        "automatic_campaign_change_started": False,
    }
