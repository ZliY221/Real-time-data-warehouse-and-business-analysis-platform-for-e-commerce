from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from .models import QualityReport


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class StoredRun:
    run_id: str
    generated_at: str
    input_file: str
    passed: bool
    total_records: int
    parsed_records: int
    invalid_json_records: int
    invalid_contract_records: int
    duplicate_records: int
    late_records: int
    passed_rules: int
    failed_rules: int

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.__dict__,
            "passed": self.passed,
        }


@dataclass(frozen=True)
class StoredRuleResult:
    run_id: str
    generated_at: str
    rule_id: str
    rule_type: str
    passed: bool
    checked_records: int
    violations: int
    metric_name: str
    observed_value: float
    threshold: float
    message: str
    samples: tuple[str, ...]
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.__dict__,
            "passed": self.passed,
            "samples": list(self.samples),
        }


class QualityHistoryStore:
    """SQLite-backed history containing summaries, never complete event payloads."""

    def __init__(self, database: Path) -> None:
        self.database = database
        database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version not in (0, SCHEMA_VERSION):
                raise ValueError(
                    f"unsupported quality history schema version {version}; "
                    f"expected {SCHEMA_VERSION}"
                )
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS quality_runs (
                    run_id TEXT PRIMARY KEY,
                    generated_at TEXT NOT NULL,
                    input_file TEXT NOT NULL,
                    passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
                    total_records INTEGER NOT NULL CHECK (total_records >= 0),
                    parsed_records INTEGER NOT NULL CHECK (parsed_records >= 0),
                    invalid_json_records INTEGER NOT NULL CHECK (invalid_json_records >= 0),
                    invalid_contract_records INTEGER NOT NULL
                        CHECK (invalid_contract_records >= 0),
                    duplicate_records INTEGER NOT NULL CHECK (duplicate_records >= 0),
                    late_records INTEGER NOT NULL CHECK (late_records >= 0),
                    passed_rules INTEGER NOT NULL CHECK (passed_rules >= 0),
                    failed_rules INTEGER NOT NULL CHECK (failed_rules >= 0),
                    stored_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS quality_rule_results (
                    run_id TEXT NOT NULL,
                    rule_id TEXT NOT NULL,
                    rule_type TEXT NOT NULL,
                    passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
                    checked_records INTEGER NOT NULL CHECK (checked_records >= 0),
                    violations INTEGER NOT NULL CHECK (violations >= 0),
                    metric_name TEXT NOT NULL,
                    observed_value REAL NOT NULL,
                    threshold REAL NOT NULL,
                    message TEXT NOT NULL,
                    samples_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, rule_id),
                    FOREIGN KEY (run_id) REFERENCES quality_runs(run_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS quality_runs_generated_at_idx
                    ON quality_runs(generated_at DESC, run_id DESC);
                CREATE INDEX IF NOT EXISTS quality_rule_results_rule_idx
                    ON quality_rule_results(rule_id, run_id);
                """
            )
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @staticmethod
    def _run_id(report: QualityReport) -> str:
        canonical = json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()[:24]

    def save(self, report: QualityReport) -> tuple[str, bool]:
        run_id = self._run_id(report)
        document = report.to_dict()
        summary = document["summary"]
        stored_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO quality_runs (
                    run_id, generated_at, input_file, passed, total_records,
                    parsed_records, invalid_json_records, invalid_contract_records,
                    duplicate_records, late_records, passed_rules, failed_rules, stored_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    document["generated_at"],
                    report.input_file,
                    int(report.passed),
                    report.total_records,
                    report.parsed_records,
                    report.invalid_json_records,
                    report.invalid_contract_records,
                    report.duplicate_records,
                    report.late_records,
                    summary["passed_rules"],
                    summary["failed_rules"],
                    stored_at,
                ),
            )
            inserted = cursor.rowcount == 1
            for rule in report.rules:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO quality_rule_results (
                        run_id, rule_id, rule_type, passed, checked_records,
                        violations, metric_name, observed_value, threshold,
                        message, samples_json, metrics_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        rule.rule_id,
                        rule.rule_type,
                        int(rule.passed),
                        rule.checked_records,
                        rule.violations,
                        rule.metric_name,
                        rule.observed_value,
                        rule.threshold,
                        rule.message,
                        json.dumps(rule.samples, ensure_ascii=False),
                        json.dumps(rule.metrics, ensure_ascii=False, sort_keys=True),
                    ),
                )
        return run_id, inserted

    @staticmethod
    def _validate_limit(limit: int) -> None:
        if isinstance(limit, bool) or not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")

    def list_runs(self, *, limit: int = 50, passed: bool | None = None) -> list[StoredRun]:
        self._validate_limit(limit)
        where = "" if passed is None else "WHERE passed = ?"
        parameters: tuple[Any, ...] = (limit,) if passed is None else (int(passed), limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT run_id, generated_at, input_file, passed, total_records,
                       parsed_records, invalid_json_records, invalid_contract_records,
                       duplicate_records, late_records, passed_rules, failed_rules
                FROM quality_runs
                {where}
                ORDER BY generated_at DESC, run_id DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [self._stored_run(row) for row in rows]

    def list_rule_results(self, run_id: str) -> list[StoredRuleResult]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT r.run_id, q.generated_at, r.rule_id, r.rule_type, r.passed,
                       r.checked_records, r.violations, r.metric_name,
                       r.observed_value, r.threshold, r.message,
                       r.samples_json, r.metrics_json
                FROM quality_rule_results r
                JOIN quality_runs q ON q.run_id = r.run_id
                WHERE r.run_id = ?
                ORDER BY r.rule_id ASC
                """,
                (run_id,),
            ).fetchall()
        return [self._stored_rule(row) for row in rows]

    def rule_trend(self, rule_id: str, *, limit: int = 50) -> list[StoredRuleResult]:
        if not rule_id.strip():
            raise ValueError("rule_id must not be blank")
        self._validate_limit(limit)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM (
                    SELECT r.run_id, q.generated_at, r.rule_id, r.rule_type, r.passed,
                           r.checked_records, r.violations, r.metric_name,
                           r.observed_value, r.threshold, r.message,
                           r.samples_json, r.metrics_json
                    FROM quality_rule_results r
                    JOIN quality_runs q ON q.run_id = r.run_id
                    WHERE r.rule_id = ?
                    ORDER BY q.generated_at DESC, r.run_id DESC
                    LIMIT ?
                )
                ORDER BY generated_at ASC, run_id ASC
                """,
                (rule_id, limit),
            ).fetchall()
        return [self._stored_rule(row) for row in rows]

    @staticmethod
    def _stored_run(row: sqlite3.Row) -> StoredRun:
        return StoredRun(
            row["run_id"],
            row["generated_at"],
            row["input_file"],
            bool(row["passed"]),
            row["total_records"],
            row["parsed_records"],
            row["invalid_json_records"],
            row["invalid_contract_records"],
            row["duplicate_records"],
            row["late_records"],
            row["passed_rules"],
            row["failed_rules"],
        )

    @staticmethod
    def _stored_rule(row: sqlite3.Row) -> StoredRuleResult:
        return StoredRuleResult(
            row["run_id"],
            row["generated_at"],
            row["rule_id"],
            row["rule_type"],
            bool(row["passed"]),
            row["checked_records"],
            row["violations"],
            row["metric_name"],
            row["observed_value"],
            row["threshold"],
            row["message"],
            tuple(json.loads(row["samples_json"])),
            json.loads(row["metrics_json"]),
        )
