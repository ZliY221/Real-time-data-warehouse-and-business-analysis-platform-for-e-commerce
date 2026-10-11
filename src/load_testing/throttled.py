"""Rate-limited NDJSON publishing primitives."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import time
from typing import Any, TextIO


def publish_lines(
    lines: Iterable[str],
    output: TextIO,
    *,
    target_rate: int,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Write non-empty NDJSON lines without exceeding the requested average schedule."""
    if not 1 <= target_rate <= 100_000:
        raise ValueError("target_rate must be between 1 and 100,000")

    started = clock()
    digest = hashlib.sha256()
    records = 0
    for line in lines:
        normalized = line.rstrip("\r\n")
        if not normalized:
            continue
        json.loads(normalized)
        deadline = started + (records + 1) / target_rate
        delay = deadline - clock()
        if delay > 0:
            sleeper(delay)
        serialized = normalized + "\n"
        output.write(serialized)
        output.flush()
        digest.update(serialized.encode("utf-8"))
        records += 1

    elapsed = max(0.0, clock() - started)
    return {
        "report_version": "1.0",
        "target_rate_per_second": target_rate,
        "records_published": records,
        "elapsed_seconds": round(elapsed, 6),
        "observed_output_rate_per_second": round(records / elapsed, 3) if elapsed else None,
        "input_sha256": digest.hexdigest(),
        "claims": {
            "measured_publisher_output_rate": True,
            "measured_kafka_ack_rate": False,
            "measured_pipeline_throughput": False,
        },
    }


def publish_file(
    input_path: Path,
    output: TextIO,
    report_path: Path,
    *,
    target_rate: int,
) -> dict[str, Any]:
    with input_path.open(encoding="utf-8") as stream:
        report = publish_lines(stream, output, target_rate=target_rate)
    report["completed_at"] = datetime.now(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    report["input_name"] = input_path.name
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report
