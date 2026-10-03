from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

import duckdb

from event_generator.generator import generate_order_events
from offline_warehouse.benchmark import run_benchmark, to_markdown as benchmark_markdown
from offline_warehouse.loader import ConflictingEventError, load_order_events
from offline_warehouse.report import build_report, to_markdown


def write_events(path: Path, events: list[object]) -> None:
    path.write_text(
        "\n".join(
            event if isinstance(event, str) else json.dumps(event, ensure_ascii=False)
            for event in events
        )
        + "\n",
        encoding="utf-8",
    )


class OfflineWarehouseTests(unittest.TestCase):
    def test_load_builds_dimensional_layers_and_exact_daily_metrics(self) -> None:
        events = generate_order_events(20)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "events.ndjson"
            database = root / "warehouse.duckdb"
            write_events(source, events)

            result = load_order_events(source, database)

            self.assertEqual(result.status, "loaded")
            self.assertEqual(result.source_records, 20)
            self.assertEqual(result.loaded_events, 20)
            self.assertEqual(result.rejected_records, 0)
            self.assertEqual(result.duplicate_records, 0)
            expected_items = sum(len(event["payload"]["items"]) for event in events)
            self.assertEqual(result.loaded_items, expected_items)

            connection = duckdb.connect(str(database), read_only=True)
            try:
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM ods.order_events").fetchone()[0],
                    20,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM dwd.fact_order_items").fetchone()[0],
                    expected_items,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM dim.dim_product").fetchone()[0],
                    6,
                )
                actual_gmv = connection.execute(
                    "SELECT SUM(gmv) FROM dws.daily_sales_by_region_channel"
                ).fetchone()[0]
                expected_gmv = sum(
                    (Decimal(event["payload"]["total_amount"]) for event in events),
                    Decimal("0.00"),
                )
                self.assertEqual(actual_gmv, expected_gmv)
                ranks = connection.execute(
                    "SELECT sales_rank FROM ads.daily_category_sales_rank ORDER BY sales_rank"
                ).fetchall()
                self.assertTrue(ranks)
                self.assertEqual(ranks[0][0], 1)
            finally:
                connection.close()

    def test_same_file_is_an_idempotent_completed_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "events.ndjson"
            database = root / "warehouse.duckdb"
            write_events(source, generate_order_events(3))

            first = load_order_events(source, database)
            second = load_order_events(source, database)

            self.assertEqual(first.run_id, second.run_id)
            self.assertEqual(second.status, "already_loaded")
            connection = duckdb.connect(str(database), read_only=True)
            try:
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM ods.order_events").fetchone()[0],
                    3,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM meta.etl_runs").fetchone()[0],
                    1,
                )
            finally:
                connection.close()

    def test_invalid_rows_are_quarantined_without_raw_payload(self) -> None:
        event = generate_order_events(1)[0]
        invalid = json.loads(json.dumps(event))
        invalid["event_id"] = "evt-invalid-private-marker"
        invalid["payload"]["total_amount"] = "0.00"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "events.ndjson"
            database = root / "warehouse.duckdb"
            write_events(source, [event, "not-json-private-marker", invalid])

            result = load_order_events(source, database)

            self.assertEqual(result.loaded_events, 1)
            self.assertEqual(result.rejected_records, 2)
            connection = duckdb.connect(str(database), read_only=True)
            try:
                rows = connection.execute(
                    """
                    SELECT error_type, error_summary, payload_sha256, payload_bytes
                    FROM meta.rejected_records
                    ORDER BY line_number
                    """
                ).fetchall()
                self.assertEqual([row[0] for row in rows], ["invalid_json", "contract_violation"])
                combined = json.dumps(rows, ensure_ascii=False, default=str)
                self.assertNotIn("private-marker", combined)
                self.assertTrue(all(len(row[2]) == 64 and row[3] > 0 for row in rows))
            finally:
                connection.close()

    def test_duplicate_event_inside_batch_is_loaded_once(self) -> None:
        event = generate_order_events(1)[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "events.ndjson"
            database = root / "warehouse.duckdb"
            write_events(source, [event, event])

            result = load_order_events(source, database)

            self.assertEqual(result.loaded_events, 1)
            self.assertEqual(result.duplicate_records, 1)

    def test_conflicting_event_rolls_back_entire_batch(self) -> None:
        existing = generate_order_events(1)[0]
        conflict = json.loads(json.dumps(existing))
        conflict["payload"]["user_id"] = "usr_conflicting"
        second = generate_order_events(1, seed=9090)[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_source = root / "first.ndjson"
            conflict_source = root / "conflict.ndjson"
            database = root / "warehouse.duckdb"
            write_events(first_source, [existing])
            write_events(conflict_source, [second, conflict])
            load_order_events(first_source, database)

            with self.assertRaisesRegex(ConflictingEventError, "conflicts with the stored event"):
                load_order_events(conflict_source, database)

            connection = duckdb.connect(str(database), read_only=True)
            try:
                event_ids = connection.execute(
                    "SELECT event_id FROM ods.order_events ORDER BY event_id"
                ).fetchall()
                self.assertEqual(event_ids, [(existing["event_id"],)])
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM meta.etl_runs").fetchone()[0],
                    1,
                )
            finally:
                connection.close()

    def test_existing_events_in_a_new_batch_are_counted_as_duplicates(self) -> None:
        events = generate_order_events(3)
        new_event = generate_order_events(1, seed=8080)[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_source = root / "first.ndjson"
            second_source = root / "second.ndjson"
            database = root / "warehouse.duckdb"
            write_events(first_source, events)
            write_events(second_source, [events[0], new_event])
            load_order_events(first_source, database)

            result = load_order_events(second_source, database)

            self.assertEqual(result.source_records, 2)
            self.assertEqual(result.loaded_events, 1)
            self.assertEqual(result.duplicate_records, 1)

    def test_report_exports_aggregates_without_business_identifiers(self) -> None:
        events = generate_order_events(4)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "events.ndjson"
            database = root / "warehouse.duckdb"
            write_events(source, events)
            load_order_events(source, database)

            report = build_report(database)
            markdown = to_markdown(report)

            self.assertEqual(report["layer_counts"]["ods_order_events"], 4)
            self.assertIn("Daily category sales rank", markdown)
            serialized = json.dumps(report, ensure_ascii=False)
            for event in events:
                self.assertNotIn(event["event_id"], serialized)
                self.assertNotIn(event["payload"]["order_id"], serialized)
                self.assertNotIn(event["payload"]["user_id"], serialized)

    def test_benchmark_runs_isolated_trials_and_verifies_results(self) -> None:
        report = run_benchmark(event_count=20, trial_count=2, seed=2027)

        self.assertEqual(report.event_count, 20)
        self.assertEqual(report.trial_count, 2)
        self.assertEqual(len(report.trials), 2)
        self.assertTrue(all(trial.loaded_events == 20 for trial in report.trials))
        self.assertGreater(report.median_events_per_second, 0)
        markdown = benchmark_markdown(report)
        self.assertIn("correctness-oriented batch-load benchmark", markdown)
        self.assertNotIn("usr_", markdown)


if __name__ == "__main__":
    unittest.main()
