"""Transactional, idempotent order-event loading into a dimensional warehouse."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any

from event_generator.validation import validate_order_event

from .schema import ensure_schema, fetch_one_value


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


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _insert_date(connection: Any, event_time: datetime) -> int:
    calendar_date = event_time.date()
    date_key = int(calendar_date.strftime("%Y%m%d"))
    connection.execute(
        """
        INSERT OR IGNORE INTO dim.dim_date
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            date_key,
            calendar_date,
            calendar_date.year,
            calendar_date.month,
            calendar_date.day,
            calendar_date.isoweekday(),
        ],
    )
    return date_key


def _dimension_key(connection: Any, table: str, key: str, name: str, value: str) -> int:
    row = connection.execute(
        f"SELECT {key} FROM {table} WHERE {name} = ?",  # identifiers are fixed by caller
        [value],
    ).fetchone()
    if row is None:
        raise WarehouseInputError(f"unsupported warehouse dimension value: {value}")
    return int(row[0])


def _product_key(
    connection: Any,
    *,
    sku_id: str,
    category: str,
    unit_price: Decimal,
    first_seen_at: datetime,
) -> int:
    row = connection.execute(
        """
        SELECT product_key, category, list_unit_price
        FROM dim.dim_product
        WHERE sku_id = ?
        """,
        [sku_id],
    ).fetchone()
    if row is not None:
        if row[1] != category or Decimal(row[2]) != unit_price:
            raise ConflictingEventError(
                f"product {sku_id} changed category or list price without a dimension policy"
            )
        return int(row[0])

    product_key = int(
        fetch_one_value(
            connection,
            "SELECT COALESCE(MAX(product_key), 0) + 1 FROM dim.dim_product",
        )
    )
    connection.execute(
        "INSERT INTO dim.dim_product VALUES (?, ?, ?, ?, ?)",
        [product_key, sku_id, category, unit_price, first_seen_at],
    )
    return product_key


def _existing_event_hash(connection: Any, event_id: str) -> str | None:
    row = connection.execute(
        "SELECT event_hash FROM ods.order_events WHERE event_id = ?",
        [event_id],
    ).fetchone()
    return None if row is None else str(row[0])


def _load_event(connection: Any, event: dict[str, object], event_hash: str, run_id: str) -> int:
    payload = event["payload"]
    assert isinstance(payload, dict)
    event_time = _parse_utc(str(event["event_time"]))
    ingest_time = _parse_utc(str(event["ingest_time"]))
    date_key = _insert_date(connection, event_time)
    region = str(payload["region"])
    channel = str(payload["channel"])
    region_key = _dimension_key(
        connection, "dim.dim_region", "region_key", "region_name", region
    )
    channel_key = _dimension_key(
        connection, "dim.dim_channel", "channel_key", "channel_name", channel
    )

    connection.execute(
        """
        INSERT INTO ods.order_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            event["event_id"],
            event_hash,
            payload["order_id"],
            payload["user_id"],
            event_time,
            ingest_time,
            region,
            channel,
            payload["currency"],
            Decimal(str(payload["total_amount"])),
            run_id,
        ],
    )

    items = payload["items"]
    assert isinstance(items, list)
    for item_position, item in enumerate(items, start=1):
        assert isinstance(item, dict)
        unit_price = Decimal(str(item["unit_price"]))
        product_key = _product_key(
            connection,
            sku_id=str(item["sku_id"]),
            category=str(item["category"]),
            unit_price=unit_price,
            first_seen_at=event_time,
        )
        connection.execute(
            """
            INSERT INTO dwd.fact_order_items
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                event["event_id"],
                item_position,
                payload["order_id"],
                date_key,
                event_time,
                ingest_time,
                payload["user_id"],
                region_key,
                channel_key,
                product_key,
                item["quantity"],
                unit_price,
                Decimal(str(item["line_amount"])),
                run_id,
            ],
        )
    return len(items)


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
        source_records = loaded_events = loaded_items = 0
        rejected_records = duplicate_records = 0
        seen: dict[str, str] = {}

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
                    rejected_records += 1
                    connection.execute(
                        "INSERT INTO meta.rejected_records VALUES (?, ?, ?, ?, ?, ?)",
                        [run_id, line_number, "invalid_json", "line is not valid UTF-8 JSON", fingerprint, len(raw_line)],
                    )
                    continue

                violations = validate_order_event(event)
                if violations:
                    rejected_records += 1
                    connection.execute(
                        "INSERT INTO meta.rejected_records VALUES (?, ?, ?, ?, ?, ?)",
                        [
                            run_id,
                            line_number,
                            "contract_violation",
                            "; ".join(violations[:3])[:500],
                            fingerprint,
                            len(raw_line),
                        ],
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

                stored_hash = _existing_event_hash(connection, event_id)
                if stored_hash is not None:
                    if stored_hash != current_hash:
                        raise ConflictingEventError(
                            f"event_id {event_id} conflicts with the stored event"
                        )
                    duplicate_records += 1
                    continue

                loaded_items += _load_event(connection, event, current_hash, run_id)
                loaded_events += 1

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
