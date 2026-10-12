"""Build an idempotent notification outbox from SLO incident state."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any


CHANNEL_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


def parse_delivery_ledger(
    delivery_ledger: dict[str, Any] | None,
) -> tuple[set[str], dict[tuple[str, str], str]]:
    """Validate the delivery ledger and return event and route completion state."""
    ledger = delivery_ledger or {
        "ledger_version": "1.0",
        "delivered_event_ids": [],
        "delivered_routes": [],
    }
    if ledger.get("ledger_version") != "1.0":
        raise ValueError("unsupported delivery ledger")
    event_ids = ledger.get("delivered_event_ids")
    route_rows = ledger.get("delivered_routes", [])
    if not isinstance(event_ids, list) or not isinstance(route_rows, list):
        raise ValueError("unsupported delivery ledger")
    delivered_events = {str(value) for value in event_ids}
    if len(delivered_events) != len(event_ids) or "" in delivered_events:
        raise ValueError("delivery ledger event IDs must be non-empty and unique")
    delivered_routes: dict[tuple[str, str], str] = {}
    for row in route_rows:
        if not isinstance(row, dict):
            raise ValueError("delivery ledger routes must be objects")
        event_id = str(row.get("event_id", ""))
        channel = str(row.get("channel", ""))
        delivered_at = str(row.get("delivered_at", ""))
        if not event_id or not CHANNEL_PATTERN.fullmatch(channel) or not delivered_at:
            raise ValueError("delivery ledger contains an invalid route")
        key = (event_id, channel)
        if key in delivered_routes:
            raise ValueError("delivery ledger routes must be unique")
        delivered_routes[key] = delivered_at
    return delivered_events, delivered_routes


def _event_id(incident_id: str, event_type: str) -> str:
    material = f"{incident_id}:{event_type}".encode("utf-8")
    return f"evt-{hashlib.sha256(material).hexdigest()[:24]}"


def plan_notifications(
    incident_state: dict[str, Any],
    routing_policy: dict[str, Any],
    delivery_ledger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return undelivered open and resolution events with stable identifiers."""
    if incident_state.get("state_version") != "1.0":
        raise ValueError("unsupported incident state version")
    incidents = incident_state.get("incidents")
    if not isinstance(incidents, list):
        raise ValueError("incident state must contain an incidents list")
    routes = routing_policy.get("severity_routes")
    if not isinstance(routes, dict) or not routes:
        raise ValueError("routing policy must contain severity_routes")
    normalized_routes: dict[str, list[str]] = {}
    for severity, channels in routes.items():
        if not isinstance(channels, list) or not channels:
            raise ValueError(f"severity route {severity} must contain channels")
        values = [str(channel) for channel in channels]
        invalid_channel = any(not CHANNEL_PATTERN.fullmatch(value) for value in values)
        if len(set(values)) != len(values) or invalid_channel:
            raise ValueError(f"severity route {severity} contains invalid channels")
        normalized_routes[str(severity)] = sorted(values)

    delivered, delivered_routes = parse_delivery_ledger(delivery_ledger)

    events: list[dict[str, Any]] = []
    seen_incidents: set[str] = set()
    for incident in incidents:
        incident_id = str(incident.get("incident_id", ""))
        severity = str(incident.get("severity", ""))
        status = str(incident.get("status", ""))
        if not incident_id or incident_id in seen_incidents:
            raise ValueError("incident IDs must be non-empty and unique")
        if severity not in normalized_routes:
            raise ValueError(f"no notification route for severity: {severity}")
        if status not in {"OPEN", "RESOLVED"}:
            raise ValueError(f"unsupported incident status: {status}")
        seen_incidents.add(incident_id)
        lifecycle = [("INCIDENT_OPENED", incident.get("first_seen_at"))]
        if status == "RESOLVED":
            lifecycle.append(("INCIDENT_RESOLVED", incident.get("resolved_at")))
        for event_type, occurred_at in lifecycle:
            if not occurred_at:
                raise ValueError(f"{event_type} requires an occurrence timestamp")
            event_id = _event_id(incident_id, event_type)
            if event_id in delivered:
                continue
            pending_channels = [
                channel
                for channel in normalized_routes[severity]
                if (event_id, channel) not in delivered_routes
            ]
            if not pending_channels:
                continue
            events.append(
                {
                    "event_id": event_id,
                    "event_type": event_type,
                    "incident_id": incident_id,
                    "alert_id": str(incident.get("alert_id", "unknown")),
                    "tier": str(incident.get("tier", "unknown")),
                    "rule_id": str(incident.get("rule_id", "unknown")),
                    "severity": severity,
                    "occurred_at": str(occurred_at),
                    "channels": pending_channels,
                }
            )
    events.sort(key=lambda row: (row["occurred_at"], row["event_id"]))
    return {
        "outbox_version": "1.0",
        "status": "PENDING" if events else "EMPTY",
        "routing_policy_version": str(routing_policy.get("policy_version", "unknown")),
        "pending_event_count": len(events),
        "events": events,
    }


def write_notification_plan(
    state_path: Path, policy_path: Path, ledger_path: Path | None, output_path: Path
) -> dict[str, Any]:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    ledger = (
        json.loads(ledger_path.read_text(encoding="utf-8"))
        if ledger_path is not None and ledger_path.is_file()
        else None
    )
    outbox = plan_notifications(state, policy, ledger)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(outbox, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return outbox
