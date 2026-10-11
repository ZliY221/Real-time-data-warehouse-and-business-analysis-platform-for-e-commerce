"""Maintain a deterministic lifecycle for operational SLO alerts."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def _timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("observed_at must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError("observed_at must include a timezone")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _new_incident(alert: dict[str, Any], observed_at: str) -> dict[str, Any]:
    alert_id = str(alert["alert_id"])
    material = f"{alert_id}:{observed_at}".encode("utf-8")
    return {
        "incident_id": f"inc-{hashlib.sha256(material).hexdigest()[:24]}",
        "alert_id": alert_id,
        "tier": str(alert.get("tier", "unknown")),
        "rule_id": str(alert.get("rule_id", "unknown")),
        "severity": str(alert.get("severity", "unknown")),
        "status": "OPEN",
        "first_seen_at": observed_at,
        "last_seen_at": observed_at,
        "resolved_at": None,
        "occurrence_count": 1,
        "latest_observation": {
            "observed": alert.get("observed"),
            "operator": alert.get("operator"),
            "threshold": alert.get("threshold"),
        },
    }


def reconcile_incidents(
    slo_report: dict[str, Any], previous_state: dict[str, Any] | None, observed_at: str
) -> dict[str, Any]:
    """Open, update, and resolve incidents from one complete SLO evaluation."""
    observed_at = _timestamp(observed_at)
    if slo_report.get("report_version") != "1.0":
        raise ValueError("unsupported SLO report version")
    if slo_report.get("status") not in {"PASS", "ALERT"}:
        raise ValueError("SLO report status must be PASS or ALERT")
    alerts = slo_report.get("alerts")
    if not isinstance(alerts, list):
        raise ValueError("SLO report alerts must be a list")
    state = previous_state or {"state_version": "1.0", "incidents": []}
    if state.get("state_version") != "1.0" or not isinstance(state.get("incidents"), list):
        raise ValueError("unsupported incident state")

    incidents = [dict(row) for row in state["incidents"]]
    current: dict[str, dict[str, Any]] = {}
    for alert in alerts:
        if not isinstance(alert, dict) or not str(alert.get("alert_id", "")):
            raise ValueError("every alert must contain a non-empty alert_id")
        alert_id = str(alert["alert_id"])
        if alert_id in current:
            raise ValueError(f"duplicate alert_id in SLO report: {alert_id}")
        current[alert_id] = alert

    open_by_alert: dict[str, dict[str, Any]] = {}
    for incident in incidents:
        if incident.get("status") != "OPEN":
            continue
        alert_id = str(incident.get("alert_id", ""))
        if not alert_id or alert_id in open_by_alert:
            raise ValueError("incident state contains invalid duplicate open alerts")
        open_by_alert[alert_id] = incident
    for alert_id, alert in sorted(current.items()):
        incident = open_by_alert.get(alert_id)
        if incident is None:
            incidents.append(_new_incident(alert, observed_at))
            continue
        if observed_at < str(incident["last_seen_at"]):
            raise ValueError("observed_at cannot move an open incident backwards")
        incident["last_seen_at"] = observed_at
        incident["occurrence_count"] = int(incident["occurrence_count"]) + 1
        incident["severity"] = str(alert.get("severity", incident["severity"]))
        incident["latest_observation"] = {
            "observed": alert.get("observed"),
            "operator": alert.get("operator"),
            "threshold": alert.get("threshold"),
        }

    for alert_id, incident in open_by_alert.items():
        if alert_id not in current:
            if observed_at < str(incident["last_seen_at"]):
                raise ValueError("observed_at cannot resolve an incident before last_seen_at")
            incident["status"] = "RESOLVED"
            incident["resolved_at"] = observed_at

    incidents.sort(key=lambda row: (str(row["first_seen_at"]), str(row["incident_id"])))
    return {
        "state_version": "1.0",
        "updated_at": observed_at,
        "source_policy_version": str(slo_report.get("policy_version", "unknown")),
        "active_incident_count": sum(row["status"] == "OPEN" for row in incidents),
        "resolved_incident_count": sum(row["status"] == "RESOLVED" for row in incidents),
        "incidents": incidents,
    }


def update_incident_state(slo_report_path: Path, state_path: Path, observed_at: str) -> dict[str, Any]:
    report = json.loads(slo_report_path.read_text(encoding="utf-8"))
    previous = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else None
    state = reconcile_incidents(report, previous, observed_at)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_name(f".{state_path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        temporary.replace(state_path)
    finally:
        temporary.unlink(missing_ok=True)
    return state
