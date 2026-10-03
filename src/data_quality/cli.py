from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from .engine import QualityConfigurationError, evaluate_ndjson, load_quality_config
from .history import QualityHistoryStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate NDJSON data-quality rules")
    parser.add_argument("--input", type=Path, required=True, help="NDJSON input path")
    parser.add_argument("--config", type=Path, required=True, help="quality rule JSON path")
    parser.add_argument("--json-output", type=Path, help="write a machine-readable report")
    parser.add_argument("--markdown-output", type=Path, help="write a reviewer-friendly report")
    parser.add_argument("--history-db", type=Path, help="persist run and rule summaries in SQLite")
    return parser


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    args = build_parser().parse_args()
    try:
        config = load_quality_config(args.config)
        with args.input.open("r", encoding="utf-8-sig") as stream:
            report = evaluate_ndjson(stream, config, input_file=str(args.input))
    except (FileNotFoundError, OSError, QualityConfigurationError) as error:
        print(f"data-quality configuration or input error: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    if args.json_output:
        _write(
            args.json_output,
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        )
    if args.markdown_output:
        _write(args.markdown_output, report.to_markdown())

    history_message = ""
    if args.history_db:
        try:
            run_id, inserted = QualityHistoryStore(args.history_db).save(report)
        except (OSError, sqlite3.Error, ValueError) as error:
            print(f"data-quality history error: {error}", file=sys.stderr)
            raise SystemExit(2) from error
        history_message = f", history run {run_id} ({'stored' if inserted else 'already present'})"

    status = "PASS" if report.passed else "FAIL"
    failed_rules = sum(not rule.passed for rule in report.rules)
    print(
        f"data quality {status}: {report.total_records} records, "
        f"{failed_rules} failed rules{history_message}"
    )
    raise SystemExit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
