"""Configurable data-quality checks for ecommerce event batches."""

from .engine import QualityConfigurationError, evaluate_ndjson, load_quality_config
from .history import QualityHistoryStore, StoredRuleResult, StoredRun
from .models import QualityReport, RuleResult

__all__ = [
    "QualityConfigurationError",
    "QualityReport",
    "QualityHistoryStore",
    "RuleResult",
    "StoredRuleResult",
    "StoredRun",
    "evaluate_ndjson",
    "load_quality_config",
]
