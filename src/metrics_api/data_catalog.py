from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Literal


AssetKind = Literal["topic", "stream", "table", "api", "dashboard"]
FreshnessStatus = Literal["fresh", "stale", "no_data"]


class DataCatalogError(ValueError):
    """Raised when the asset catalog is invalid or cannot satisfy a query."""


@dataclass(frozen=True)
class DataAsset:
    asset_id: str
    name: str
    kind: AssetKind
    owner: str
    upstreams: tuple[str, ...]
    freshness_slo_seconds: int | None = None


@dataclass(frozen=True)
class FreshnessEvaluation:
    asset: DataAsset
    status: FreshnessStatus
    evaluated_at: datetime
    observed_at: datetime | None
    lag_seconds: int | None
    impacted_assets: tuple[str, ...]


class DataAssetCatalog:
    def __init__(self, assets: list[DataAsset]) -> None:
        self._assets = {asset.asset_id: asset for asset in assets}
        if len(self._assets) != len(assets):
            raise DataCatalogError("asset ids must be unique")
        if not self._assets:
            raise DataCatalogError("catalog must contain at least one asset")
        for asset in assets:
            missing = [item for item in asset.upstreams if item not in self._assets]
            if missing:
                raise DataCatalogError(
                    f"asset {asset.asset_id} references unknown upstreams: {missing}"
                )
            if asset.asset_id in asset.upstreams:
                raise DataCatalogError(f"asset {asset.asset_id} cannot depend on itself")
        self._assert_acyclic()

    @classmethod
    def from_file(cls, path: Path) -> "DataAssetCatalog":
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            rows = document["assets"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise DataCatalogError(f"cannot load asset catalog: {path}") from error
        if not isinstance(rows, list):
            raise DataCatalogError("assets must be a list")
        assets: list[DataAsset] = []
        for row in rows:
            try:
                slo = row.get("freshness_slo_seconds")
                if slo is not None and (not isinstance(slo, int) or slo <= 0):
                    raise DataCatalogError("freshness_slo_seconds must be positive")
                assets.append(
                    DataAsset(
                        asset_id=str(row["id"]),
                        name=str(row["name"]),
                        kind=row["kind"],
                        owner=str(row["owner"]),
                        upstreams=tuple(str(item) for item in row.get("upstreams", [])),
                        freshness_slo_seconds=slo,
                    )
                )
            except (KeyError, TypeError) as error:
                raise DataCatalogError("asset entry is incomplete") from error
        return cls(assets)

    def get(self, asset_id: str) -> DataAsset:
        try:
            return self._assets[asset_id]
        except KeyError as error:
            raise DataCatalogError(f"unknown asset: {asset_id}") from error

    def list_assets(self) -> tuple[DataAsset, ...]:
        """Return the complete catalog in a stable upstream-first order."""
        ordered: list[DataAsset] = []
        remaining = set(self._assets)
        while remaining:
            ready = sorted(
                asset_id
                for asset_id in remaining
                if all(upstream not in remaining for upstream in self._assets[asset_id].upstreams)
            )
            if not ready:
                raise DataCatalogError("asset lineage must be acyclic")
            for asset_id in ready:
                ordered.append(self._assets[asset_id])
                remaining.remove(asset_id)
        return tuple(ordered)

    def downstream(self, asset_id: str, *, max_depth: int = 10) -> tuple[str, ...]:
        self.get(asset_id)
        if max_depth < 1:
            raise DataCatalogError("max_depth must be at least one")
        reverse: dict[str, list[str]] = {item: [] for item in self._assets}
        for asset in self._assets.values():
            for upstream in asset.upstreams:
                reverse[upstream].append(asset.asset_id)
        queue: list[tuple[str, int]] = [(asset_id, 0)]
        discovered: list[str] = []
        seen = {asset_id}
        while queue:
            current, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for dependent in sorted(reverse[current]):
                if dependent in seen:
                    continue
                seen.add(dependent)
                discovered.append(dependent)
                queue.append((dependent, depth + 1))
        return tuple(discovered)

    def evaluate_freshness(
        self,
        asset_id: str,
        *,
        observed_at: datetime | None,
        evaluated_at: datetime | None = None,
    ) -> FreshnessEvaluation:
        asset = self.get(asset_id)
        if asset.freshness_slo_seconds is None:
            raise DataCatalogError(f"asset {asset_id} has no freshness SLO")
        now = _utc(evaluated_at or datetime.now(UTC))
        observed = _utc(observed_at) if observed_at is not None else None
        lag_seconds = None
        status: FreshnessStatus = "no_data"
        if observed is not None:
            lag_seconds = max(0, int((now - observed).total_seconds()))
            status = (
                "fresh"
                if lag_seconds <= asset.freshness_slo_seconds
                else "stale"
            )
        return FreshnessEvaluation(
            asset=asset,
            status=status,
            evaluated_at=now,
            observed_at=observed,
            lag_seconds=lag_seconds,
            impacted_assets=self.downstream(asset_id),
        )

    def _assert_acyclic(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(asset_id: str) -> None:
            if asset_id in visiting:
                raise DataCatalogError("asset lineage must be acyclic")
            if asset_id in visited:
                return
            visiting.add(asset_id)
            for upstream in self._assets[asset_id].upstreams:
                visit(upstream)
            visiting.remove(asset_id)
            visited.add(asset_id)

        for asset_id in self._assets:
            visit(asset_id)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
