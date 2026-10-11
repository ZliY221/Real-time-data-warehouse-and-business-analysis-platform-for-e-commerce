"""Tiered load-test plans with explicit measurement boundaries."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any


LOAD_TIERS = (
    {"name": "low", "event_count": 10_000, "target_publish_rate_per_second": 100},
    {"name": "medium", "event_count": 50_000, "target_publish_rate_per_second": 1_000},
    {"name": "high", "event_count": 100_000, "target_publish_rate_per_second": 5_000},
)


def build_load_plan(*, generated_at: datetime | None = None) -> dict[str, Any]:
    """Return the canonical, machine-readable three-tier experiment plan."""
    timestamp = (generated_at or datetime.now(UTC)).astimezone(UTC)
    tiers = [
        {
            **tier,
            "minimum_publish_duration_seconds": round(
                tier["event_count"] / tier["target_publish_rate_per_second"], 3
            ),
            "required_evidence": [
                "publisher-report.json",
                "flink-runtime.json",
                "clickhouse-final-count.json",
            ],
        }
        for tier in LOAD_TIERS
    ]
    return {
        "plan_version": "1.0",
        "generated_at": timestamp.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "tiers": tiers,
        "measurement_policy": {
            "event_time_rate_is_throughput": False,
            "publisher_output_rate_is_pipeline_throughput": False,
            "pipeline_throughput_requires_sink_completion": True,
        },
    }


def write_load_plan(path: Path, *, generated_at: datetime | None = None) -> dict[str, Any]:
    plan = build_load_plan(generated_at=generated_at)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return plan
