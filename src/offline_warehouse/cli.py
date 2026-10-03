"""Command line interface for the local dimensional warehouse."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .loader import load_order_events


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the local dimensional warehouse")
    parser.add_argument("--input", type=Path, required=True, help="order event NDJSON input")
    parser.add_argument("--database", type=Path, required=True, help="DuckDB database path")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = load_order_events(args.input, args.database)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
