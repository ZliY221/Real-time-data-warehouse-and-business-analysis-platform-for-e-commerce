from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .engine import QualityConfigurationError, evaluate_ndjson, load_quality_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate NDJSON data-quality rules")
    parser.add_argument("--input", type=Path, required=True, help="NDJSON input path")
    parser.add_argument("--config", type=Path, required=True, help="quality rule JSON path")
    parser.add_argument("--json-output", type=Path, help="write a machine-readable report")
    parser.add_argument("--markdown-output", type=Path, help="write a reviewer-friendly report")
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

    status = "PASS" if report.passed else "FAIL"
    failed_rules = sum(not rule.passed for rule in report.rules)
    print(
        f"data quality {status}: {report.total_records} records, "
        f"{failed_rules} failed rules"
    )
    raise SystemExit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
