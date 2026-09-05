"""What to fetch for WHICH incident before the diagnostician reads it (ADR-266).

Four diagnoses out of four (2026-09-02 → 2026-09-05) ended in "insufficient
evidence" while Prometheus held the breakdown (two failed operations out of
eight, both ``http_500``) and Loki held the failing path (every failure on
``rag_injection_failed``). The pack the model received had seven fields and no
way to reach either. A recipe declares, per CORRELATION key, the catalogue
queries and the log events worth reading for that incident — nothing free-form
ever reaches a telemetry backend (ADR-247 pillar 1).

Keyed by correlation key on purpose: an alert-sourced and a self-check-sourced
incident for the same outage share one key, so they share one recipe. The boot
assert (ADR-085 doctrine) refuses a registry that leaves a check's key without a
recipe, names a catalogue query that does not exist, or fetches nothing without
saying why. Whether every LOADED alert has a recipe is asserted in CI, where the
rendered rule file is at hand (`test_evidence_recipes.py`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.core.constants import DIAGNOSTICS_CONTEXT_WINDOW_MINUTES
from src.domains.diagnostics.logql import DiagService


@dataclass(frozen=True)
class LogRecipe:
    """Which log lines to read for an incident (bounded by the LogQL builder).

    Attributes:
        service: Compose service whose stream is read (closed enum).
        events: structlog event names kept; EMPTY means every line of the
            service — for containers that do not log structlog JSON (the backup
            sidecar), where the level and the raw line are all there is.
        levels: Levels kept when a line carries one; a line without a level
            label (non-structlog container) is kept regardless.
    """

    service: DiagService = DiagService.API
    events: tuple[str, ...] = ()
    levels: tuple[str, ...] = ("error", "warning")


@dataclass(frozen=True)
class EvidenceRecipe:
    """The evidence worth fetching for one correlation key.

    Attributes:
        correlation_key: The alertname a check mirrors, else its check id.
        prom_queries: Catalogue query ids rendered with ``window_minutes``.
        logs: What to read from Loki, or None for no log excerpt.
        window_minutes: Look-back for both sources (clamped by the builders).
        reason_for_none: Written justification when the recipe fetches nothing
            — the boot assert refuses an empty recipe that stays silent.
    """

    correlation_key: str
    prom_queries: tuple[str, ...] = ()
    logs: LogRecipe | None = None
    window_minutes: int = DIAGNOSTICS_CONTEXT_WINDOW_MINUTES
    reason_for_none: str = ""


_EMBEDDING_BREAKDOWNS: tuple[str, ...] = (
    "embedding_outcomes_by_result",
    "embedding_calls_by_status",
    "embedding_shaper_by_outcome",
    "embedding_errors_by_reason",
)

_EMBEDDING_LOGS = LogRecipe(
    events=(
        "gemini_embedding_failed",
        "max_retries_exceeded",
        "rag_injection_failed",
        "system_rag_injection_failed",
    ),
)

_LLM_LOGS = LogRecipe(events=("llm_api_call_failed", "circuit_breaker_opened"))

_HTTP_LOGS = LogRecipe(events=("request_failed", "internal_server_error", "unhandled_exception"))

_REDIS_LOGS = LogRecipe(
    events=(
        "health_check_redis_failed",
        "redis_initialization_failed",
        "scheduler_leader_redis_unavailable",
        "rate_limit_redis_error",
    ),
)

_LEDGER_LOGS = LogRecipe(
    events=(
        "effect_unrecorded",
        "effect_refused_ledger_unavailable",
        "effect_orphans_sync_failed",
        "ledger_volume_sync_failed",
        "ledger_chain_sync_failed",
        "ledger_notary_pass_failed",
        "ledger_notary_account_failed",
    ),
)

#: One recipe per correlation key. Alert names are those of
#: ``alerts-core.yml`` — the only rule file Prometheus loads (ADR-119) — plus
#: the keys of the checks that mirror a legacy alert or no alert at all.
EVIDENCE_RECIPES: dict[str, EvidenceRecipe] = {
    recipe.correlation_key: recipe
    for recipe in (
        # ---- availability -----------------------------------------------
        EvidenceRecipe(
            "ServiceDown",
            prom_queries=("dependency_up", "http_request_rate"),
            logs=_HTTP_LOGS,
        ),
        EvidenceRecipe(
            "DatabaseDown",
            prom_queries=("dependency_up",),
            logs=LogRecipe(
                events=("health_check_database_failed", "db_connection_budget_overcommit")
            ),
        ),
        EvidenceRecipe("RedisDown", prom_queries=("dependency_up",), logs=_REDIS_LOGS),
        EvidenceRecipe(
            "RedisConnectionPoolExhaustion", prom_queries=("dependency_up",), logs=_REDIS_LOGS
        ),
        EvidenceRecipe(
            "GlobalRateLimitDegraded",
            prom_queries=("dependency_up",),
            logs=LogRecipe(events=("rate_limit_redis_error", "rate_limit_script_load_failed")),
        ),
        # ---- host & containers ------------------------------------------
        EvidenceRecipe("DiskSpaceCritical", prom_queries=("disk_usage_percent",)),
        EvidenceRecipe("ContainerMemoryNearLimit", prom_queries=("memory_usage_percent",)),
        EvidenceRecipe("HighMemoryUsage", prom_queries=("memory_usage_percent",)),
        EvidenceRecipe(
            "ContainerRestartLoop",
            prom_queries=("dependency_up", "http_request_rate", "background_job_errors"),
            logs=_HTTP_LOGS,
        ),
        # ---- API & answer path ------------------------------------------
        EvidenceRecipe(
            "HighErrorRate",
            prom_queries=("api_error_rate", "http_request_rate", "llm_errors_by_kind"),
            logs=_HTTP_LOGS,
        ),
        EvidenceRecipe(
            "SSELatencyP95High",
            prom_queries=("api_latency_p95", "http_request_rate", "llm_errors_by_kind"),
            logs=LogRecipe(events=("sse_stream_error", "llm_api_call_failed")),
        ),
        EvidenceRecipe(
            "api_latency_p95",
            prom_queries=("api_latency_p95", "http_request_rate", "llm_errors_by_kind"),
            logs=LogRecipe(events=("sse_stream_error", "llm_api_call_failed")),
        ),
        # ---- LLM & embeddings -------------------------------------------
        EvidenceRecipe(
            "LLMAPIFailureRateHigh",
            prom_queries=("llm_failure_rate", "llm_errors_by_kind", "circuit_breakers_open"),
            logs=_LLM_LOGS,
        ),
        EvidenceRecipe(
            "LLMCallsWithoutUsage", prom_queries=("llm_errors_by_kind",), logs=_LLM_LOGS
        ),
        EvidenceRecipe(
            "circuit_breakers",
            prom_queries=("circuit_breakers_open", "llm_errors_by_kind"),
            logs=LogRecipe(events=("circuit_breaker_opened", "circuit_breaker_rejected_request")),
        ),
        EvidenceRecipe(
            "EmbeddingOperationsFailing",
            prom_queries=("embedding_failure_rate", *_EMBEDDING_BREAKDOWNS),
            logs=_EMBEDDING_LOGS,
        ),
        EvidenceRecipe(
            "SystemKnowledgeIndexationFailing",
            prom_queries=_EMBEDDING_BREAKDOWNS,
            logs=LogRecipe(
                events=(
                    "gemini_embedding_failed",
                    "max_retries_exceeded",
                    "system_rag_startup_failed",
                    "system_rag_startup_error",
                )
            ),
        ),
        # ---- schedulers -------------------------------------------------
        EvidenceRecipe(
            "scheduler_tick",
            prom_queries=("background_job_errors",),
            logs=LogRecipe(
                events=("diagnostics_self_check_failed", "diagnostics_diagnosis_pump_failed")
            ),
        ),
        # ---- backup & public path ---------------------------------------
        EvidenceRecipe(
            "BackupFailed",
            prom_queries=("disk_usage_percent",),
            # Not a structlog container: every line of the sidecar is kept.
            logs=LogRecipe(service=DiagService.POSTGRES_BACKUP, levels=()),
        ),
        EvidenceRecipe(
            "PublicEndpointDown",
            prom_queries=("dependency_up", "http_request_rate"),
            # The tunnel is a host process outside every compose stream; the
            # API can only show whether it is itself answering.
        ),
        EvidenceRecipe(
            "CertificateExpirySoon",
            reason_for_none="a certificate's expiry is a date, not a signal any "
            "metric or log line of this stack elaborates on",
        ),
        EvidenceRecipe(
            "platform_egress",
            reason_for_none="the probe's own detail already names the unreachable "
            "target; nothing in Prometheus or Loki sees further than the socket",
        ),
        # ---- observability tier -----------------------------------------
        EvidenceRecipe("AlertmanagerDown", prom_queries=("dependency_up",)),
        EvidenceRecipe("ObservabilityScrapeTargetMissing", prom_queries=("dependency_up",)),
        # ---- transparency registers (ADR-263) ---------------------------
        EvidenceRecipe(
            "EffectLedgerClaimedOrphans", prom_queries=("effect_register_gaps",), logs=_LEDGER_LOGS
        ),
        EvidenceRecipe(
            "EffectLedgerUnavailable",
            prom_queries=("effect_register_gaps", "dependency_up"),
            logs=_LEDGER_LOGS,
        ),
        EvidenceRecipe("TransparencyRegisterGrowth", prom_queries=("transparency_register_bytes",)),
        EvidenceRecipe(
            "TransparencyRegisterNotOpen",
            prom_queries=("transparency_register_bytes",),
            logs=_LEDGER_LOGS,
        ),
        EvidenceRecipe("LedgerChainBroken", logs=_LEDGER_LOGS),
        EvidenceRecipe(
            "LedgerNotaryStalled",
            prom_queries=("background_job_errors",),
            logs=_LEDGER_LOGS,
        ),
    )
}


def recipe_for(correlation_key: str) -> EvidenceRecipe | None:
    """The declared recipe for a correlation key, or None.

    None is a legitimate answer, never an error: an incident opened under a key
    this build does not know (a newer rule file) is still diagnosed, with the
    runtime block alone.

    Args:
        correlation_key: The incident's correlation key.

    Returns:
        The recipe, or None when none is declared.
    """
    return EVIDENCE_RECIPES.get(correlation_key)


def _required_keys_from_checks() -> frozenset[str]:
    """Correlation keys the self-check registry can open incidents under."""
    from src.domains.diagnostics.checks import ALL_CHECKS

    return frozenset(check.alertname or check.check_id for check in ALL_CHECKS)


def assert_evidence_recipes_completeness(
    recipes: Mapping[str, EvidenceRecipe] | None = None,
    *,
    required_keys: frozenset[str] | None = None,
) -> None:
    """Refuse to boot with a recipe registry that would fetch the wrong thing.

    Args:
        recipes: Override for tests; defaults to the real registry.
        required_keys: Keys that MUST have a recipe; defaults to every key the
            check registry can open an incident under.

    Raises:
        AssertionError: A required key has no recipe, a key does not match its
            recipe, a recipe names an unknown catalogue query, or a recipe
            fetches nothing without a written reason.
    """
    from src.domains.diagnostics.query_catalogue import QUERY_CATALOGUE

    registry = recipes if recipes is not None else EVIDENCE_RECIPES
    required = required_keys if required_keys is not None else _required_keys_from_checks()

    missing = required - set(registry)
    assert not missing, f"no evidence recipe for correlation keys: {sorted(missing)}"
    for key, recipe in registry.items():
        assert key == recipe.correlation_key, (
            f"registry key '{key}' does not match recipe.correlation_key "
            f"'{recipe.correlation_key}'"
        )
        for query_id in recipe.prom_queries:
            assert query_id in QUERY_CATALOGUE, f"{key}: unknown catalogue query '{query_id}'"
        assert recipe.window_minutes >= 1, f"{key}: window_minutes must be positive"
        if not recipe.prom_queries and recipe.logs is None:
            assert recipe.reason_for_none, (
                f"{key}: the recipe fetches nothing and does not say why — a silent "
                "empty recipe is indistinguishable from a forgotten one"
            )
