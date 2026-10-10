# Offline Warehouse Performance Evidence

## Conclusion

On the same local machine and the same deterministic 1,000-event input, replacing Python-driven row-by-row dimension lookups and inserts with DuckDB-native validated NDJSON staging, `INSERT ... SELECT`, and `UNNEST` reduced the median cold-database load time from **27.393944 seconds** to **0.206895 seconds** across three trials. This is a **132.41× speedup** and a **99.24% load-time reduction** for this controlled input.

A separate five-trial 50,000-event run produced a median of **5.105932 seconds**, or **9,792.53 events/second**. Every trial verified the final ODS row count, DWD item count, and exact `Decimal` GMV after the database was committed and closed.

These are local ecommerce measurements, not production SLAs and not Spark/Hive distributed benchmarks.

## Environment

| Field | Value |
| --- | --- |
| Date | 2026-10-03 |
| Operating system | Windows 11 |
| Architecture | AMD64 |
| Logical CPUs | 16 |
| Python | 3.14.6 |
| DuckDB | 1.5.6 |
| Storage mode | Fresh local DuckDB file for every trial |

The report intentionally excludes hostname, username, absolute paths, and other machine identifiers.

## Benchmark scope

Each measured trial includes:

1. opening a new DuckDB database;
2. creating the warehouse schemas and stable dimensions;
3. reading an already generated deterministic NDJSON file;
4. v1 contract validation and event fingerprinting;
5. staging valid events and loading ODS, DIM, and DWD records;
6. committing and closing the database;
7. reopening it read-only and verifying event count, item count, and exact GMV.

Event generation time is reported separately and is not included in load throughput. Every trial uses a new database, so an idempotent no-op rerun is never measured as a full load.

## Controlled 1,000-event comparison

Input conditions:

- generator seed: `2027`;
- event start: `2026-10-01T00:00:00Z`;
- orders: 1,000;
- order-item rows: 1,980;
- canonical input bytes: 562,185;
- canonical input SHA-256: `d6720e9a5c56d81450a8a7ffbd50ccb75888eb32fd9997dfbcccac3376d3a4fc`.

### Baseline implementation

Git commit: `af54c57 feat: add offline dimensional warehouse`

The baseline performs repeated per-event and per-item SQL lookups and inserts from Python.

| Trial | Load seconds | Events/second |
| ---: | ---: | ---: |
| 1 | 25.930787 | 38.56 |
| 2 | 27.500313 | 36.36 |
| 3 | 27.393944 | 36.50 |
| **Median** | **27.393944** | **36.50** |

The baseline was measured in a detached temporary Git worktree at the exact commit above. The worktree was removed after the third trial.

### Optimized implementation

The optimized loader keeps Python contract validation and conflict semantics, then:

- writes only validated events to an automatically deleted temporary NDJSON staging file;
- lets DuckDB read that file into a temporary table;
- detects stored event and product conflicts with set-based joins;
- inserts dates, products, orders, and item facts using set-based SQL;
- expands item arrays with `UNNEST` and preserves item positions with `generate_subscripts`.

| Trial | Load seconds | Events/second |
| ---: | ---: | ---: |
| 1 | 0.208982 | 4,785.10 |
| 2 | 0.206895 | 4,833.36 |
| 3 | 0.191709 | 5,216.23 |
| **Median** | **0.206895** | **4,833.37** |

Result calculation:

```text
speedup = 27.393944 / 0.206895 = 132.41×
load-time reduction = (1 - 0.206895 / 27.393944) × 100% = 99.24%
```

## 50,000-event capacity-oriented run

Input conditions:

- generator seed: `2027`;
- orders: 50,000;
- order-item rows per trial: 100,323;
- input bytes: 28,254,087;
- input SHA-256: `04e0835049f8d110065eb36c60bbc8d498be0020039bc714cf3dc3047279be06`;
- exact expected GMV: 16,702,509.60 CNY.

| Trial | Load seconds | Events/second | Database bytes |
| ---: | ---: | ---: | ---: |
| 1 | 4.167803 | 11,996.73 | 22,818,816 |
| 2 | 5.099347 | 9,805.18 | 22,556,672 |
| 3 | 5.105932 | 9,792.53 | 22,556,672 |
| 4 | 5.138174 | 9,731.08 | 22,556,672 |
| 5 | 5.106130 | 9,792.15 | 22,818,816 |
| **Median** | **5.105932** | **9,792.53** | — |

The first trial is visibly faster than later trials, so the report uses the median rather than selecting the best value.

## Reproduction

Run the current benchmark:

```powershell
python -m pip install -e ".[warehouse]"
./scripts/benchmark-offline-warehouse.ps1 -Events 50000 -Trials 5
```

Outputs are written to:

- `build/offline-warehouse/benchmark.json`;
- `build/offline-warehouse/benchmark.md`.

The JSON report includes every trial, input hash, package versions, architecture, logical CPU count, row counts, database size, and benchmark scope.

## Interpretation and limits

- The result primarily measures removal of Python-to-database round trips; it does not prove all workloads improve by 132×.
- The events are synthetic and use a six-product catalog, so product dimension cardinality is low.
- The benchmark does not measure peak memory, concurrent writers, concurrent queries, disk saturation, or failure recovery time.
- DuckDB runs in one local process. The result cannot be compared directly with a distributed Spark or Hive job.
- OS file cache, CPU frequency, and background processes were not controlled. Multiple trials and the median reduce, but do not eliminate, this variance.
- Any published performance statement must retain the input size and local benchmark boundary. “System throughput is 9,793 TPS” would be inaccurate; “50,000 synthetic orders loaded at a five-run local median of about 9,793 events/s under the documented benchmark” is defensible.
