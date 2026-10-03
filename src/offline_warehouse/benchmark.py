"""Reproducible local benchmark for the transactional offline warehouse loader."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
from tempfile import TemporaryDirectory
import time

from event_generator.generator import generate_order_events

from .loader import load_order_events


@dataclass(frozen=True)
class TrialResult:
    trial: int
    load_seconds: float
    events_per_second: float
    loaded_events: int
    loaded_items: int
    database_bytes: int


@dataclass(frozen=True)
class BenchmarkReport:
    generated_at: str
    benchmark_scope: str
    event_count: int
    trial_count: int
    seed: int
    input_bytes: int
    input_sha256: str
    generation_seconds: float
    expected_gmv: str
    median_load_seconds: float
    min_load_seconds: float
    max_load_seconds: float
    median_events_per_second: float
    python_version: str
    duckdb_version: str
    operating_system: str
    machine_architecture: str
    logical_cpu_count: int | None
    trials: tuple[TrialResult, ...]

    def to_dict(self) -> dict[str, object]:
        document = asdict(self)
        document["trials"] = [asdict(trial) for trial in self.trials]
        return document


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_events(path: Path, events: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for event in events:
            stream.write(
                json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            )
            stream.write("\n")


def run_benchmark(
    *,
    event_count: int,
    trial_count: int,
    seed: int = 2027,
) -> BenchmarkReport:
    """Run isolated cold-database trials and verify every loaded result."""

    if not 1 <= event_count <= 1_000_000:
        raise ValueError("event_count must be from 1 to 1000000")
    if not 1 <= trial_count <= 20:
        raise ValueError("trial_count must be from 1 to 20")

    import duckdb

    generation_started = time.perf_counter()
    events = generate_order_events(
        event_count,
        seed=seed,
        start_time=datetime(2026, 10, 1, tzinfo=UTC),
    )
    generation_seconds = time.perf_counter() - generation_started
    expected_gmv = sum(
        (Decimal(str(event["payload"]["total_amount"])) for event in events),
        Decimal("0.00"),
    )

    trial_results: list[TrialResult] = []
    with TemporaryDirectory(prefix="offline-warehouse-benchmark-") as directory:
        root = Path(directory)
        source = root / "events.ndjson"
        _write_events(source, events)
        input_bytes = source.stat().st_size
        input_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()

        for trial in range(1, trial_count + 1):
            database = root / f"trial-{trial}.duckdb"
            started = time.perf_counter()
            result = load_order_events(source, database)
            load_seconds = time.perf_counter() - started

            connection = duckdb.connect(str(database), read_only=True)
            try:
                stored_events, stored_items, stored_gmv = connection.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM ods.order_events),
                        (SELECT COUNT(*) FROM dwd.fact_order_items),
                        (SELECT SUM(total_amount) FROM ods.order_events)
                    """
                ).fetchone()
            finally:
                connection.close()
            if int(stored_events) != event_count or int(stored_items) != result.loaded_items:
                raise RuntimeError("benchmark row-count verification failed")
            if Decimal(stored_gmv) != expected_gmv:
                raise RuntimeError("benchmark GMV verification failed")
            trial_results.append(
                TrialResult(
                    trial=trial,
                    load_seconds=round(load_seconds, 6),
                    events_per_second=round(event_count / load_seconds, 2),
                    loaded_events=result.loaded_events,
                    loaded_items=result.loaded_items,
                    database_bytes=database.stat().st_size,
                )
            )

    load_times = [trial.load_seconds for trial in trial_results]
    median_load = statistics.median(load_times)
    return BenchmarkReport(
        generated_at=_utc_text(datetime.now(UTC)),
        benchmark_scope=(
            "cold DuckDB database creation, validated NDJSON staging, dimensional load, "
            "commit, close, and post-load row/GMV verification"
        ),
        event_count=event_count,
        trial_count=trial_count,
        seed=seed,
        input_bytes=input_bytes,
        input_sha256=input_sha256,
        generation_seconds=round(generation_seconds, 6),
        expected_gmv=f"{expected_gmv:.2f}",
        median_load_seconds=round(median_load, 6),
        min_load_seconds=round(min(load_times), 6),
        max_load_seconds=round(max(load_times), 6),
        median_events_per_second=round(event_count / median_load, 2),
        python_version=platform.python_version(),
        duckdb_version=duckdb.__version__,
        operating_system=f"{platform.system()} {platform.release()}",
        machine_architecture=platform.machine(),
        logical_cpu_count=os.cpu_count(),
        trials=tuple(trial_results),
    )


def to_markdown(report: BenchmarkReport) -> str:
    lines = [
        "# Offline Warehouse Benchmark",
        "",
        f"Generated at: `{report.generated_at}`",
        "",
        "## Scope",
        "",
        report.benchmark_scope,
        "",
        "## Environment and input",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Events | {report.event_count} |",
        f"| Trials | {report.trial_count} |",
        f"| Seed | {report.seed} |",
        f"| Input bytes | {report.input_bytes} |",
        f"| Input SHA-256 | `{report.input_sha256}` |",
        f"| Expected GMV | {report.expected_gmv} CNY |",
        f"| Event generation | {report.generation_seconds:.6f} s |",
        f"| Python | {report.python_version} |",
        f"| DuckDB | {report.duckdb_version} |",
        f"| OS | {report.operating_system} |",
        f"| Architecture | {report.machine_architecture} |",
        f"| Logical CPUs | {report.logical_cpu_count} |",
        "",
        "## Result",
        "",
        f"- Median load time: **{report.median_load_seconds:.6f} s**",
        f"- Median throughput: **{report.median_events_per_second:.2f} events/s**",
        f"- Range: {report.min_load_seconds:.6f}—{report.max_load_seconds:.6f} s",
        "",
        "| Trial | Load seconds | Events/s | Events | Items | Database bytes |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(
        f"| {trial.trial} | {trial.load_seconds:.6f} | "
        f"{trial.events_per_second:.2f} | {trial.loaded_events} | "
        f"{trial.loaded_items} | {trial.database_bytes} |"
        for trial in report.trials
    )
    lines.extend(
        [
            "",
            "> This is a local correctness-oriented batch-load benchmark, not a "
            "production SLA or a distributed Spark/Hive benchmark.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the offline warehouse loader")
    parser.add_argument("--events", type=int, default=50_000)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--seed", type=int, default=2027)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("build/offline-warehouse/benchmark.json"),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("build/offline-warehouse/benchmark.md"),
    )
    args = parser.parse_args()
    report = run_benchmark(
        event_count=args.events,
        trial_count=args.trials,
        seed=args.seed,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(to_markdown(report), encoding="utf-8")
    print(
        f"offline warehouse benchmark PASS: median {report.median_load_seconds:.6f}s, "
        f"{report.median_events_per_second:.2f} events/s"
    )


if __name__ == "__main__":
    main()
