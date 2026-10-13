from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
import unittest

from metrics_api.data_catalog import DataAssetCatalog, DataCatalogError


class DataAssetCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = DataAssetCatalog.from_file(
            Path(__file__).parents[1] / "config" / "data-assets.json"
        )

    def test_downstream_impact_is_ordered_by_lineage_depth(self) -> None:
        self.assertEqual(
            ("api.metrics", "dashboard.operations"),
            self.catalog.downstream("clickhouse.minute-metrics"),
        )

    def test_catalog_listing_is_stable_and_upstream_first(self) -> None:
        assets = self.catalog.list_assets()
        positions = {asset.asset_id: index for index, asset in enumerate(assets)}
        self.assertEqual(5, len(assets))
        for asset in assets:
            for upstream in asset.upstreams:
                self.assertLess(positions[upstream], positions[asset.asset_id])

    def test_freshness_evaluation_exposes_slo_and_impact(self) -> None:
        evaluation = self.catalog.evaluate_freshness(
            "clickhouse.minute-metrics",
            observed_at=datetime(2026, 10, 13, 8, 0, 10, tzinfo=UTC),
            evaluated_at=datetime(2026, 10, 13, 8, 2, 15, tzinfo=UTC),
        )
        self.assertEqual("stale", evaluation.status)
        self.assertEqual(125, evaluation.lag_seconds)
        self.assertEqual(("api.metrics", "dashboard.operations"), evaluation.impacted_assets)

    def test_missing_observation_is_explicit(self) -> None:
        evaluation = self.catalog.evaluate_freshness(
            "clickhouse.minute-metrics",
            observed_at=None,
            evaluated_at=datetime(2026, 10, 13, 8, 2, tzinfo=UTC),
        )
        self.assertEqual("no_data", evaluation.status)
        self.assertIsNone(evaluation.lag_seconds)

    def test_invalid_catalog_rejects_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(
                json.dumps(
                    {
                        "assets": [
                            {"id": "a", "name": "A", "kind": "table", "owner": "x", "upstreams": ["b"]},
                            {"id": "b", "name": "B", "kind": "table", "owner": "x", "upstreams": ["a"]},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(DataCatalogError, "acyclic"):
                DataAssetCatalog.from_file(path)
