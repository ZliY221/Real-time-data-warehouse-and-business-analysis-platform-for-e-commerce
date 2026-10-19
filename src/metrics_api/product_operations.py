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
