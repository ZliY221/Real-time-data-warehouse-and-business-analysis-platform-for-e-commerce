from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable

from event_generator.validation import validate_order_event

from .models import QualityReport, RuleResult


SUPPORTED_RULE_TYPES = {
    "contract",
    "completeness",
    "uniqueness",
    "range",
    "timeliness",
    "distribution",
}
MISSING = object()
MAX_SAMPLES = 5


class QualityConfigurationError(ValueError):
    """Raised when the rule configuration is unsafe or incomplete."""


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _require_rate(rule: dict[str, Any], name: str) -> float:
    value = rule.get(name)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1:
        raise QualityConfigurationError(f"{rule.get('id', '<unknown>')}.{name} must be 0..1")
    return float(value)


def _require_text(rule: dict[str, Any], name: str) -> str:
    value = rule.get(name)
    if not isinstance(value, str) or not value.strip():
        raise QualityConfigurationError(f"{rule.get('id', '<unknown>')}.{name} must be text")
    return value


def _validate_rule(rule: Any) -> dict[str, Any]:
    if not isinstance(rule, dict):
        raise QualityConfigurationError("each rule must be an object")
    rule_id = _require_text(rule, "id")
    rule_type = _require_text(rule, "type")
    if rule_type not in SUPPORTED_RULE_TYPES:
        raise QualityConfigurationError(f"{rule_id}.type is not supported: {rule_type}")

    threshold_fields = {
        "contract": ("max_invalid_rate",),
        "completeness": ("max_missing_rate",),
        "uniqueness": ("max_duplicate_rate",),
        "range": ("max_out_of_range_rate",),
        "timeliness": ("max_late_rate",),
        "distribution": ("max_absolute_deviation",),
    }
    for field in threshold_fields[rule_type]:
        _require_rate(rule, field)

    if rule_type == "completeness":
        fields = rule.get("fields")
        if not isinstance(fields, list) or not fields or any(
            not isinstance(field, str) or not field for field in fields
        ):
            raise QualityConfigurationError(f"{rule_id}.fields must be a non-empty text list")
    elif rule_type in {"uniqueness", "range", "distribution"}:
        _require_text(rule, "field")
    elif rule_type == "timeliness":
        _require_text(rule, "event_time_field")
        _require_text(rule, "observed_time_field")
        max_lag = rule.get("max_lag_seconds")
        if (
            not isinstance(max_lag, (int, float))
            or isinstance(max_lag, bool)
            or not math.isfinite(max_lag)
            or max_lag < 0
        ):
            raise QualityConfigurationError(f"{rule_id}.max_lag_seconds must be non-negative")

    if rule_type == "range":
        try:
            minimum = Decimal(str(rule["min"]))
            maximum = Decimal(str(rule["max"]))
        except (KeyError, InvalidOperation):
            raise QualityConfigurationError(f"{rule_id}.min and max must be numeric") from None
        if not minimum.is_finite() or not maximum.is_finite() or minimum > maximum:
            raise QualityConfigurationError(f"{rule_id}.min must not exceed max")

    if rule_type == "distribution":
        expected = rule.get("expected")
        if not isinstance(expected, dict) or not expected:
            raise QualityConfigurationError(f"{rule_id}.expected must be a non-empty object")
        if any(
            not isinstance(name, str)
            or not isinstance(share, (int, float))
            or isinstance(share, bool)
            or not math.isfinite(share)
            or share < 0
            for name, share in expected.items()
        ):
            raise QualityConfigurationError(f"{rule_id}.expected has invalid shares")
        if abs(sum(expected.values()) - 1.0) > 0.000001:
            raise QualityConfigurationError(f"{rule_id}.expected shares must sum to 1")
        minimum_records = rule.get("minimum_records", 1)
        if (
            not isinstance(minimum_records, int)
            or isinstance(minimum_records, bool)
            or minimum_records < 1
        ):
            raise QualityConfigurationError(f"{rule_id}.minimum_records must be positive")
    return rule


def load_quality_config(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise QualityConfigurationError(f"invalid JSON config: {error.msg}") from error
    if not isinstance(document, dict) or document.get("version") != 1:
        raise QualityConfigurationError("config version must be 1")
    rules = document.get("rules")
    if not isinstance(rules, list) or not rules:
        raise QualityConfigurationError("config rules must be a non-empty list")
    validated = [_validate_rule(rule) for rule in rules]
    rule_ids = [rule["id"] for rule in validated]
    if len(rule_ids) != len(set(rule_ids)):
        raise QualityConfigurationError("rule ids must be unique")
    return {"version": 1, "rules": validated}


def _value_at(event: dict[str, Any], path: str) -> Any:
    value: Any = event
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return MISSING
        value = value[part]
    return value


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _contract_rule(
    rule: dict[str, Any],
    records: list[tuple[int, dict[str, Any]]],
    invalid_json: list[str],
    total_records: int,
) -> RuleResult:
    invalid_contract = []
    for line_number, event in records:
        errors = validate_order_event(event)
        if errors:
            invalid_contract.append(f"line {line_number}: {'; '.join(errors[:3])}")
    violations = len(invalid_json) + len(invalid_contract)
    observed = _rate(violations, total_records)
    threshold = float(rule["max_invalid_rate"])
    return RuleResult(
        rule["id"],
        rule["type"],
        observed <= threshold,
        total_records,
        violations,
        "invalid_rate",
        observed,
        threshold,
        f"{violations} of {total_records} records failed JSON parsing or the v1 contract",
        tuple((invalid_json + invalid_contract)[:MAX_SAMPLES]),
        {
            "invalid_json_records": len(invalid_json),
            "invalid_contract_records": len(invalid_contract),
        },
    )


def _completeness_rule(
    rule: dict[str, Any], records: list[tuple[int, dict[str, Any]]]
) -> RuleResult:
    samples: list[str] = []
    missing_counts: Counter[str] = Counter()
    violations = 0
    for line_number, event in records:
        missing_fields = [
            field
            for field in rule["fields"]
            if _value_at(event, field) is MISSING or _value_at(event, field) in (None, "")
        ]
        if missing_fields:
            violations += 1
            missing_counts.update(missing_fields)
            samples.append(f"line {line_number}: missing {', '.join(missing_fields)}")
    observed = _rate(violations, len(records))
    threshold = float(rule["max_missing_rate"])
    return RuleResult(
        rule["id"], rule["type"], observed <= threshold, len(records), violations,
        "missing_rate", observed, threshold,
        f"{violations} records were missing one or more required fields",
        tuple(samples[:MAX_SAMPLES]), {"missing_by_field": dict(sorted(missing_counts.items()))},
    )


def _uniqueness_rule(
    rule: dict[str, Any], records: list[tuple[int, dict[str, Any]]]
) -> RuleResult:
    seen: dict[str, int] = {}
    samples: list[str] = []
    checked = 0
    violations = 0
    for line_number, event in records:
        raw_value = _value_at(event, rule["field"])
        if raw_value is MISSING or raw_value in (None, ""):
            continue
        checked += 1
        value = str(raw_value)
        if value in seen:
            violations += 1
            fingerprint = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
            samples.append(
                f"line {line_number}: duplicates line {seen[value]} "
                f"value_sha256={fingerprint}"
            )
        else:
            seen[value] = line_number
    observed = _rate(violations, checked)
    threshold = float(rule["max_duplicate_rate"])
    return RuleResult(
        rule["id"], rule["type"], observed <= threshold, checked, violations,
        "duplicate_rate", observed, threshold,
        f"{violations} duplicate occurrences found for {rule['field']}",
        tuple(samples[:MAX_SAMPLES]),
    )


def _range_rule(rule: dict[str, Any], records: list[tuple[int, dict[str, Any]]]) -> RuleResult:
    minimum = Decimal(str(rule["min"]))
    maximum = Decimal(str(rule["max"]))
    samples: list[str] = []
    violations = 0
    for line_number, event in records:
        raw_value = _value_at(event, rule["field"])
        try:
            value = Decimal(str(raw_value)) if raw_value is not MISSING else None
            in_range = value is not None and value.is_finite() and minimum <= value <= maximum
        except (InvalidOperation, TypeError):
            value = None
            in_range = False
        if not in_range:
            violations += 1
            samples.append(f"line {line_number}: {rule['field']}={raw_value!r}")
    observed = _rate(violations, len(records))
    threshold = float(rule["max_out_of_range_rate"])
    return RuleResult(
        rule["id"], rule["type"], observed <= threshold, len(records), violations,
        "out_of_range_rate", observed, threshold,
        f"{violations} values fell outside [{minimum}, {maximum}]",
        tuple(samples[:MAX_SAMPLES]),
    )


def _timeliness_rule(
    rule: dict[str, Any], records: list[tuple[int, dict[str, Any]]]
) -> RuleResult:
    samples: list[str] = []
    violations = 0
    max_lag = float(rule["max_lag_seconds"])
    observed_lags: list[float] = []
    for line_number, event in records:
        event_time = _parse_timestamp(_value_at(event, rule["event_time_field"]))
        observed_time = _parse_timestamp(_value_at(event, rule["observed_time_field"]))
        lag = (observed_time - event_time).total_seconds() if event_time and observed_time else None
        if lag is not None:
            observed_lags.append(lag)
        if lag is None or lag < 0 or lag > max_lag:
            violations += 1
            samples.append(f"line {line_number}: lag_seconds={lag!r}")
    observed = _rate(violations, len(records))
    threshold = float(rule["max_late_rate"])
    return RuleResult(
        rule["id"], rule["type"], observed <= threshold, len(records), violations,
        "late_rate", observed, threshold,
        f"{violations} records exceeded {max_lag:g} seconds or had invalid timestamps",
        tuple(samples[:MAX_SAMPLES]),
        {"maximum_observed_lag_seconds": max(observed_lags, default=None)},
    )


def _distribution_rule(
    rule: dict[str, Any], records: list[tuple[int, dict[str, Any]]]
) -> RuleResult:
    counts: Counter[str] = Counter()
    for _, event in records:
        value = _value_at(event, rule["field"])
        if value is not MISSING and value not in (None, ""):
            counts[str(value)] += 1
    checked = sum(counts.values())
    observed_shares = {name: count / checked for name, count in counts.items()} if checked else {}
    categories = set(rule["expected"]) | set(observed_shares)
    deviations = {
        name: abs(observed_shares.get(name, 0.0) - float(rule["expected"].get(name, 0.0)))
        for name in categories
    }
    observed = max(deviations.values(), default=1.0)
    threshold = float(rule["max_absolute_deviation"])
    minimum_records = int(rule.get("minimum_records", 1))
    passed = checked >= minimum_records and observed <= threshold
    deviating = sorted(name for name, value in deviations.items() if value > threshold)
    message = (
        f"maximum category-share deviation was {observed:.4f}"
        if checked >= minimum_records
        else f"only {checked} records were available; at least {minimum_records} are required"
    )
    samples = tuple(
        f"{name}: observed={observed_shares.get(name, 0.0):.4f}, "
        f"expected={float(rule['expected'].get(name, 0.0)):.4f}"
        for name in deviating[:MAX_SAMPLES]
    )
    return RuleResult(
        rule["id"], rule["type"], passed, checked, len(deviating),
        "max_absolute_deviation", observed, threshold, message, samples,
        {
            "observed_shares": dict(sorted(observed_shares.items())),
            "record_counts": dict(sorted(counts.items())),
        },
    )


RuleEvaluator = Callable[[dict[str, Any], list[tuple[int, dict[str, Any]]]], RuleResult]
RULE_EVALUATORS: dict[str, RuleEvaluator] = {
    "completeness": _completeness_rule,
    "uniqueness": _uniqueness_rule,
    "range": _range_rule,
    "timeliness": _timeliness_rule,
    "distribution": _distribution_rule,
}


def evaluate_ndjson(
    lines: Iterable[str],
    config: dict[str, Any],
    *,
    input_file: str,
    generated_at: datetime | None = None,
) -> QualityReport:
    records: list[tuple[int, dict[str, Any]]] = []
    invalid_json: list[str] = []
    total_records = 0
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        total_records += 1
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            invalid_json.append(f"line {line_number}: invalid JSON: {error.msg}")
            continue
        if not isinstance(event, dict):
            invalid_json.append(f"line {line_number}: JSON value must be an object")
            continue
        records.append((line_number, event))

    results: list[RuleResult] = []
    for rule in config["rules"]:
        if rule["type"] == "contract":
            results.append(_contract_rule(rule, records, invalid_json, total_records))
        else:
            results.append(RULE_EVALUATORS[rule["type"]](rule, records))

    contract_results = [result for result in results if result.rule_type == "contract"]
    invalid_contract_records = (
        int(contract_results[0].metrics["invalid_contract_records"]) if contract_results else 0
    )
    duplicate_records = sum(
        result.violations for result in results if result.rule_type == "uniqueness"
    )
    late_records = sum(result.violations for result in results if result.rule_type == "timeliness")
    timestamp = generated_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ValueError("generated_at must include timezone information")
    return QualityReport(
        timestamp,
        input_file,
        total_records,
        len(records),
        len(invalid_json),
        invalid_contract_records,
        duplicate_records,
        late_records,
        all(result.passed for result in results),
        tuple(results),
    )
