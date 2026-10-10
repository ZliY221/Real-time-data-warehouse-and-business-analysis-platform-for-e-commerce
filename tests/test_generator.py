from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import copy
import json
from pathlib import Path
import unittest

from event_generator import generate_order_events, validate_order_event
from event_generator.generator import CHANNELS, REGIONS


class GenerateOrderEventsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.start_time = datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)

    def test_generation_is_deterministic(self) -> None:
        first = generate_order_events(10, seed=7, start_time=self.start_time)
        second = generate_order_events(10, seed=7, start_time=self.start_time)
        self.assertEqual(first, second)

    def test_event_and_order_ids_are_unique(self) -> None:
        events = generate_order_events(100, seed=8, start_time=self.start_time)
        event_ids = {event["event_id"] for event in events}
        order_ids = {event["payload"]["order_id"] for event in events}
        self.assertEqual(100, len(event_ids))
        self.assertEqual(100, len(order_ids))

    def test_total_amount_matches_item_lines(self) -> None:
        events = generate_order_events(100, seed=9, start_time=self.start_time)
        for event in events:
            payload = event["payload"]
            expected = sum(Decimal(item["line_amount"]) for item in payload["items"])
            self.assertEqual(expected, Decimal(payload["total_amount"]))

    def test_required_envelope_values_are_present(self) -> None:
        event = generate_order_events(1, seed=10, start_time=self.start_time)[0]
        self.assertEqual("1.0", event["schema_version"])
        self.assertEqual("order_created", event["event_type"])
        self.assertEqual("order-service", event["source"])
        self.assertTrue(event["event_time"].endswith("Z"))
        self.assertTrue(event["ingest_time"].endswith("Z"))

    def test_generated_events_pass_business_contract(self) -> None:
        events = generate_order_events(100, seed=11, start_time=self.start_time)
        for event in events:
            self.assertEqual([], validate_order_event(event))

    def test_invalid_amount_is_reported(self) -> None:
        event = generate_order_events(1, seed=12, start_time=self.start_time)[0]
        invalid = copy.deepcopy(event)
        invalid["payload"]["total_amount"] = "0.01"
        errors = validate_order_event(invalid)
        self.assertIn("total_amount does not equal the sum of item line amounts", errors)

    def test_generator_enums_match_json_schema(self) -> None:
        schema_path = Path(__file__).parents[1] / "schemas" / "order_created_v1.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        properties = schema["properties"]["payload"]["properties"]
        self.assertEqual(set(REGIONS), set(properties["region"]["enum"]))
        self.assertEqual(set(CHANNELS), set(properties["channel"]["enum"]))

    def test_negative_count_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            generate_order_events(-1, start_time=self.start_time)

    def test_naive_start_time_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            generate_order_events(1, start_time=datetime(2026, 10, 2, 10, 0))

    def test_load_event_time_density_is_deterministic(self) -> None:
        events = generate_order_events(
            4,
            seed=13,
            start_time=self.start_time,
            events_per_second=4,
        )
        self.assertEqual(
            [
                "2026-10-02T10:00:00Z",
                "2026-10-02T10:00:00.250000Z",
                "2026-10-02T10:00:00.500000Z",
                "2026-10-02T10:00:00.750000Z",
            ],
            [event["event_time"] for event in events],
        )
        for event in events:
            self.assertEqual([], validate_order_event(event))

    def test_non_positive_load_rate_is_rejected(self) -> None:
        for rate in (0, -1):
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                generate_order_events(
                    1,
                    start_time=self.start_time,
                    events_per_second=rate,
                )


if __name__ == "__main__":
    unittest.main()

