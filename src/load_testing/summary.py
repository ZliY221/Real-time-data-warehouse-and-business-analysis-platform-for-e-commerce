"""Validated summaries for three-tier end-to-end load evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"evidence must be a JSON object: {path}")
    return document


def _read_ndjson(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"runtime series must contain JSON objects: {path}")
    return rows


def _runtime_summary(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    peak_input = 0.0
    peak_output = 0.0
    max_backpressure = 0.0
    failed_checkpoints = 0
    states: set[str] = set()
    for snapshot in snapshots:
        job = snapshot.get("job", {})
        states.add(str(job.get("state", "UNKNOWN")))
        checkpoints = snapshot.get("checkpoints", {}).get("counts", {})
        failed_checkpoints = max(failed_checkpoints, int(checkpoints.get("failed", 0)))
        for vertex in snapshot.get("vertices", []):
            metrics = vertex.get("metrics", {})
            peak_input = max(peak_input, float(metrics.get("numRecordsInPerSecond") or 0))
            peak_output = max(peak_output, float(metrics.get("numRecordsOutPerSecond") or 0))
            backpressure = vertex.get("backpressure", {})
            max_backpressure = max(
                max_backpressure, float(backpressure.get("max_backpressure_ratio") or 0)
            )
    return {
        "sample_count": len(snapshots),
        "job_states": sorted(states),
        "peak_vertex_input_per_second": round(peak_input, 3),
        "peak_vertex_output_per_second": round(peak_output, 3),
        "max_backpressure_ratio": round(max_backpressure, 6),
        "max_failed_checkpoint_count": failed_checkpoints,
    }


def summarize_load_experiment(plan: dict[str, Any], evidence_root: Path) -> dict[str, Any]:
    tiers = plan.get("tiers")
    if not isinstance(tiers, list) or [tier.get("name") for tier in tiers] != [
        "low",
        "medium",
        "high",
    ]:
        raise ValueError("load plan must contain low, medium, and high tiers in order")
    summaries: list[dict[str, Any]] = []
    for tier in tiers:
        name = str(tier["name"])
        tier_root = evidence_root / name
        publisher = _read_json(tier_root / "publisher-report.json")
        sink = _read_json(tier_root / "sink-completion.json")
        snapshots = _read_ndjson(tier_root / "flink-series.ndjson")
        expected = int(tier["event_count"])
        target_rate = int(tier["target_publish_rate_per_second"])
        errors: list[str] = []
        if int(publisher.get("records_published", -1)) != expected:
            errors.append("publisher record count does not match the plan")
        if int(publisher.get("target_rate_per_second", -1)) != target_rate:
            errors.append("publisher target rate does not match the plan")
        if sink.get("status") != "COMPLETE" or not sink.get("claims", {}).get(
            "sink_completion_verified"
        ):
            errors.append("ClickHouse sink completion is not verified")
        if int(sink.get("expected_records", -1)) != expected:
            errors.append("sink expected record count does not match the plan")
        if int(sink.get("observed_records", -1)) < expected:
            errors.append("sink observed fewer records than required")
        if errors:
            raise ValueError(f"{name} evidence is inconsistent: {'; '.join(errors)}")
        summaries.append(
            {
                "name": name,
                "status": "COMPLETE",
                "event_count": expected,
                "target_publish_rate_per_second": target_rate,
                "observed_publisher_output_rate_per_second": publisher.get(
                    "observed_output_rate_per_second"
                ),
                "end_to_end_elapsed_seconds": sink.get("elapsed_seconds"),
                "end_to_end_throughput_per_second": sink.get(
                    "end_to_end_throughput_per_second"
                ),
                "runtime": _runtime_summary(snapshots),
            }
        )
    return {
        "summary_version": "1.0",
        "status": "COMPLETE",
        "plan_version": plan.get("plan_version"),
        "tiers": summaries,
        "claims": {
            "all_sink_completions_verified": True,
            "results_are_production_capacity": False,
        },
    }


def write_experiment_summary(plan_path: Path, evidence_root: Path, output: Path) -> dict[str, Any]:
    summary = summarize_load_experiment(_read_json(plan_path), evidence_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary
