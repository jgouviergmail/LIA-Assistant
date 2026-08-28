"""Declarative self-check registry (golden signals + in-process probes).

Doctrine:

- **Thresholds live in settings**, referenced here by FIELD NAME — the boot
  assert resolves each name against ``Settings`` so a renamed field refuses to
  boot instead of silently comparing against nothing.
- **A check may declare the alertname it mirrors** (e.g. the redis probe
  mirrors ``RedisDown``): both sources then converge on ONE incident via the
  correlation key — one outage, one incident, whichever observer saw it first.
  A declared alertname must have its runbook file (enforced in CI).
- **Unknown is not healthy, and not an outage either**: blindness (Prometheus
  unreachable, no data) caps the overall verdict at ``degraded``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum


class CheckStatus(str, Enum):
    """Verdict of one check (and of a whole snapshot)."""

    OK = "ok"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


#: Ordering used by ``overall_status`` (higher = worse).
_SEVERITY_RANK: dict[CheckStatus, int] = {
    CheckStatus.OK: 0,
    CheckStatus.UNKNOWN: 1,
    CheckStatus.DEGRADED: 2,
    CheckStatus.CRITICAL: 3,
}


#: Units a check may report. Closed on purpose: the admin panel renders a
#: suffix per entry, so an undeclared unit would be shown as a bare number
#: rather than guessed — and the boot assert refuses one outright.
KNOWN_UNITS: frozenset[str] = frozenset({"", "percent", "seconds", "milliseconds", "count"})


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one check with its exact measured value."""

    check_id: str
    status: CheckStatus
    value: float | None
    detail: str
    alertname: str | None


@dataclass(frozen=True)
class PromCheck:
    """A Prometheus-backed check: catalogue query + settings thresholds.

    The comparator is uniform by design: a value at or above ``warn`` degrades,
    at or above ``crit`` is critical (every current signal is "higher is
    worse"; a lower-is-worse signal would get its own dataclass, not a flag).
    """

    check_id: str
    title: str
    query_id: str
    params: dict[str, float]
    warn_setting: str
    crit_setting: str
    alertname: str | None
    unit: str


@dataclass(frozen=True)
class InProcessCheck:
    """A check evaluated without Prometheus (works while observability is down)."""

    check_id: str
    title: str
    alertname: str | None
    #: Unit of the reported value, from ``KNOWN_UNITS``. Published to the client:
    #: a renderer that infers the unit from the check id eventually infers wrong.
    unit: str = ""
    #: Settings field that must be truthy for this check to run at all. A check
    #: nobody configured is ABSENT from the snapshot — never ``ok`` (which would
    #: claim a measurement nobody took) and never ``unknown`` (which would cap
    #: every default install at ``degraded``).
    enabled_setting: str | None = None


PROM_CHECKS: tuple[PromCheck, ...] = (
    PromCheck(
        check_id="api_error_rate",
        title="HTTP 5xx rate",
        query_id="api_error_rate",
        params={"window_minutes": 15},
        warn_setting="diagnostics_check_api_error_rate_warn",
        crit_setting="diagnostics_check_api_error_rate_crit",
        alertname="HighErrorRate",
        unit="percent",
    ),
    PromCheck(
        check_id="api_latency_p95",
        title="HTTP p95 latency",
        query_id="api_latency_p95",
        params={"window_minutes": 15},
        warn_setting="diagnostics_check_api_latency_p95_warn",
        crit_setting="diagnostics_check_api_latency_p95_crit",
        # Deliberately uncorrelated: the core alert measures p99, this check
        # p95 — folding them into one incident would claim an identity the
        # measures do not have.
        alertname=None,
        unit="seconds",
    ),
    PromCheck(
        check_id="llm_failure_rate",
        title="LLM API failure rate",
        query_id="llm_failure_rate",
        params={"window_minutes": 30},
        warn_setting="diagnostics_check_llm_failure_rate_warn",
        crit_setting="diagnostics_check_llm_failure_rate_crit",
        alertname="LLMAPIFailureRateHigh",
        unit="percent",
    ),
    PromCheck(
        check_id="disk_usage",
        title="Host disk usage",
        query_id="disk_usage_percent",
        params={},
        warn_setting="diagnostics_check_disk_usage_warn",
        crit_setting="diagnostics_check_disk_usage_crit",
        alertname="DiskSpaceCritical",
        unit="percent",
    ),
    PromCheck(
        check_id="memory_usage",
        title="Host memory usage",
        query_id="memory_usage_percent",
        params={},
        warn_setting="diagnostics_check_memory_usage_warn",
        crit_setting="diagnostics_check_memory_usage_crit",
        alertname="HighMemoryUsage",
        unit="percent",
    ),
)

IN_PROCESS_CHECKS: tuple[InProcessCheck, ...] = (
    InProcessCheck(check_id="database", title="PostgreSQL reachability", alertname="DatabaseDown"),
    InProcessCheck(check_id="redis", title="Redis reachability", alertname="RedisDown"),
    InProcessCheck(
        check_id="circuit_breakers",
        title="Open circuit breakers",
        alertname=None,
        unit="count",
    ),
    InProcessCheck(
        check_id="scheduler_tick",
        title="Self-check loop liveness",
        alertname=None,
        unit="seconds",
    ),
    InProcessCheck(
        check_id="platform_egress",
        title="Outbound connectivity",
        alertname=None,
        unit="milliseconds",
        enabled_setting="diagnostics_egress_probe_target",
    ),
)


#: Every check, both kinds — the one place the two registries are read together.
ALL_CHECKS: tuple[PromCheck | InProcessCheck, ...] = (*PROM_CHECKS, *IN_PROCESS_CHECKS)

#: Unit by check id, derived from the registries — never restated by hand.
_UNITS_BY_CHECK_ID: dict[str, str] = {check.check_id: check.unit for check in ALL_CHECKS}


def _assert_prom_queries_and_thresholds(
    proms: tuple[PromCheck, ...],
    settings: object,
    catalogue: Mapping[str, object],
) -> None:
    """Every Prometheus check names a real query and two real, ordered settings.

    Args:
        proms: Prometheus-backed checks.
        settings: The composed settings object.
        catalogue: The named-query catalogue.

    Raises:
        AssertionError: Unknown query id, missing settings field, or warn >= crit.
    """
    for check in proms:
        assert (
            check.query_id in catalogue
        ), f"{check.check_id}: unknown catalogue key '{check.query_id}'"
        for setting_name in (check.warn_setting, check.crit_setting):
            assert hasattr(
                settings, setting_name
            ), f"{check.check_id}: settings field '{setting_name}' does not exist"
        warn = float(getattr(settings, check.warn_setting))
        crit = float(getattr(settings, check.crit_setting))
        assert warn < crit, f"{check.check_id}: warn ({warn}) must be < crit ({crit})"


def _assert_enablement_gates(
    in_process: tuple[InProcessCheck, ...],
    settings: object,
) -> None:
    """A gate nobody can read silently disables its check forever.

    Args:
        in_process: In-process checks.
        settings: The composed settings object.

    Raises:
        AssertionError: A declared gate has no matching settings field.
    """
    for check in in_process:
        gate = check.enabled_setting
        assert gate is None or hasattr(settings, gate), (
            f"{check.check_id}: settings field '{gate}' does not exist — "
            "a gate nobody can read silently disables the check forever"
        )


def _assert_units(checks: tuple[PromCheck | InProcessCheck, ...]) -> None:
    """Every check reports a unit the admin panel knows how to render.

    Args:
        checks: All checks, both kinds.

    Raises:
        AssertionError: A check declares a unit outside ``KNOWN_UNITS``.
    """
    for check in checks:
        assert check.unit in KNOWN_UNITS, (
            f"{check.check_id}: unit '{check.unit}' is not renderable — "
            f"declare one of {sorted(KNOWN_UNITS)} and give it a suffix in the UI"
        )


def assert_check_registry_completeness(
    prom_checks: tuple[PromCheck, ...] | None = None,
    in_process_checks: tuple[InProcessCheck, ...] | None = None,
) -> None:
    """Refuse to run with a structurally broken check registry (boot assert).

    Args:
        prom_checks: Override for tests; defaults to the real registry.
        in_process_checks: Override for tests; defaults to the real registry.

    Raises:
        AssertionError: Duplicate ids, unknown catalogue key, threshold field
            missing on Settings, or warn >= crit.
    """
    from src.core.config import settings
    from src.domains.diagnostics.query_catalogue import QUERY_CATALOGUE

    proms = prom_checks if prom_checks is not None else PROM_CHECKS
    in_process = in_process_checks if in_process_checks is not None else IN_PROCESS_CHECKS

    ids = [c.check_id for c in proms] + [c.check_id for c in in_process]
    assert len(ids) == len(set(ids)), "duplicate check ids"

    _assert_prom_queries_and_thresholds(proms, settings, QUERY_CATALOGUE)
    _assert_enablement_gates(in_process, settings)
    _assert_units((*proms, *in_process))


def with_units(rows: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Attach each stored row's declared unit, read from the registry.

    Snapshots persist the MEASUREMENT, not the unit — the unit belongs to the
    check and would otherwise be frozen into every historical row. The read
    paths therefore join it in, which also means a row written before a unit
    existed renders correctly today.

    Args:
        rows: Per-check rows as stored in the snapshot's JSONB column.

    Returns:
        New dicts (the inputs are never mutated) carrying a ``unit`` key.
    """
    return [{**row, "unit": unit_for(str(row.get("check_id", "")))} for row in rows]


def unit_for(check_id: str) -> str:
    """The unit a check reports, or ``""`` when it reports no value.

    Single lookup for every reader: the unit belongs to the CHECK, not to a
    measurement, so a snapshot stored before a unit existed still renders with
    the right suffix.

    Args:
        check_id: Identifier of the check.

    Returns:
        The declared unit, or an empty string for an unknown id.
    """
    return _UNITS_BY_CHECK_ID.get(check_id, "")


def overall_status(results: list[CheckResult]) -> CheckStatus:
    """Fold per-check verdicts into one snapshot verdict.

    Worst wins, with two deliberate rules: ``unknown`` alone caps at
    ``degraded`` (blind is not healthy, blindness is not an outage), and an
    EMPTY result set is ``degraded`` (no evidence of health is not health).

    Args:
        results: Per-check results.

    Returns:
        The snapshot verdict.
    """
    if not results:
        return CheckStatus.DEGRADED
    worst = max(results, key=lambda r: _SEVERITY_RANK[r.status]).status
    if worst is CheckStatus.UNKNOWN:
        return CheckStatus.DEGRADED
    return worst
