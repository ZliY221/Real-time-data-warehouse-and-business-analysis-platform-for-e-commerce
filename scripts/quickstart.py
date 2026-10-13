#!/usr/bin/env python3
"""Run the portable local ecommerce warehouse flow with one command."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.11.2"


def _output_path(value: Path) -> Path:
    return value.resolve() if value.is_absolute() else (ROOT / value).resolve()


def _run(label: str, *arguments: str) -> None:
    print(f"==> {label}", flush=True)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    completed = subprocess.run(
        [sys.executable, *arguments],
        cwd=ROOT,
        env=environment,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(f"{label} failed with exit code {completed.returncode}")


def _write_json_atomic(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a deterministic local ecommerce warehouse and report"
    )
    parser.add_argument("--output-dir", type=Path, default=Path("build/quickstart"))
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--seed", type=int, default=2027)
    args = parser.parse_args()
    if args.count <= 0:
        parser.error("--count must be greater than zero")

    output = _output_path(args.output_dir)
    events = output / "order_events.ndjson"
    database = output / f"ecommerce-{args.seed}-{args.count}.duckdb"
    doctor_json = output / "doctor.json"
    doctor_markdown = output / "doctor.md"
    report_json = output / "warehouse-report.json"
    report_markdown = output / "warehouse-report.md"

    _run(
        "Inspect environment",
        "scripts/project_doctor.py",
        "--profile",
        "warehouse",
        "--json-output",
        str(doctor_json),
        "--markdown-output",
        str(doctor_markdown),
    )
    _run(
        "Generate deterministic order events",
        "-m",
        "event_generator.cli",
        "--count",
        str(args.count),
        "--seed",
        str(args.seed),
        "--output",
        str(events),
    )
    _run(
        "Validate event contract",
        "-m",
        "event_generator.validate_cli",
        "--input",
        str(events),
        "--expected-count",
        str(args.count),
    )
    _run(
        "Build DuckDB warehouse",
        "-m",
        "offline_warehouse.cli",
        "--input",
        str(events),
        "--database",
        str(database),
    )
    _run(
        "Export aggregate warehouse report",
        "-m",
        "offline_warehouse.report",
        "--database",
        str(database),
        "--json-output",
        str(report_json),
        "--markdown-output",
        str(report_markdown),
    )

    report = json.loads(report_json.read_text(encoding="utf-8"))
    loaded_events = int(report["layer_counts"]["ods_order_events"])
    if loaded_events != args.count:
        raise SystemExit(
            f"warehouse verification failed: expected {args.count} events, found {loaded_events}"
        )
    summary = {
        "status": "COMPLETE",
        "project": "ecommerce-realtime-warehouse",
        "version": VERSION,
        "event_count": args.count,
        "seed": args.seed,
        "loaded_event_count": loaded_events,
        "outputs": {
            "doctor": str(doctor_json),
            "events": str(events),
            "database": str(database),
            "warehouse_report": str(report_json),
            "warehouse_report_markdown": str(report_markdown),
        },
    }
    summary_path = output / "summary.json"
    _write_json_atomic(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
