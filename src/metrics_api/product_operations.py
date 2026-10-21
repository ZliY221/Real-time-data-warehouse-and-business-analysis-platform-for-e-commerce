"""Product-level operating insights derived from realtime metric windows."""

from __future__ import annotations

from decimal import Decimal
from math import ceil
from typing import Any


def compare_product_windows(current: list[dict[str, Any]], baseline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return deterministic GMV deltas for matching product dimensions."""
    previous = {str(item["name"]): Decimal(str(item["gmv"])) for item in baseline}
    items: list[dict[str, Any]] = []
    for row in current:
        name = str(row["name"])
        value = Decimal(str(row["gmv"]))
        base = previous.get(name, Decimal("0"))
        delta = value - base
        rate = float(delta / base) if base else None
        items.append({"name": name, "category": row.get("category"), "current_gmv": f"{value:.2f}", "baseline_gmv": f"{base:.2f}", "gmv_delta": f"{delta:.2f}", "gmv_rate": rate, "trend": "UP" if delta > 0 else "DOWN" if delta < 0 else "FLAT"})
    return sorted(items, key=lambda item: abs(Decimal(item["gmv_delta"])), reverse=True)


def product_contribution(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Calculate each product's share of GMV and order volume."""
    total_gmv = sum((Decimal(str(row["gmv"])) for row in rows), Decimal("0"))
    total_orders = sum(int(row["order_count"]) for row in rows)
    items = [{**row, "gmv_share": float(Decimal(str(row["gmv"])) / total_gmv) if total_gmv else 0.0, "order_share": int(row["order_count"]) / total_orders if total_orders else 0.0} for row in rows]
    return sorted(items, key=lambda item: item["gmv_share"], reverse=True)


def product_alerts(comparisons: list[dict[str, Any]], *, rate_threshold: float = 0.25) -> list[dict[str, Any]]:
    """Turn material product movements into explainable operating alerts."""
    if rate_threshold <= 0:
        raise ValueError("rate_threshold must be positive")
    alerts = []
    for item in comparisons:
        rate = item.get("gmv_rate")
        if rate is None or abs(float(rate)) < rate_threshold:
            continue
        alerts.append({"name": item["name"], "severity": "HIGH" if abs(float(rate)) >= rate_threshold * 2 else "MEDIUM", "direction": item["trend"], "gmv_rate": rate, "message": "GMV exceeded the configured movement threshold"})
    return alerts


def resource_plan(*, product_count: int, alert_count: int, refresh_seconds: int) -> dict[str, Any]:
    """Recommend bounded dashboard refresh and query concurrency."""
    if product_count < 0 or alert_count < 0 or refresh_seconds < 5:
        raise ValueError("counts must be non-negative and refresh_seconds at least 5")
    pressure = product_count + alert_count * 5
    mode = "PROTECT" if pressure >= 100 else "BALANCED" if pressure >= 40 else "NORMAL"
    minimum_refresh = 60 if mode == "PROTECT" else 30 if mode == "BALANCED" else 10
    return {"mode": mode, "requested_refresh_seconds": refresh_seconds, "recommended_refresh_seconds": max(refresh_seconds, minimum_refresh), "max_concurrent_queries": 2 if mode == "PROTECT" else 4 if mode == "BALANCED" else 8}


def command_center(current: list[dict[str, Any]], baseline: list[dict[str, Any]]) -> dict[str, Any]:
    """Build one operator-facing snapshot from realtime product windows."""
    comparisons = compare_product_windows(current, baseline)
    alerts = product_alerts(comparisons)
    contributions = product_contribution(current)
    total_gmv = sum((Decimal(str(row["gmv"])) for row in current), Decimal("0"))
    return {"product_count": len(current), "total_gmv": f"{total_gmv:.2f}",
            "alert_count": len(alerts), "top_contributors": contributions[:3],
            "alerts": alerts, "operating_status": "ATTENTION" if alerts else "STABLE"}


def campaign_pacing(*, current_gmv: Decimal, target_gmv: Decimal,
                    elapsed_ratio: float) -> dict[str, Any]:
    """Compare live campaign progress with the expected time pace."""
    if target_gmv <= 0 or current_gmv < 0 or not 0 < elapsed_ratio <= 1:
        raise ValueError("target must be positive, current non-negative and elapsed ratio in (0, 1]")
    progress = float(current_gmv / target_gmv)
    gap = progress - elapsed_ratio
    status = "AHEAD" if gap >= 0.05 else "BEHIND" if gap <= -0.05 else "ON_PACE"
    return {"current_gmv": f"{current_gmv:.2f}", "target_gmv": f"{target_gmv:.2f}",
            "progress_ratio": progress, "elapsed_ratio": elapsed_ratio,
            "pace_gap": gap, "status": status}


def inventory_signal(*, available_units: int, demand_per_hour: float,
                     replenishment_hours: float) -> dict[str, Any]:
    """Estimate stock coverage from live demand without mutating inventory."""
    if available_units < 0 or demand_per_hour < 0 or replenishment_hours < 0:
        raise ValueError("inventory inputs cannot be negative")
    coverage = None if demand_per_hour == 0 else available_units / demand_per_hour
    if coverage is None:
        status = "NO_DEMAND"
    elif coverage < replenishment_hours:
        status = "STOCKOUT_RISK"
    elif coverage < replenishment_hours * 1.5:
        status = "REPLENISH_SOON"
    else:
        status = "HEALTHY"
    return {"available_units": available_units, "demand_per_hour": demand_per_hour,
            "coverage_hours": coverage, "replenishment_hours": replenishment_hours,
            "status": status}


def operating_briefing(*, alert_count: int, campaign_status: str,
                       inventory_status: str) -> dict[str, Any]:
    """Turn realtime conditions into a short, ordered operator checklist."""
    if alert_count < 0:
        raise ValueError("alert_count cannot be negative")
    actions: list[dict[str, str]] = []
    if inventory_status == "STOCKOUT_RISK":
        actions.append({"priority": "P0", "action": "Confirm replenishment and limit promotion exposure"})
    if campaign_status == "BEHIND":
        actions.append({"priority": "P1", "action": "Review traffic, conversion and campaign placement"})
    if alert_count:
        actions.append({"priority": "P1", "action": "Review products with material GMV movement"})
    if not actions:
        actions.append({"priority": "P3", "action": "Continue monitoring current operating window"})
    return {"action_count": len(actions), "actions": actions,
            "briefing_status": "ACTION_REQUIRED" if actions[0]["priority"] in {"P0", "P1"} else "MONITOR"}


def conversion_funnel(*, views: int, carts: int, orders: int) -> dict[str, Any]:
    """Calculate bounded realtime funnel rates and the largest loss stage."""
    if min(views, carts, orders) < 0 or carts > views or orders > carts:
        raise ValueError("funnel counts must be non-negative and non-increasing")
    cart_rate = carts / views if views else 0.0
    order_rate = orders / carts if carts else 0.0
    view_loss = views - carts
    cart_loss = carts - orders
    return {"views": views, "carts": carts, "orders": orders,
            "view_to_cart_rate": cart_rate, "cart_to_order_rate": order_rate,
            "largest_loss_stage": "VIEW_TO_CART" if view_loss >= cart_loss else "CART_TO_ORDER"}


def alert_acknowledgement(*, alert_count: int, owner: str, acknowledged_count: int = 0) -> dict[str, Any]:
    """Track a bounded acknowledgement plan for realtime product alerts."""
    if alert_count < 0 or acknowledged_count < 0 or acknowledged_count > alert_count:
        raise ValueError("acknowledgement counts are invalid")
    if not owner.strip():
        raise ValueError("owner is required")
    remaining = alert_count - acknowledged_count
    return {"owner": owner.strip(), "alert_count": alert_count,
            "acknowledged_count": acknowledged_count, "remaining_count": remaining,
            "status": "COMPLETE" if remaining == 0 else "IN_PROGRESS" if acknowledged_count else "PENDING"}


def campaign_guardrail(*, discount_rate: float, inventory_status: str,
                       campaign_status: str) -> dict[str, Any]:
    """Check promotion launch conditions against margin and stock risk."""
    if not 0 <= discount_rate <= 1:
        raise ValueError("discount_rate must be between 0 and 1")
    blockers = []
    if discount_rate > 0.5:
        blockers.append("discount exceeds 50% review threshold")
    if inventory_status == "STOCKOUT_RISK":
        blockers.append("inventory coverage is below replenishment lead time")
    if campaign_status == "BEHIND" and discount_rate > 0.3:
        blockers.append("campaign is behind while discount is already above 30%")
    return {"discount_rate": discount_rate, "inventory_status": inventory_status,
            "campaign_status": campaign_status, "blockers": blockers,
            "launch_status": "BLOCKED" if blockers else "READY"}


def shift_handoff(*, alert_count: int, unacknowledged_count: int,
                  campaign_status: str, inventory_status: str) -> dict[str, Any]:
    """Create a concise commerce operations handoff summary."""
    if alert_count < 0 or unacknowledged_count < 0 or unacknowledged_count > alert_count:
        raise ValueError("handoff alert counts are invalid")
    actions = []
    if unacknowledged_count:
        actions.append("Acknowledge remaining product alerts")
    if inventory_status in {"STOCKOUT_RISK", "REPLENISH_SOON"}:
        actions.append("Review replenishment plan")
    if campaign_status == "BEHIND":
        actions.append("Review campaign conversion and placement")
    if not actions:
        actions.append("Continue realtime monitoring")
    return {"alert_count": alert_count, "unacknowledged_count": unacknowledged_count,
            "campaign_status": campaign_status, "inventory_status": inventory_status,
            "actions": actions, "handoff_status": "ACTION_REQUIRED" if len(actions) > 1 or unacknowledged_count else "MONITOR"}


def promotion_margin_guardrail(*, selling_price: Decimal, unit_cost: Decimal,
                               discount_rate: float, shipping_subsidy: Decimal,
                               expected_return_rate: float,
                               minimum_margin_rate: float = 0.1) -> dict[str, Any]:
    """Protect contribution margin after discount, subsidy and expected returns."""
    if selling_price <= 0 or unit_cost < 0 or shipping_subsidy < 0:
        raise ValueError("price must be positive and costs cannot be negative")
    if not 0 <= discount_rate < 1 or not 0 <= expected_return_rate < 1:
        raise ValueError("discount and return rates must be in [0, 1)")
    if not 0 <= minimum_margin_rate < 1:
        raise ValueError("minimum_margin_rate must be in [0, 1)")
    discounted_price = selling_price * (Decimal("1") - Decimal(str(discount_rate)))
    expected_revenue = discounted_price * (Decimal("1") - Decimal(str(expected_return_rate)))
    contribution = expected_revenue - unit_cost - shipping_subsidy
    margin_rate = contribution / expected_revenue if expected_revenue else Decimal("-1")
    required_revenue = (unit_cost + shipping_subsidy) / (Decimal("1") - Decimal(str(minimum_margin_rate)))
    denominator = selling_price * (Decimal("1") - Decimal(str(expected_return_rate)))
    maximum_discount = Decimal("1") - required_revenue / denominator if denominator else Decimal("0")
    maximum_discount = max(Decimal("0"), min(Decimal("0.99"), maximum_discount))
    floor = Decimal(str(minimum_margin_rate))
    status = "BLOCKED" if contribution < 0 or margin_rate < floor else "REVIEW" if margin_rate < floor + Decimal("0.05") else "READY"
    reasons = []
    if contribution < 0:
        reasons.append("expected contribution margin is negative")
    elif margin_rate < floor:
        reasons.append("expected margin rate is below the configured floor")
    return {"selling_price": f"{selling_price:.2f}",
            "discounted_price": f"{discounted_price:.2f}",
            "expected_realized_revenue": f"{expected_revenue:.2f}",
            "expected_contribution": f"{contribution:.2f}",
            "expected_margin_rate": float(margin_rate),
            "minimum_margin_rate": minimum_margin_rate,
            "maximum_safe_discount_rate": float(maximum_discount),
            "status": status, "reasons": reasons}


def return_capacity_signal(*, orders: int, return_requests: int,
                           processed_returns: int, existing_backlog: int,
                           handling_rate_per_hour: int, horizon_hours: int = 8,
                           return_rate_threshold: float = 0.15) -> dict[str, Any]:
    """Forecast reverse-logistics capacity from a live return window."""
    if min(orders, return_requests, processed_returns, existing_backlog, handling_rate_per_hour) < 0:
        raise ValueError("return capacity inputs cannot be negative")
    if handling_rate_per_hour < 1 or horizon_hours < 1 or horizon_hours > 168:
        raise ValueError("handling rate and horizon are invalid")
    if not 0 < return_rate_threshold <= 1:
        raise ValueError("return_rate_threshold must be in (0, 1]")
    workload = existing_backlog + return_requests
    completed = min(processed_returns, workload)
    pending = workload - completed
    capacity = handling_rate_per_hour * horizon_hours
    forecast_backlog = max(0, pending - capacity)
    return_rate = return_requests / orders if orders else (1.0 if return_requests else 0.0)
    surge = return_rate >= return_rate_threshold
    if surge and forecast_backlog:
        status = "SURGE_CAPACITY_GAP"
    elif forecast_backlog:
        status = "CAPACITY_GAP"
    elif surge:
        status = "RETURN_SURGE"
    else:
        status = "HEALTHY"
    required_rate = ceil(pending / horizon_hours) if pending else 0
    return {"orders": orders, "return_requests": return_requests,
            "return_rate": return_rate, "return_rate_threshold": return_rate_threshold,
            "existing_backlog": existing_backlog, "processed_returns": completed,
            "pending_returns": pending, "horizon_hours": horizon_hours,
            "available_capacity": capacity, "forecast_backlog": forecast_backlog,
            "recommended_additional_capacity_per_hour": max(0, required_rate - handling_rate_per_hour),
            "status": status}
