"""Export a bounded, privacy-safe verification report from the local warehouse."""

from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from typing import Any


class WarehouseReportError(ValueError):
    """Raised when a report cannot be built from the requested database."""


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, date):
        return value.isoformat()
    return value


def _rows(connection: Any, query: str) -> list[dict[str, object]]:
    result = connection.execute(query)
    names = [column[0] for column in result.description]
    return [
        {name: _json_value(value) for name, value in zip(names, row, strict=True)}
        for row in result.fetchall()
    ]


def build_report(database_path: Path) -> dict[str, object]:
    """Read aggregate warehouse evidence without exporting event or user identifiers."""

    try:
        import duckdb
    except ImportError as error:  # pragma: no cover - exercised at the CLI boundary
        raise RuntimeError('install the warehouse dependencies with: pip install -e ".[warehouse]"') from error

    database_path = Path(database_path)
    if not database_path.is_file():
        raise WarehouseReportError(f"warehouse database does not exist: {database_path}")

    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        runs = _rows(
            connection,
            """
            SELECT run_id, input_name, source_records, loaded_events, loaded_items,
                   rejected_records, duplicate_records
            FROM meta.etl_runs
            ORDER BY completed_at DESC, run_id DESC
            LIMIT 20
            """,
        )
        if not runs:
            raise WarehouseReportError("warehouse contains no completed ETL runs")
        counts = {
            row[0]: int(row[1])
            for row in connection.execute(
                """
                SELECT 'ods_order_events', COUNT(*) FROM ods.order_events
                UNION ALL
                SELECT 'dwd_fact_order_items', COUNT(*) FROM dwd.fact_order_items
                UNION ALL
                SELECT 'dim_products', COUNT(*) FROM dim.dim_product
                UNION ALL
                SELECT 'rejected_records', COUNT(*) FROM meta.rejected_records
                """
            ).fetchall()
        }
        daily_sales = _rows(
            connection,
            """
            SELECT calendar_date, region, channel, order_count, customer_count,
                   gmv, average_order_value
            FROM dws.daily_sales_by_region_channel
            ORDER BY calendar_date, region, channel
            LIMIT 100
            """,
        )
        category_rank = _rows(
            connection,
            """
            SELECT calendar_date, category, units_sold, sales_amount, sales_rank
            FROM ads.daily_category_sales_rank
            ORDER BY calendar_date, sales_rank, category
            LIMIT 100
            """,
        )
        return {
            "database_name": database_path.name,
            "layer_counts": counts,
            "etl_runs": runs,
            "daily_sales": daily_sales,
            "daily_category_sales_rank": category_rank,
        }
    except WarehouseReportError:
        raise
    except Exception as error:
        raise WarehouseReportError("database does not contain the expected warehouse schema") from error
    finally:
        connection.close()


def to_markdown(report: dict[str, object]) -> str:
    counts = report["layer_counts"]
    assert isinstance(counts, dict)
    runs = report["etl_runs"]
    daily_sales = report["daily_sales"]
    category_rank = report["daily_category_sales_rank"]
    assert isinstance(runs, list)
    assert isinstance(daily_sales, list)
    assert isinstance(category_rank, list)
    lines = [
        "# Offline Warehouse Verification",
        "",
        f"Database: `{report['database_name']}`",
        "",
        "## Layer counts",
        "",
        "| Dataset | Rows |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {name} | {value} |" for name, value in sorted(counts.items()))
    lines.extend(
        [
            "",
            "## ETL runs",
            "",
            "| Run ID | Input | Source | Loaded events | Loaded items | Rejected | Duplicates |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for run in runs:
        lines.append(
            f"| {run['run_id']} | {run['input_name']} | {run['source_records']} | "
            f"{run['loaded_events']} | {run['loaded_items']} | "
            f"{run['rejected_records']} | {run['duplicate_records']} |"
        )
    lines.extend(
        [
            "",
            "## Daily sales by region and channel",
            "",
            "| Date | Region | Channel | Orders | Customers | GMV | AOV |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in daily_sales:
        lines.append(
            f"| {row['calendar_date']} | {row['region']} | {row['channel']} | "
            f"{row['order_count']} | {row['customer_count']} | {row['gmv']} | "
            f"{row['average_order_value']} |"
        )
    lines.extend(
        [
            "",
            "## Daily category sales rank",
            "",
            "| Date | Category | Units | Sales | Rank |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    for row in category_rank:
        lines.append(
            f"| {row['calendar_date']} | {row['category']} | {row['units_sold']} | "
            f"{row['sales_amount']} | {row['sales_rank']} |"
        )
    lines.extend(
        [
            "",
            "> This report intentionally excludes event IDs, order IDs, and user IDs.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export offline warehouse verification")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.database)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(to_markdown(report), encoding="utf-8")
    print(
        f"warehouse report PASS: {len(report['etl_runs'])} run(s), "
        f"{report['layer_counts']['ods_order_events']} order event(s)"
    )


if __name__ == "__main__":
    main()
