from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from event_generator import generate_order_events
from event_generator.validate_cli import main


class ValidateCliTests(unittest.TestCase):
    def _write_events(self, events: list[dict[str, object]]) -> Path:
        handle = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".ndjson", delete=False
        )
        with handle:
            for event in events:
                handle.write(json.dumps(event, ensure_ascii=False))
                handle.write("\n")
        self.addCleanup(handle.name.unlink if isinstance(handle.name, Path) else Path(handle.name).unlink)
        return Path(handle.name)

    def test_valid_file_passes(self) -> None:
        events = generate_order_events(
            3, seed=22, start_time=datetime(2026, 10, 2, tzinfo=timezone.utc)
        )
        path = self._write_events(events)
        with patch.object(sys, "argv", ["validate", "--input", str(path), "--expected-count", "3"]):
            with redirect_stdout(io.StringIO()):
                main()

    def test_wrong_count_fails(self) -> None:
        events = generate_order_events(
            1, seed=23, start_time=datetime(2026, 10, 2, tzinfo=timezone.utc)
        )
        path = self._write_events(events)
        with patch.object(sys, "argv", ["validate", "--input", str(path), "--expected-count", "2"]):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main()


if __name__ == "__main__":
    unittest.main()

