"""Central registry of health metric kinds.

Single source of truth for every kind's semantics:

- **Validation bounds** (``min_value``, ``max_value``) with optional per-kind
  override via ``.env`` (`HEALTH_METRICS_<KIND>_MIN`, `_MAX`).
- **Merge strategy** for intra-batch deduplication
  (see :func:`src.domains.health_metrics.repository._merge_duplicate_samples`).
- **Aggregation method** for bucketed charts and summaries
  (see :func:`src.domains.health_metrics.aggregator.aggregate_samples`).
- **Baseline kind** (daily sum vs daily average) for long-term comparisons.
- **Agent name** for the LangGraph catalogue registration.
- **i18n display key** for the Settings UI.
- **Legacy response fields** for backward-compatible aggregation responses.

Adding a new kind is a single-file edit here plus a per-kind tool pack;
see ``docs/technical/HEALTH_METRICS.md`` for the full checklist.

Phase: evolution — Health Metrics (assistant agents + extensibility)
Created: 2026-04-22
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MergeStrategy(str, Enum):
    """Strategy for collapsing intra-batch duplicates on (date_start, date_end)."""

    MAX = "max"
    """Keep the largest value in the group (e.g. steps: Watch vs iPhone undercount)."""

    AVG_ROUNDED = "avg_rounded"
    """Arithmetic mean rounded to nearest int (e.g. heart_rate: sensor fusion)."""

    MIN = "min"
    """Keep the smallest value in the group."""

    SUM = "sum"
    """Sum values across the group (rare; use with care on overlapping samples)."""

    LAST_WINS = "last_wins"
    """Keep the last sample encountered (fallback for forward-compat unknown kinds)."""


class AggregationMethod(str, Enum):
    """How to aggregate samples within a time bucket for charts / summaries."""

    SUM = "sum"
    """Add values (e.g. steps total over the bucket)."""

    AVG_MIN_MAX = "avg_min_max"
    """Compute average + min + max across the bucket (e.g. heart_rate)."""

    LAST_VALUE = "last_value"
    """Keep the latest sample in the bucket (e.g. instantaneous state metrics)."""


class BaselineKind(str, Enum):
    """How to compute a user's per-day baseline value for a kind."""

    DAILY_SUM = "daily_sum"
    """Sum samples per day (e.g. steps: 8500/day baseline)."""

    DAILY_AVG = "daily_avg"
    """Average samples per day (e.g. heart_rate: 68 bpm baseline)."""

    RESTING = "resting"
    """Placeholder for sleep-aware resting values (future, requires sleep data)."""


@dataclass(frozen=True, slots=True)
class HealthKindSpec:
    """Canonical declaration of one health metric kind.

    Consumed by every integration point (validation, merge, aggregation,
    baseline computation, catalogue registration, Heartbeat source, Journal
    context, Memory biometric enrichment). Dataclass is ``frozen`` so the
    registry cannot be mutated at runtime by accident.

    Attributes:
        kind: Discriminator value stored in ``health_samples.kind`` (also the
            suffix in the ingestion endpoint URL, e.g. ``/ingest/health/steps``).
        payload_value_key: Name of the scalar field in the client-side JSON
            payload. Usually equal to ``kind`` but kept separate for clarity
            (a future ``sleep_duration`` kind might carry the value under the
            key ``duration_minutes`` rather than ``sleep_duration``).
        unit: Human-readable unit shown in UI and LLM responses
            (``"bpm"``, ``"steps"``, ``"minutes"``, ``"%"``...).
        min_value: Default lower bound for physiological validation. Overridable
            via ``.env`` as ``HEALTH_METRICS_<KIND>_MIN``.
        max_value: Default upper bound for physiological validation. Overridable
            via ``.env`` as ``HEALTH_METRICS_<KIND>_MAX``.
        merge_strategy: Arbitration when multiple samples in the same batch
            share ``(date_start, date_end)``.
        aggregation_method: How to aggregate within a time bucket for charts.
        baseline_kind: How to compute the user's per-day baseline.
        agent_name: LangGraph agent identifier registered in
            :func:`src.main.lifespan` (e.g. ``"steps_agent"``).
        display_i18n_key: i18next key resolving to the human-readable name
            in the Settings UI.
        legacy_response_fields: Names of the fields currently present on
            :class:`src.domains.health_metrics.schemas.HealthMetricAggregatePoint`
            that this kind should populate. Used by the polymorphic
            aggregator to keep backward compatibility with the frontend
            schema while the new ``metrics_by_kind`` field takes over.
    """

    kind: str
    payload_value_key: str
    unit: str
    min_value: int
    max_value: int
    merge_strategy: MergeStrategy
    aggregation_method: AggregationMethod
    baseline_kind: BaselineKind
    agent_name: str
    display_i18n_key: str
    legacy_response_fields: tuple[str, ...]


# =============================================================================
# Registry
# =============================================================================


HEALTH_KINDS: dict[str, HealthKindSpec] = {
    "heart_rate": HealthKindSpec(
        kind="heart_rate",
        payload_value_key="heart_rate",
        unit="bpm",
        min_value=20,
        max_value=250,
        merge_strategy=MergeStrategy.AVG_ROUNDED,
        aggregation_method=AggregationMethod.AVG_MIN_MAX,
        baseline_kind=BaselineKind.DAILY_AVG,
        agent_name="heart_rate_agent",
        display_i18n_key="healthMetrics.kinds.heart_rate",
        legacy_response_fields=("heart_rate_avg", "heart_rate_min", "heart_rate_max"),
    ),
    "steps": HealthKindSpec(
        kind="steps",
        payload_value_key="steps",
        unit="steps",
        min_value=0,
        max_value=15000,
        merge_strategy=MergeStrategy.MAX,
        aggregation_method=AggregationMethod.SUM,
        baseline_kind=BaselineKind.DAILY_SUM,
        agent_name="steps_agent",
        display_i18n_key="healthMetrics.kinds.steps",
        legacy_response_fields=("steps_total",),
    ),
}


# =============================================================================
# Registry accessors
# =============================================================================


def get_spec(kind: str) -> HealthKindSpec:
    """Return the spec for a given kind, raising a clear error if unknown.

    Args:
        kind: Discriminator value.

    Returns:
        The :class:`HealthKindSpec` for the kind.

    Raises:
        KeyError: If the kind is not registered in :data:`HEALTH_KINDS`.
            The error message lists the available kinds to speed up debugging.
    """
    try:
        return HEALTH_KINDS[kind]
    except KeyError as exc:
        raise KeyError(
            f"Unknown health kind {kind!r}. " f"Registered kinds: {sorted(HEALTH_KINDS)}"
        ) from exc


def get_active_bounds(spec: HealthKindSpec) -> tuple[int, int]:
    """Resolve the effective validation bounds for a kind.

    Reads potential overrides from settings (field names follow the
    convention ``health_metrics_<kind>_min`` / ``_max``). Falls back to
    the defaults declared in the spec.

    Args:
        spec: The kind spec.

    Returns:
        Tuple ``(lo, hi)`` of the currently active bounds.
    """
    # Imported inside the function to keep this module free of runtime
    # configuration dependencies (makes it trivial to unit-test the registry
    # in isolation).
    from src.core.config import settings

    lo: int = getattr(settings, f"health_metrics_{spec.kind}_min", spec.min_value)
    hi: int = getattr(settings, f"health_metrics_{spec.kind}_max", spec.max_value)
    return lo, hi


def kinds() -> tuple[str, ...]:
    """Return the tuple of registered kind discriminators (DB-allowed values).

    Used as a single source of truth for:
    - The ``HEALTH_METRICS_KINDS`` constant exposed to the router / tests.
    - The ``CheckConstraint`` value list in Alembic migrations.
    - Iteration over kinds in cross-kind code (aggregator, service, tools).
    """
    return tuple(HEALTH_KINDS.keys())
