"""Generate deterministic, privacy-safe ecommerce order events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import random
import uuid


REGIONS = ("辽宁", "北京", "上海", "广东", "四川")
CHANNELS = ("app", "web", "mini_program")
CATALOG = (
    ("SKU-1001", "数码配件", Decimal("39.90")),
    ("SKU-1002", "数码配件", Decimal("89.00")),
    ("SKU-2001", "办公用品", Decimal("12.50")),
    ("SKU-2002", "办公用品", Decimal("25.80")),
    ("SKU-3001", "生活用品", Decimal("56.00")),
    ("SKU-3002", "生活用品", Decimal("109.90")),
)


def _utc_text(value: datetime) -> str:
    utc_value = value.astimezone(timezone.utc)
    timespec = "microseconds" if utc_value.microsecond else "seconds"
    return utc_value.isoformat(timespec=timespec).replace("+00:00", "Z")


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def generate_order_events(
    count: int,
    *,
    seed: int = 2027,
    start_time: datetime | None = None,
    events_per_second: int | None = None,
) -> list[dict[str, object]]:
    """Return deterministic order-created events.

    The same count, seed and start_time always produce identical output. No
    generated field maps to a real person or real order.
    """

    if count < 0:
        raise ValueError("count must be zero or greater")
    if events_per_second is not None and events_per_second <= 0:
        raise ValueError("events_per_second must be greater than zero")

    base_time = start_time or datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)
    if base_time.tzinfo is None:
        raise ValueError("start_time must include timezone information")

    rng = random.Random(seed)
    namespace = uuid.uuid5(uuid.NAMESPACE_URL, f"ecommerce-order-events:{seed}")
    events: list[dict[str, object]] = []

    for index in range(count):
        if events_per_second is None:
            event_time = base_time + timedelta(seconds=index * 3)
        else:
            event_time = base_time + timedelta(
                microseconds=(index * 1_000_000) // events_per_second
            )
        simulated_delay = rng.randint(0, 15)
        ingest_time = event_time + timedelta(seconds=simulated_delay)
        item_count = rng.randint(1, 3)
        selected_products = rng.sample(CATALOG, k=item_count)
        items: list[dict[str, object]] = []
        total_amount = Decimal("0.00")

        for sku_id, category, unit_price in selected_products:
            quantity = rng.randint(1, 5)
            line_amount = unit_price * quantity
            total_amount += line_amount
            items.append(
                {
                    "sku_id": sku_id,
                    "category": category,
                    "quantity": quantity,
                    "unit_price": _money(unit_price),
                    "line_amount": _money(line_amount),
                }
            )

        order_id = f"ord_{seed}_{index:08d}"
        event_uuid = uuid.uuid5(namespace, order_id)
        events.append(
            {
                "schema_version": "1.0",
                "event_id": f"evt_{event_uuid.hex}",
                "event_type": "order_created",
                "event_time": _utc_text(event_time),
                "ingest_time": _utc_text(ingest_time),
                "source": "order-service",
                "payload": {
                    "order_id": order_id,
                    "user_id": f"usr_{rng.randint(1, 500):05d}",
                    "region": rng.choice(REGIONS),
                    "channel": rng.choice(CHANNELS),
                    "currency": "CNY",
                    "total_amount": _money(total_amount),
                    "items": items,
                },
            }
        )

    return events

