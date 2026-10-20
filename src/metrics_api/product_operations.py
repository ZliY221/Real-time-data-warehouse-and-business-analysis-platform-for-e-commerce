"""Product-level operating insights derived from realtime metric windows."""

from __future__ import annotations

from decimal import Decimal
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
