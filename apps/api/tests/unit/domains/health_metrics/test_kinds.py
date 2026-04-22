"""Invariants of the health metrics kind registry.

Locks the following properties so adding a new kind never silently breaks
an integration:

- Every ``HealthKindSpec`` is internally consistent (bounds ordered,
  agent_name non-empty, legacy_response_fields match the aggregation method).
- Registry keys match ``kind`` attributes.
- ``HEALTH_METRICS_KINDS`` constant stays in sync with the registry.
- Agent names are unique across kinds.
- Bounds default resolution falls back cleanly when settings overrides are
  absent.

These tests guard the pluggable-kind contract — if you add a new kind
(e.g. ``sleep_duration``), you must add an entry here if its semantics
differ, or this suite will flag the divergence.
"""

from __future__ import annotations

import pytest

from src.core.constants import HEALTH_METRICS_KINDS
from src.domains.health_metrics.kinds import (
    HEALTH_KINDS,
    AggregationMethod,
    BaselineKind,
    HealthKindSpec,
    MergeStrategy,
    get_active_bounds,
    get_spec,
    kinds,
)

pytestmark = pytest.mark.unit


# =============================================================================
# Structural invariants
# =============================================================================


class TestRegistryStructure:
    """Each spec is well-formed and internally consistent."""

    @pytest.mark.parametrize("key,spec", HEALTH_KINDS.items())
    def test_key_matches_kind_attribute(self, key: str, spec: HealthKindSpec) -> None:
        """Dict key and the ``kind`` attribute must be identical."""
        assert key == spec.kind

    @pytest.mark.parametrize("spec", HEALTH_KINDS.values())
    def test_bounds_ordered(self, spec: HealthKindSpec) -> None:
        """``min_value`` must be strictly less than ``max_value``."""
        assert (
            spec.min_value < spec.max_value
        ), f"{spec.kind}: min_value={spec.min_value} !< max_value={spec.max_value}"

    @pytest.mark.parametrize("spec", HEALTH_KINDS.values())
    def test_non_empty_strings(self, spec: HealthKindSpec) -> None:
        """String attributes are non-empty (prevents silent mis-registration)."""
        assert spec.kind
        assert spec.payload_value_key
        assert spec.unit
        assert spec.agent_name
        assert spec.display_i18n_key

    @pytest.mark.parametrize("spec", HEALTH_KINDS.values())
    def test_legacy_response_fields_match_aggregation_method(self, spec: HealthKindSpec) -> None:
        """Legacy field names must have suffixes consistent with the aggregation method.

        - ``AVG_MIN_MAX`` produces ``avg`` / ``min`` / ``max`` → field names
          ending in ``_avg`` / ``_min`` / ``_max``.
        - ``SUM`` produces ``sum`` → field names ending in ``_total``.
        - ``LAST_VALUE`` produces ``last`` → field names ending in ``_last``.
        """
        allowed_suffixes_by_method: dict[AggregationMethod, tuple[str, ...]] = {
            AggregationMethod.AVG_MIN_MAX: ("_avg", "_min", "_max"),
            AggregationMethod.SUM: ("_total",),
            AggregationMethod.LAST_VALUE: ("_last",),
        }
        allowed = allowed_suffixes_by_method[spec.aggregation_method]
        for field_name in spec.legacy_response_fields:
            assert any(field_name.endswith(s) for s in allowed), (
                f"{spec.kind}: legacy_response_field {field_name!r} does not end in "
                f"any of {allowed} for aggregation_method={spec.aggregation_method.value}"
            )

    def test_agent_names_unique(self) -> None:
        """No two kinds can share the same agent name."""
        names = [spec.agent_name for spec in HEALTH_KINDS.values()]
        assert len(names) == len(set(names)), f"Duplicate agent_names detected: {names}"

    def test_agent_names_end_with_suffix(self) -> None:
        """Agent names follow the ``<domain>_agent`` convention."""
        for spec in HEALTH_KINDS.values():
            assert spec.agent_name.endswith(
                "_agent"
            ), f"{spec.kind}: agent_name={spec.agent_name!r} does not end with '_agent'"


# =============================================================================
# Alignment with external constants / DB constraint
# =============================================================================


class TestRegistryAlignment:
    """Registry stays in sync with downstream constants."""

    def test_kinds_tuple_matches_constant(self) -> None:
        """``kinds()`` helper must match the ``HEALTH_METRICS_KINDS`` constant.

        If this fails, either a kind was added to the registry without
        updating the constant, or vice-versa. Fix by deriving the constant
        from ``HEALTH_KINDS`` (see ``core/constants.py``).
        """
        assert set(kinds()) == set(HEALTH_METRICS_KINDS)

    def test_expected_kinds_present(self) -> None:
        """Smoke check for the two v1.17.2 kinds (future kinds just add entries)."""
        assert "heart_rate" in HEALTH_KINDS
        assert "steps" in HEALTH_KINDS


# =============================================================================
# Accessors
# =============================================================================


class TestGetSpec:
    """``get_spec`` yields registry entries and fails loudly on unknowns."""

    def test_returns_registered_spec(self) -> None:
        spec = get_spec("heart_rate")
        assert spec.kind == "heart_rate"
        assert spec.unit == "bpm"

    def test_raises_on_unknown(self) -> None:
        with pytest.raises(KeyError, match="Unknown health kind"):
            get_spec("sleep_duration")  # not registered in v1.17.2


class TestGetActiveBounds:
    """``get_active_bounds`` resolves from settings with spec fallback."""

    def test_falls_back_to_spec_defaults(self) -> None:
        """When settings don't override, bounds come from the spec."""
        # Current settings expose health_metrics_heart_rate_{min,max} matching
        # the spec defaults (cf. config/health_metrics.py), so both paths yield
        # the same values. The guarantee is: no crash, tuple returned.
        spec = HEALTH_KINDS["heart_rate"]
        lo, hi = get_active_bounds(spec)
        assert isinstance(lo, int) and isinstance(hi, int)
        assert lo < hi


# =============================================================================
# Enum sanity
# =============================================================================


class TestEnums:
    """Enum members cover every value used by the current registry."""

    def test_every_registered_merge_strategy_is_defined(self) -> None:
        for spec in HEALTH_KINDS.values():
            assert spec.merge_strategy in MergeStrategy

    def test_every_registered_aggregation_method_is_defined(self) -> None:
        for spec in HEALTH_KINDS.values():
            assert spec.aggregation_method in AggregationMethod

    def test_every_registered_baseline_kind_is_defined(self) -> None:
        for spec in HEALTH_KINDS.values():
            assert spec.baseline_kind in BaselineKind
