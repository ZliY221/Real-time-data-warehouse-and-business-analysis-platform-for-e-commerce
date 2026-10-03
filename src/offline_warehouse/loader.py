"""Transactional, idempotent order-event loading into a dimensional warehouse."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from event_generator.validation import validate_order_event

from .schema import ensure_schema


class WarehouseInputError(ValueError):
    """Raised when the input file cannot be safely loaded."""


class ConflictingEventError(WarehouseInputError):
    """Raised when one event ID maps to more than one business payload."""


@dataclass(frozen=True)
class LoadResult:
    run_id: str
    status: str
    source_records: int
    loaded_events: int
    loaded_items: int
    rejected_records: int
    duplicate_records: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _payload_fingerprint(raw_line: bytes) -> str:
    return hashlib.sha256(raw_line).hexdigest()


def _event_hash(event: dict[str, object]) -> str:
    canonical = json.dumps(
        event,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _read_input_batch(
    input_path: Path,
    run_id: str,
) -> tuple[int, list[tuple[dict[str, object], str]], list[list[object]], int]:
    source_records = 0
    duplicate_records = 0
    seen: dict[str, str] = {}
    valid_events: list[tuple[dict[str, object], str]] = []
    rejected_rows: list[list[object]] = []

    with input_path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            raw_line = raw_line.rstrip(b"\r\n")
            if not raw_line.strip():
                continue
            source_records += 1
            fingerprint = _payload_fingerprint(raw_line)
            try:
                event = json.loads(raw_line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                rejected_rows.append(
                    [
                        run_id,
                        line_number,
                        "invalid_json",
                        "line is not valid UTF-8 JSON",
                        fingerprint,
                        len(raw_line),
                    ]
                )
                continue

            violations = validate_order_event(event)
            if violations:
                rejected_rows.append(
                    [
                        run_id,
                        line_number,
                        "contract_violation",
                        "; ".join(violations[:3])[:500],
                        fingerprint,
                        len(raw_line),
                    ]
                )
                continue

            assert isinstance(event, dict)
            event_id = str(event["event_id"])
            current_hash = _event_hash(event)
            previous_hash = seen.get(event_id)
            if previous_hash is not None:
                if previous_hash != current_hash:
                    raise ConflictingEventError(
                        f"event_id {event_id} has conflicting payloads within the input batch"
                    )
                duplicate_records += 1
                continue
            seen[event_id] = current_hash
            valid_events.append((event, current_hash))

    return source_records, valid_events, rejected_rows, duplicate_records


def _stage_valid_events(
    connection: Any,
    valid_events: list[tuple[dict[str, object], str]],
) -> None:
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix="warehouse-stage-",
            suffix=".ndjson",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            for event, event_hash in valid_events:
                staged_event = dict(event)
                staged_event["_event_hash"] = event_hash
                stream.write(
                    json.dumps(
                        staged_event,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
                stream.write("\n")
        connection.execute(
            """
            CREATE TEMP TABLE staged_valid_events AS
            SELECT *
            FROM read_json(?, format = 'newline_delimited', records = true)
            """,
            [str(temporary_path)],
        )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _insert_native_batch(
    connection: Any,
    *,
    valid_events: list[tuple[dict[str, object], str]],
    run_id: str,
) -> tuple[int, int, int]:
    if not valid_events:
        return 0, 0, 0
    _stage_valid_events(connection, valid_events)

    conflict = connection.execute(
        """
        SELECT staged.event_id
        FROM staged_valid_events AS staged
        JOIN ods.order_events AS stored USING (event_id)
        WHERE staged._event_hash <> stored.event_hash
        LIMIT 1
        """
    ).fetchone()
    if conflict is not None:
        raise ConflictingEventError(
            f"event_id {conflict[0]} conflicts with the stored event"
        )
    duplicate_records = int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM staged_valid_events AS staged
            JOIN ods.order_events AS stored USING (event_id)
            """
        ).fetchone()[0]
    )
    connection.execute(
        """
        CREATE TEMP TABLE staged_new_events AS
        SELECT staged.*
        FROM staged_valid_events AS staged
        LEFT JOIN ods.order_events AS stored USING (event_id)
        WHERE stored.event_id IS NULL
        """
    )

    batch_product_conflict = connection.execute(
        """
        WITH exploded AS (
            SELECT unnest(payload.items) AS item
            FROM staged_new_events
        )
        SELECT item.sku_id
        FROM exploded
        GROUP BY item.sku_id
        HAVING COUNT(DISTINCT item.category) > 1
            OR COUNT(DISTINCT item.unit_price) > 1
        LIMIT 1
        """
    ).fetchone()
    if batch_product_conflict is not None:
        raise ConflictingEventError(
            f"product {batch_product_conflict[0]} changed category or list price within the batch"
        )
    stored_product_conflict = connection.execute(
        """
        WITH exploded AS (
            SELECT unnest(payload.items) AS item
            FROM staged_new_events
        )
        SELECT item.sku_id
        FROM exploded
        JOIN dim.dim_product AS product ON product.sku_id = item.sku_id
        WHERE product.category <> item.category
           OR product.list_unit_price <> CAST(item.unit_price AS DECIMAL(18, 2))
        LIMIT 1
        """
    ).fetchone()
    if stored_product_conflict is not None:
        raise ConflictingEventError(
            f"product {stored_product_conflict[0]} changed category or list price without a dimension policy"
        )

    loaded_events = int(
        connection.execute("SELECT COUNT(*) FROM staged_new_events").fetchone()[0]
    )
    loaded_items = int(
        connection.execute(
            "SELECT COUNT(*) FROM (SELECT unnest(payload.items) FROM staged_new_events)"
        ).fetchone()[0]
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO dim.dim_date
        SELECT DISTINCT
            CAST(strftime(event_time, '%Y%m%d') AS INTEGER),
            CAST(event_time AS DATE),
            CAST(EXTRACT(YEAR FROM event_time) AS SMALLINT),
            CAST(EXTRACT(MONTH FROM event_time) AS TINYINT),
            CAST(EXTRACT(DAY FROM event_time) AS TINYINT),
            CAST(EXTRACT(ISODOW FROM event_time) AS TINYINT)
        FROM staged_new_events
        """
    )
    connection.execute(
        """
        WITH exploded AS (
            SELECT event_time, unnest(payload.items) AS item
            FROM staged_new_events
        ),
        new_products AS (
            SELECT
                item.sku_id AS sku_id,
                MIN(item.category) AS category,
                CAST(MIN(item.unit_price) AS DECIMAL(18, 2)) AS unit_price,
                MIN(event_time) AS first_seen_at
            FROM exploded
            LEFT JOIN dim.dim_product AS product ON product.sku_id = item.sku_id
            WHERE product.sku_id IS NULL
            GROUP BY item.sku_id
        )
        INSERT INTO dim.dim_product
        SELECT
            (SELECT COALESCE(MAX(product_key), 0) FROM dim.dim_product)
                + ROW_NUMBER() OVER (ORDER BY sku_id),
            sku_id,
            category,
            unit_price,
            first_seen_at AT TIME ZONE 'UTC'
        FROM new_products
        """
    )
    connection.execute(
        """
        INSERT INTO ods.order_events
        SELECT
            event_id,
            _event_hash,
            payload.order_id,
            payload.user_id,
            event_time AT TIME ZONE 'UTC',
            ingest_time AT TIME ZONE 'UTC',
            payload.region,
            payload.channel,
            payload.currency,
            CAST(payload.total_amount AS DECIMAL(18, 2)),
            ?
        FROM staged_new_events
        """,
        [run_id],
    )
    connection.execute(
        """
        WITH exploded AS (
            SELECT
                event_id,
                payload.order_id AS order_id,
                event_time,
                ingest_time,
                payload.user_id AS user_id,
                payload.region AS region,
                payload.channel AS channel,
                unnest(payload.items) AS item,
                generate_subscripts(payload.items, 1) AS item_position
            FROM staged_new_events
        )
        INSERT INTO dwd.fact_order_items
        SELECT
            event_id,
            item_position,
            order_id,
            CAST(strftime(event_time, '%Y%m%d') AS INTEGER),
            event_time AT TIME ZONE 'UTC',
            ingest_time AT TIME ZONE 'UTC',
            user_id,
            region.region_key,
            channel.channel_key,
            product.product_key,
            CAST(item.quantity AS INTEGER),
            CAST(item.unit_price AS DECIMAL(18, 2)),
            CAST(item.line_amount AS DECIMAL(18, 2)),
            ?
        FROM exploded
        JOIN dim.dim_region AS region ON region.region_name = exploded.region
        JOIN dim.dim_channel AS channel ON channel.channel_name = exploded.channel
        JOIN dim.dim_product AS product ON product.sku_id = item.sku_id
        """,
        [run_id],
    )
    return loaded_events, loaded_items, duplicate_records


def _completed_result(connection: Any, run_id: str) -> LoadResult | None:
    row = connection.execute(
        """
        SELECT source_records, loaded_events, loaded_items,
               rejected_records, duplicate_records
        FROM meta.etl_runs
        WHERE run_id = ?
        """,
        [run_id],
    ).fetchone()
    if row is None:
        return None
    return LoadResult(run_id, "already_loaded", *(int(value) for value in row))


def load_order_events(input_path: Path, database_path: Path) -> LoadResult:
    """Load one NDJSON batch atomically and return auditable batch statistics.

    Invalid JSON and contract-invalid rows are quarantined with only a hash,
    byte count, and bounded error summary. A reused event ID with a different
    canonical payload is an integrity violation and rolls back the whole batch.
    """

    try:
        import duckdb
    except ImportError as error:  # pragma: no cover - exercised at the CLI boundary
        raise RuntimeError('install the warehouse dependencies with: pip install -e ".[warehouse]"') from error

    input_path = Path(input_path)
    database_path = Path(database_path)
    if not input_path.is_file():
        raise WarehouseInputError(f"input file does not exist: {input_path}")
    database_path.parent.mkdir(parents=True, exist_ok=True)
    input_hash = _file_sha256(input_path)
    run_id = f"warehouse-{input_hash[:20]}"
    started_at = datetime.now(UTC)

    connection = duckdb.connect(str(database_path))
    try:
        ensure_schema(connection)
        if completed := _completed_result(connection, run_id):
            return completed

        connection.begin()
        source_records, valid_events, rejected_rows, duplicate_records = _read_input_batch(
            input_path, run_id
        )
        loaded_events, loaded_items, stored_duplicates = _insert_native_batch(
            connection, valid_events=valid_events, run_id=run_id
        )
        duplicate_records += stored_duplicates
        if rejected_rows:
            connection.executemany(
                "INSERT INTO meta.rejected_records VALUES (?, ?, ?, ?, ?, ?)",
                rejected_rows,
            )
        rejected_records = len(rejected_rows)

        completed_at = datetime.now(UTC)
        connection.execute(
            """
            INSERT INTO meta.etl_runs
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                run_id,
                input_hash,
                input_path.name,
                source_records,
                loaded_events,
                loaded_items,
                rejected_records,
                duplicate_records,
                started_at,
                completed_at,
            ],
        )
        connection.commit()
        return LoadResult(
            run_id,
            "loaded",
            source_records,
            loaded_events,
            loaded_items,
            rejected_records,
            duplicate_records,
        )
    except Exception:
        try:
            connection.rollback()
        except Exception:
            pass
        raise
    finally:
        connection.close()
