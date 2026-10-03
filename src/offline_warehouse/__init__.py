"""Local analytical warehouse used to demonstrate dimensional ETL semantics."""

from .loader import ConflictingEventError, LoadResult, load_order_events

__all__ = ["ConflictingEventError", "LoadResult", "load_order_events"]
