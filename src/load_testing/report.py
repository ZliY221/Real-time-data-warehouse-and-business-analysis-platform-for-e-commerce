"""Render a compact human-readable Flink runtime snapshot."""

from __future__ import annotations

from typing import Any


def runtime_snapshot_markdown(snapshot: dict[str, Any]) -> str:
    job = snapshot["job"]
    checkpoints = snapshot["checkpoints"]
    counts = checkpoints["counts"]
    lines = [
        "# Flink runtime snapshot",
        "",
        f"- Collected at: `{snapshot['collected_at']}`",
        f"- Job: `{job['name']}` (`{job['id']}`)",
        f"- State: **{job['state']}**",
        f"- Restarts: {job['metrics'].get('numRestarts')}",
        f"- Checkpoints: {counts['completed']} completed, {counts['failed']} failed, "
        f"{counts['in_progress']} in progress",
        "- Privacy: no event payloads or exception messages are included",
        "",
        "## Vertices",
        "",
        "| Vertex | Status | Parallelism | Records in | Records out | In/s | Out/s | "
        "Busy ms/s | Backpressured ms/s | Backpressure |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for vertex in snapshot["vertices"]:
        metrics = vertex["metrics"]
        lines.append(
            f"| {vertex['name']} | {vertex['status']} | {vertex['parallelism']} | "
            f"{metrics.get('numRecordsIn')} | {metrics.get('numRecordsOut')} | "
            f"{metrics.get('numRecordsInPerSecond')} | "
            f"{metrics.get('numRecordsOutPerSecond')} | "
            f"{metrics.get('busyTimeMsPerSecond')} | "
            f"{metrics.get('backPressuredTimeMsPerSecond')} | "
            f"{vertex['backpressure'].get('level')} |"
        )
    latest = checkpoints.get("latest_completed")
    if latest:
        lines.extend(
            [
                "",
                "## Latest completed checkpoint",
                "",
                f"- ID: {latest['id']}",
                f"- Duration: {latest['duration_ms']} ms",
                f"- Checkpointed size: {latest['checkpointed_size_bytes']} bytes",
                f"- Acknowledged subtasks: {latest['acknowledged_subtasks']}/{latest['subtasks']}",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
