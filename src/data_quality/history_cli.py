from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
import sys

from .history import QualityHistoryStore, StoredRuleResult, StoredRun


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export stored data-quality history")
    parser.add_argument("--database", type=Path, required=True, help="SQLite history path")
    parser.add_argument("--limit", type=int, default=50, help="maximum runs or points")
    parser.add_argument("--rule-id", help="include the chronological trend for this rule")
    parser.add_argument("--json-output", type=Path, help="write machine-readable history")
    parser.add_argument("--markdown-output", type=Path, help="write reviewer-friendly history")
    return parser


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _document(runs: list[StoredRun], trend: list[StoredRuleResult]) -> dict[str, object]:
    return {
        "history_version": "1.0",
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "run_count": len(runs),
        "runs": [run.to_dict() for run in runs],
        "trend": [point.to_dict() for point in trend],
    }


def _markdown(runs: list[StoredRun], trend: list[StoredRuleResult]) -> str:
    lines = [
        "# Data quality history",
        "",
        f"Stored runs shown: {len(runs)}",
        "",
        "| Generated at | Status | Records | Failed rules | Invalid | Duplicates | Late |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for run in runs:
        invalid = run.invalid_json_records + run.invalid_contract_records
        lines.append(
            f"| {run.generated_at} | {'PASS' if run.passed else 'FAIL'} | "
            f"{run.total_records} | {run.failed_rules} | {invalid} | "
            f"{run.duplicate_records} | {run.late_records} |"
        )
    if trend:
        lines.extend(
            [
                "",
                f"## Rule trend: {trend[0].rule_id}",
                "",
                "| Generated at | Status | Observed | Limit | Violations |",
                "| --- | --- | ---: | ---: | ---: |",
            ]
        )
        for point in trend:
            lines.append(
                f"| {point.generated_at} | {'PASS' if point.passed else 'FAIL'} | "
                f"{point.observed_value:.4f} | {point.threshold:.4f} | "
                f"{point.violations} |"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = build_parser().parse_args()
    try:
        if not args.database.is_file():
            raise FileNotFoundError(f"history database not found: {args.database}")
        store = QualityHistoryStore(args.database)
        runs = store.list_runs(limit=args.limit)
        trend = store.rule_trend(args.rule_id, limit=args.limit) if args.rule_id else []
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"data-quality history error: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    document = _document(runs, trend)
    if args.json_output:
        _write(args.json_output, json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    if args.markdown_output:
        _write(args.markdown_output, _markdown(runs, trend))
    print(f"exported {len(runs)} quality runs and {len(trend)} trend points")


if __name__ == "__main__":
    main()
