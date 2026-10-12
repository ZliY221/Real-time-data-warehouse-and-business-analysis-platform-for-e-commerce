"""Reconcile notification delivery receipts into a route-level ledger."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any

from .notifications import CHANNEL_PATTERN, parse_delivery_ledger


def _timestamp(value: Any) -> str:
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("receipt attempted_at must be ISO 8601") from error
    if parsed.tzinfo is None:
        raise ValueError("receipt attempted_at must include a timezone")
    return parsed.isoformat().replace("+00:00", "Z")


def reconcile_delivery_receipts(
    outbox: dict[str, Any],
    receipt_document: dict[str, Any],
    delivery_ledger: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply successful route receipts without marking partial events complete."""
    if outbox.get("outbox_version") != "1.0" or not isinstance(outbox.get("events"), list):
        raise ValueError("unsupported notification outbox")
    if receipt_document.get("receipt_version") != "1.0" or not isinstance(
        receipt_document.get("receipts"), list
    ):
        raise ValueError("unsupported receipt document")
    delivered_events, delivered_routes = parse_delivery_ledger(delivery_ledger)
    events: dict[str, dict[str, Any]] = {}
    for event in outbox["events"]:
        if not isinstance(event, dict):
            raise ValueError("notification events must be objects")
        event_id = str(event.get("event_id", ""))
        channels = event.get("channels")
        if not event_id or event_id in events or not isinstance(channels, list) or not channels:
            raise ValueError("notification events must have unique IDs and channels")
        normalized_channels = [str(channel) for channel in channels]
        if len(set(normalized_channels)) != len(normalized_channels) or any(
            not CHANNEL_PATTERN.fullmatch(channel) for channel in normalized_channels
        ):
            raise ValueError("notification event channels are invalid")
        events[event_id] = {**event, "channels": normalized_channels}

    receipt_status: dict[tuple[str, str], str] = {}
    for receipt in receipt_document["receipts"]:
        if not isinstance(receipt, dict):
            raise ValueError("delivery receipts must be objects")
        event_id = str(receipt.get("event_id", ""))
        channel = str(receipt.get("channel", ""))
        key = (event_id, channel)
        if event_id not in events or channel not in events[event_id]["channels"]:
            raise ValueError("delivery receipt does not match the outbox")
        if key in receipt_status:
            raise ValueError("delivery receipts must be unique by event and channel")
        status = str(receipt.get("status", ""))
        if status not in {"DELIVERED", "FAILED"}:
            raise ValueError("delivery receipt status must be DELIVERED or FAILED")
        attempted_at = _timestamp(receipt.get("attempted_at", ""))
        receipt_status[key] = status
        if status == "DELIVERED" and key not in delivered_routes:
            delivered_routes[key] = attempted_at

    event_results: list[dict[str, Any]] = []
    for event_id, event in sorted(events.items()):
        channels = event["channels"]
        delivered_count = sum((event_id, channel) in delivered_routes for channel in channels)
        failed_count = sum(
            receipt_status.get((event_id, channel)) == "FAILED" for channel in channels
        )
        if delivered_count == len(channels):
            status = "DELIVERED"
            delivered_events.add(event_id)
        elif delivered_count:
            status = "PARTIAL"
        elif failed_count:
            status = "FAILED"
        else:
            status = "PENDING"
        event_results.append(
            {
                "event_id": event_id,
                "status": status,
                "required_channel_count": len(channels),
                "delivered_channel_count": delivered_count,
                "failed_channel_count": failed_count,
            }
        )

    ledger = {
        "ledger_version": "1.0",
        "delivered_event_ids": sorted(delivered_events),
        "delivered_routes": [
            {"event_id": event_id, "channel": channel, "delivered_at": delivered_at}
            for (event_id, channel), delivered_at in sorted(delivered_routes.items())
        ],
    }
    complete = all(row["status"] == "DELIVERED" for row in event_results)
    report = {
        "receipt_report_version": "1.0",
        "status": "COMPLETE" if complete else "PARTIAL",
        "event_count": len(event_results),
        "delivered_event_count": sum(row["status"] == "DELIVERED" for row in event_results),
        "events": event_results,
    }
    return ledger, report


def _write_json_atomic(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def update_delivery_ledger(
    outbox_path: Path,
    receipts_path: Path,
    ledger_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    existing = (
        json.loads(ledger_path.read_text(encoding="utf-8"))
        if ledger_path.is_file()
        else None
    )
    ledger, report = reconcile_delivery_receipts(
        json.loads(outbox_path.read_text(encoding="utf-8")),
        json.loads(receipts_path.read_text(encoding="utf-8")),
        existing,
    )
    _write_json_atomic(ledger_path, ledger)
    _write_json_atomic(report_path, report)
    return report
