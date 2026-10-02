"""Dependency-free validation for the order-created v1 business contract."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .generator import CHANNELS, REGIONS


ENVELOPE_KEYS = {
    "schema_version",
    "event_id",
    "event_type",
    "event_time",
    "ingest_time",
    "source",
    "payload",
}
PAYLOAD_KEYS = {
    "order_id",
    "user_id",
    "region",
    "channel",
    "currency",
    "total_amount",
    "items",
}
ITEM_KEYS = {"sku_id", "category", "quantity", "unit_price", "line_amount"}


def _parse_utc_timestamp(value: Any, field: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        errors.append(f"{field} must be a UTC timestamp ending with Z")
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field} must be valid ISO 8601")
        return None


def _parse_money(value: Any, field: str, errors: list[str]) -> Decimal | None:
    if not isinstance(value, str):
        errors.append(f"{field} must be a decimal string")
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        errors.append(f"{field} must be a valid decimal string")
        return None
    if parsed <= 0 or parsed.as_tuple().exponent != -2:
        errors.append(f"{field} must be positive with exactly two decimal places")
        return None
    return parsed


def validate_order_event(event: Any) -> list[str]:
    """Return human-readable contract violations; an empty list means valid."""

    errors: list[str] = []
    if not isinstance(event, dict):
        return ["event must be an object"]

    if set(event) != ENVELOPE_KEYS:
        errors.append("event envelope fields do not match the v1 contract")
    if event.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if event.get("event_type") != "order_created":
        errors.append("event_type must be order_created")
    if event.get("source") != "order-service":
        errors.append("source must be order-service")
    if not isinstance(event.get("event_id"), str) or not event["event_id"]:
        errors.append("event_id must be a non-empty string")

    event_time = _parse_utc_timestamp(event.get("event_time"), "event_time", errors)
    ingest_time = _parse_utc_timestamp(event.get("ingest_time"), "ingest_time", errors)
    if event_time and ingest_time and ingest_time < event_time:
        errors.append("ingest_time must not be earlier than event_time")

    payload = event.get("payload")
    if not isinstance(payload, dict):
        errors.append("payload must be an object")
        return errors
    if set(payload) != PAYLOAD_KEYS:
        errors.append("payload fields do not match the v1 contract")
    if not isinstance(payload.get("order_id"), str) or not payload["order_id"]:
        errors.append("order_id must be a non-empty string")
    if not isinstance(payload.get("user_id"), str) or not payload["user_id"]:
        errors.append("user_id must be a non-empty string")
    if payload.get("region") not in REGIONS:
        errors.append("region is not supported")
    if payload.get("channel") not in CHANNELS:
        errors.append("channel is not supported")
    if payload.get("currency") != "CNY":
        errors.append("currency must be CNY")

    total_amount = _parse_money(payload.get("total_amount"), "total_amount", errors)
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        errors.append("items must be a non-empty array")
        return errors

    line_total = Decimal("0.00")
    for index, item in enumerate(items):
        prefix = f"items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if set(item) != ITEM_KEYS:
            errors.append(f"{prefix} fields do not match the v1 contract")
        if not isinstance(item.get("sku_id"), str) or not item["sku_id"]:
            errors.append(f"{prefix}.sku_id must be a non-empty string")
        if not isinstance(item.get("category"), str) or not item["category"]:
            errors.append(f"{prefix}.category must be a non-empty string")
        quantity = item.get("quantity")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or not 1 <= quantity <= 5:
            errors.append(f"{prefix}.quantity must be an integer from 1 to 5")
            quantity = None
        unit_price = _parse_money(item.get("unit_price"), f"{prefix}.unit_price", errors)
        line_amount = _parse_money(item.get("line_amount"), f"{prefix}.line_amount", errors)
        if quantity is not None and unit_price is not None and line_amount is not None:
            if unit_price * quantity != line_amount:
                errors.append(f"{prefix}.line_amount does not equal quantity times unit_price")
            line_total += line_amount

    if total_amount is not None and line_total != total_amount:
        errors.append("total_amount does not equal the sum of item line amounts")
    return errors

