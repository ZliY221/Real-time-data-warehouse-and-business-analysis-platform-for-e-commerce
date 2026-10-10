"""Create deterministic load-test inputs with a machine-readable manifest."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from event_generator.generator import generate_order_events
from event_generator.validation import validate_order_event


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must include timezone information")
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def generate_load_dataset(
    output: Path,
    manifest_output: Path,
    *,
    count: int,
    seed: int,
    start_time: datetime,
    event_time_rate: int,
    profile: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if not 1 <= count <= 1_000_000:
        raise ValueError("count must be between 1 and 1,000,000")
    if not 1 <= event_time_rate <= 100_000:
        raise ValueError("event_time_rate must be between 1 and 100,000")
    if not profile or len(profile) > 50 or not profile.replace("-", "").isalnum():
        raise ValueError("profile must be 1-50 letters, digits, or hyphens")

    events = generate_order_events(
        count,
        seed=seed,
        start_time=start_time,
        events_per_second=event_time_rate,
    )
    for index, event in enumerate(events):
        errors = validate_order_event(event)
        if errors:
            raise ValueError(f"generated event {index} violates the contract: {errors}")

    output.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size_bytes = 0
    with output.open("wb") as stream:
        for event in events:
            line = (json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
            stream.write(line)
            digest.update(line)
            size_bytes += len(line)

    timestamp = generated_at or datetime.now(UTC)
    manifest: dict[str, Any] = {
        "manifest_version": "1.0",
        "profile": profile,
        "generated_at": _utc_text(timestamp),
        "generator": {
            "count": count,
            "seed": seed,
            "start_time": _utc_text(start_time),
            "event_time_rate_per_second": event_time_rate,
            "event_time_span_ms": ((count - 1) * 1_000_000 // event_time_rate) // 1_000,
        },
        "dataset": {
            "path": output.name,
            "format": "ndjson",
            "size_bytes": size_bytes,
            "sha256": digest.hexdigest(),
        },
        "claims": {
            "measured_publish_rate": False,
            "measured_pipeline_throughput": False,
        },
    }
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest
