"""Check registry — declarative, settings-thresholded, catalogue-backed.

Thresholds are read from ``settings`` dynamically (never literals in tests —
configs change, hard-coded thresholds silently drift the assertion).
"""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.domains.diagnostics.checks import (
    IN_PROCESS_CHECKS,
    PROM_CHECKS,
    CheckResult,
    CheckStatus,
    PromCheck,
    assert_check_registry_completeness,
    overall_status,
)
from src.domains.diagnostics.query_catalogue import QUERY_CATALOGUE


@pytest.mark.unit
class TestCheckRegistry:
    def test_real_registry_passes_the_boot_assert(self) -> None:
        assert_check_registry_completeness()

    def test_ids_are_unique_across_both_families(self) -> None:
        ids = [c.check_id for c in PROM_CHECKS] + [c.check_id for c in IN_PROCESS_CHECKS]
        assert len(ids) == len(set(ids))

    def test_every_prom_check_query_id_exists_in_the_catalogue(self) -> None:
        for check in PROM_CHECKS:
            assert check.query_id in QUERY_CATALOGUE, check.check_id

    def test_thresholds_resolve_on_settings_and_are_ordered(self) -> None:
        for check in PROM_CHECKS:
            warn = getattr(settings, check.warn_setting)
            crit = getattr(settings, check.crit_setting)
            assert warn < crit, check.check_id

    def test_declared_alertnames_have_a_runbook_file(self) -> None:
        """A check mirroring an alert must point at that alert's runbook."""
        from pathlib import Path

        runbooks = Path(__file__).resolve().parents[6] / "docs" / "runbooks" / "alerts"
        for check in (*PROM_CHECKS, *IN_PROCESS_CHECKS):
            if check.alertname is not None:
                assert (runbooks / f"{check.alertname}.md").is_file(), check.alertname

    def test_duplicate_id_is_refused(self) -> None:
        duplicated = (PROM_CHECKS[0], PROM_CHECKS[0])
        with pytest.raises(AssertionError):
            assert_check_registry_completeness(prom_checks=duplicated)

    def test_unknown_threshold_setting_is_refused(self) -> None:
        bad = PromCheck(
            check_id="bogus",
            title="Bogus",
            query_id="api_error_rate",
            params={},
            warn_setting="diagnostics_check_does_not_exist_warn",
            crit_setting="diagnostics_check_does_not_exist_crit",
            alertname=None,
            unit="percent",
        )
        with pytest.raises(AssertionError):
            assert_check_registry_completeness(prom_checks=(bad,))


@pytest.mark.unit
class TestBootWiring:
    def test_failfast_validations_wire_the_check_registry_assert(self) -> None:
        import inspect

        import src.infrastructure.startup.registries as registries

        assert "_validate_diagnostics_registries" in inspect.getsource(
            registries.run_failfast_validations
        )
        assert "assert_check_registry_completeness" in inspect.getsource(
            registries._validate_diagnostics_registries
        )


@pytest.mark.unit
class TestOverallStatus:
    def _result(self, status: CheckStatus) -> CheckResult:
        return CheckResult(check_id="x", status=status, value=None, detail="", alertname=None)

    def test_critical_wins(self) -> None:
        results = [self._result(CheckStatus.OK), self._result(CheckStatus.CRITICAL)]
        assert overall_status(results) is CheckStatus.CRITICAL

    def test_unknown_alone_caps_at_degraded(self) -> None:
        """Blind is not healthy, but blindness alone is not an outage."""
        results = [self._result(CheckStatus.OK), self._result(CheckStatus.UNKNOWN)]
        assert overall_status(results) is CheckStatus.DEGRADED

    def test_all_ok_is_ok(self) -> None:
        assert overall_status([self._result(CheckStatus.OK)]) is CheckStatus.OK

    def test_empty_results_are_degraded_not_ok(self) -> None:
        """No evidence of health is not health."""
        assert overall_status([]) is CheckStatus.DEGRADED


@pytest.mark.unit
class TestEveryCheckPublishesItsUnit:
    """A renderer that guesses the unit eventually guesses wrong.

    The admin panel used to derive the suffix from the check id, with `%` as
    the fallback — so a new check measuring milliseconds would have rendered
    "12.3%". ADR-184 doctrine: what the system knows, it publishes to whoever
    must produce or display the value.
    """

    def test_every_check_declares_a_unit_from_the_closed_set(self) -> None:
        from src.domains.diagnostics.checks import (
            IN_PROCESS_CHECKS,
            KNOWN_UNITS,
            PROM_CHECKS,
        )

        for check in (*PROM_CHECKS, *IN_PROCESS_CHECKS):
            assert check.unit in KNOWN_UNITS, f"{check.check_id}: unit '{check.unit}'"

    def test_an_unknown_unit_refuses_to_boot(self) -> None:
        from src.domains.diagnostics.checks import (
            InProcessCheck,
            assert_check_registry_completeness,
        )

        rogue = (InProcessCheck(check_id="x", title="X", alertname=None, unit="furlongs"),)
        with pytest.raises(AssertionError, match="furlongs"):
            assert_check_registry_completeness(prom_checks=(), in_process_checks=rogue)

    def test_unit_for_is_the_single_lookup(self) -> None:
        from src.domains.diagnostics.checks import unit_for

        assert unit_for("api_latency_p95") == "seconds"
        assert unit_for("platform_egress") == "milliseconds"
        assert unit_for("database") == ""
        assert unit_for("nonexistent") == ""

    def test_a_snapshot_row_stored_before_this_change_still_gets_its_unit(self) -> None:
        """The unit belongs to the CHECK, not to the measurement — so old rows win too."""
        from src.domains.diagnostics.schemas import CheckResultOut

        out = CheckResultOut(check_id="api_latency_p95", status="ok", value=0.21)
        assert out.unit == "seconds"
