"""Evaluate operational SLOs against validated load-experiment summaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    return float(value)


def evaluate_slos(summary: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic pass/fail decisions without claiming production capacity."""
    if summary.get("status") != "COMPLETE":
        raise ValueError("load summary must be COMPLETE")
    tiers = summary.get("tiers")
    if not isinstance(tiers, list) or not tiers:
        raise ValueError("load summary must contain tiers")
    defaults = policy.get("defaults")
    overrides = policy.get("tier_overrides", {})
    if not isinstance(defaults, dict) or not isinstance(overrides, dict):
        raise ValueError("SLO policy must contain defaults and optional tier_overrides")

    evaluations: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for tier in tiers:
        name = str(tier.get("name", ""))
        if not name or name in seen_names:
            raise ValueError("load summary tier names must be non-empty and unique")
        seen_names.add(name)
        runtime = tier.get("runtime")
        if not isinstance(runtime, dict):
            raise ValueError(f"{name} runtime summary is missing")
        thresholds = {**defaults, **overrides.get(name, {})}
        required = {
            "min_throughput_ratio",
            "max_backpressure_ratio",
            "max_failed_checkpoints",
            "allowed_job_states",
        }
        if missing := required - thresholds.keys():
            raise ValueError(f"{name} SLO thresholds are missing {sorted(missing)}")
        target = _number(tier.get("target_publish_rate_per_second"), f"{name} target rate")
        throughput = _number(tier.get("end_to_end_throughput_per_second"), f"{name} throughput")
        if target <= 0 or throughput < 0:
            raise ValueError(f"{name} rates must be non-negative and target must be positive")
        throughput_ratio = throughput / target
        backpressure = _number(runtime.get("max_backpressure_ratio"), f"{name} backpressure")
        failed_checkpoints = int(
            _number(runtime.get("max_failed_checkpoint_count"), f"{name} failed checkpoints")
        )
        job_states = runtime.get("job_states")
        allowed_states = thresholds["allowed_job_states"]
        if not isinstance(job_states, list) or not isinstance(allowed_states, list):
            raise ValueError(f"{name} job states must be lists")

        checks = [
            {
                "rule_id": "SLO-THROUGHPUT-RATIO",
                "severity": "critical",
                "observed": round(throughput_ratio, 6),
                "operator": ">=",
                "threshold": _number(thresholds["min_throughput_ratio"], "minimum throughput ratio"),
                "passed": throughput_ratio
                >= _number(thresholds["min_throughput_ratio"], "minimum throughput ratio"),
            },
            {
                "rule_id": "SLO-BACKPRESSURE-RATIO",
                "severity": "warning",
                "observed": round(backpressure, 6),
                "operator": "<=",
                "threshold": _number(thresholds["max_backpressure_ratio"], "maximum backpressure ratio"),
                "passed": backpressure
                <= _number(thresholds["max_backpressure_ratio"], "maximum backpressure ratio"),
            },
            {
                "rule_id": "SLO-FAILED-CHECKPOINTS",
                "severity": "critical",
                "observed": failed_checkpoints,
                "operator": "<=",
                "threshold": int(
                    _number(thresholds["max_failed_checkpoints"], "maximum failed checkpoints")
                ),
                "passed": failed_checkpoints
                <= int(_number(thresholds["max_failed_checkpoints"], "maximum failed checkpoints")),
            },
            {
                "rule_id": "SLO-JOB-STATE",
                "severity": "critical",
                "observed": sorted(str(state) for state in job_states),
                "operator": "subset_of",
                "threshold": sorted(str(state) for state in allowed_states),
                "passed": bool(job_states) and set(job_states).issubset(set(allowed_states)),
            },
        ]
        for check in checks:
            if not check["passed"]:
                alerts.append(
                    {
                        "alert_id": f"{name}:{check['rule_id']}",
                        "tier": name,
                        **check,
                    }
                )
        evaluations.append(
            {
                "tier": name,
                "status": "PASS" if all(check["passed"] for check in checks) else "ALERT",
                "checks": checks,
            }
        )
    return {
        "report_version": "1.0",
        "status": "PASS" if not alerts else "ALERT",
        "policy_version": str(policy.get("policy_version", "unknown")),
        "summary_plan_version": summary.get("plan_version"),
        "evaluations": evaluations,
        "alerts": alerts,
        "claims": {"production_slo_certified": False},
    }


def write_slo_report(summary_path: Path, policy_path: Path, output_path: Path) -> dict[str, Any]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    report = evaluate_slos(summary, policy)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report
