"""Continuous Flink runtime sampling for bounded load experiments."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import json
from pathlib import Path
import time
from typing import Any

from .flink_runtime import FlinkRestClient, collect_runtime_snapshot


def collect_runtime_series(
    client: FlinkRestClient,
    job_id: str,
    *,
    sample_count: int,
    interval_seconds: float,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleeper: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    if not 1 <= sample_count <= 1_000:
        raise ValueError("sample_count must be between 1 and 1,000")
    if not 0 <= interval_seconds <= 3_600:
        raise ValueError("interval_seconds must be between 0 and 3,600")
    snapshots: list[dict[str, Any]] = []
    for index in range(sample_count):
        snapshots.append(collect_runtime_snapshot(client, job_id, collected_at=clock()))
        if index + 1 < sample_count:
            sleeper(interval_seconds)
    return snapshots


def write_runtime_series(path: Path, snapshots: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for snapshot in snapshots:
            handle.write(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
