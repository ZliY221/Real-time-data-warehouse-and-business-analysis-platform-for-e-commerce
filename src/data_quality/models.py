from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    rule_type: str
    passed: bool
    checked_records: int
    violations: int
    metric_name: str
    observed_value: float
    threshold: float
    message: str
    samples: tuple[str, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["observed_value"] = round(self.observed_value, 6)
        result["threshold"] = round(self.threshold, 6)
        result["samples"] = list(self.samples)
        return result


@dataclass(frozen=True)
class QualityReport:
    generated_at: datetime
    input_file: str
    total_records: int
    parsed_records: int
    invalid_json_records: int
    invalid_contract_records: int
    duplicate_records: int
    late_records: int
    passed: bool
    rules: tuple[RuleResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_version": "1.0",
            "generated_at": _utc_text(self.generated_at),
            "input_file": self.input_file,
            "summary": {
                "passed": self.passed,
                "total_records": self.total_records,
                "parsed_records": self.parsed_records,
                "invalid_json_records": self.invalid_json_records,
                "invalid_contract_records": self.invalid_contract_records,
                "duplicate_records": self.duplicate_records,
                "late_records": self.late_records,
                "passed_rules": sum(rule.passed for rule in self.rules),
                "failed_rules": sum(not rule.passed for rule in self.rules),
            },
            "rules": [rule.to_dict() for rule in self.rules],
        }

    def to_markdown(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [
            "# Data quality report",
            "",
            f"- Status: **{status}**",
            f"- Input: `{Path(self.input_file).as_posix()}`",
            f"- Generated at: `{_utc_text(self.generated_at)}`",
            f"- Records: {self.total_records} total, {self.parsed_records} parsed",
            "",
            "| Rule | Type | Status | Observed | Limit | Violations |",
            "| --- | --- | --- | ---: | ---: | ---: |",
        ]
        for rule in self.rules:
            rule_status = "PASS" if rule.passed else "FAIL"
            lines.append(
                f"| {rule.rule_id} | {rule.rule_type} | {rule_status} | "
                f"{rule.observed_value:.4f} | {rule.threshold:.4f} | {rule.violations} |"
            )

        failed_rules = [rule for rule in self.rules if not rule.passed]
        if failed_rules:
            lines.extend(["", "## Failed rules", ""])
            for rule in failed_rules:
                lines.append(f"### {rule.rule_id}")
                lines.extend(["", rule.message])
                if rule.samples:
                    lines.extend(["", "Samples:"])
                    lines.extend(f"- {sample}" for sample in rule.samples)
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"
