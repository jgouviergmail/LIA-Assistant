"""Startup steps: registries and fail-fast boot validations.

Groups the lifespan steps that guarantee every registry is complete and
populated before the first request: eager SQLAlchemy model imports and
boot-time completeness gates (ADR-085 family).

Extracted verbatim from ``src.main.lifespan`` (ADR-123): same structlog
events, same exception handling. The lifespan remains the single
orchestration point — these functions are only called from there.
"""

from typing import get_args

import structlog

from src.core.bootstrap import (
    validate_embedding_configuration,
    validate_llm_configuration,
    validate_provider_usage_capabilities,
    validate_tool_call_run_limits,
    validate_tool_error_codes,
)
from src.core.config import settings

logger = structlog.get_logger(__name__)


def import_domain_models() -> None:
    """Eagerly import all domain models so SQLAlchemy mappers are fully configured.

    Must run before any query. Required for models referenced via string in
    relationships (e.g., ``User.skill_states`` → ``UserSkillState``,
    ``User.usage_limit`` → ``UserUsageLimit``).
    """
    import src.domains.skills.models  # noqa: F401
    from src.infrastructure.database.registry import import_all_models

    import_all_models()


def _validate_memory_category_vocabulary() -> None:
    """Boot gate of the memory-category vocabulary (ADR-085 pattern).

    ``MemoryCategory`` is what the column stores; three surfaces restate it —
    two typing faces, because MyPy needs literal values, and the catalogue the
    settings screen reads. A drift is silent in every direction: it dropped
    every ``procedural`` memory the extraction prompt asked for, kept the
    category out of the published catalogue, and one stored row would have
    failed the list endpoint's response model (measured 2026-08-28).

    Raises:
        RuntimeError: If any surface disagrees with the enum.
    """
    try:
        from src.domains.agents.tools.memory_tools import (
            MemoryCategoryType as _ToolCategoryType,
        )
        from src.domains.agents.tools.memory_tools import get_memory_categories
        from src.domains.memories.schemas import (
            assert_category_vocabulary_completeness,
        )

        assert_category_vocabulary_completeness(surface="the schemas Literal")
        assert_category_vocabulary_completeness(
            get_args(_ToolCategoryType), surface="the tools Literal"
        )
        assert_category_vocabulary_completeness(
            tuple(entry["name"] for entry in get_memory_categories()),
            surface="the published catalogue",
        )
    except AssertionError as exc:
        logger.error("memory_category_vocabulary_drift", error=str(exc), exc_info=True)
        raise RuntimeError(f"Memory category vocabulary drift: {exc}") from exc


def _validate_redis_key_families() -> None:
    """Boot gate of the Redis key-family registry (ADR-260).

    A key family without a declared scope is one the conversation reset can
    neither purge nor protect knowingly. The registry refuses to boot when a
    ``core.constants`` prefix names a family it does not know.

    Raises:
        RuntimeError: If any prefix constant is undeclared.
    """
    from src.infrastructure.cache.key_families import assert_key_families_complete

    try:
        assert_key_families_complete()
    except RuntimeError as exc:
        logger.error("redis_key_family_registry_drift", error=str(exc), exc_info=True)
        raise


def _install_proactive_notifier() -> None:
    """Wire the notification dispatcher into its seam, and prove it (ADR-276).

    Same inversion and same lesson as the consultation register: a feature
    domain must not import the dispatcher (``agents`` imports ``workboard``,
    the dispatcher imports ``agents``), so the adapter installs itself as an
    IMPORT SIDE EFFECT — and an import nobody declares is an import that can
    stop happening when somebody reorders a module.

    ADR-270 measured what that costs on the consultation seam: it answered a
    no-op, in silence, along the exact path a sweep used. Here the cost would
    be a person never told that a ticket was handed to them, with nothing
    anywhere saying so.

    Raises:
        RuntimeError: If the dispatcher did not claim the seam.
    """
    # The adapter also installs itself at import, for every path that does not
    # go through the boot. Here the step INSTALLS: an import runs its side effect
    # once per process, so a module already imported wires nothing and the check
    # below would refuse a seam that was never claimed rather than claiming it
    # (measured 2026-09-10 — a boot guard raising in a worker where the adapter
    # was merely already loaded).
    from src.domains.shared.proactive_sink import (
        install_proactive_notifier,
        notifier_is_installed,
    )
    from src.infrastructure.proactive.notification_sink import (
        dispatch_proactive_notification,
    )

    install_proactive_notifier(dispatch_proactive_notification)

    if not notifier_is_installed():
        raise RuntimeError(
            "the notification dispatcher did not claim its seam: every "
            "domain-initiated notification would be dropped silently"
        )


def _install_ticket_releaser() -> None:
    """Wire the board into the peer-release seam, and prove it (ADR-276 lot 5).

    Same inversion and same lesson as the two seams beside it: ``workboard``
    imports ``peers`` (the service re-checks the connection at every write), so
    ``peers`` cannot import the board back. The adapter installs itself as an
    IMPORT SIDE EFFECT — and an import nobody declares is one that can stop
    happening when somebody reorders a module.

    ADR-270 measured what that costs: a no-op answering in silence along the
    exact path a sweep used. Here the cost would be a ticket left assigned to
    somebody who no longer has any access to the board it lives on.

    Raises:
        RuntimeError: If the board did not claim the seam.
    """
    # The adapter also installs itself at import, for every path that does not
    # go through the boot. Here the step INSTALLS: an import runs its side effect
    # once per process, so a module already imported wires nothing and the check
    # below would refuse a seam that was never claimed rather than claiming it
    # (measured 2026-09-10 — a boot guard raising in a worker where the adapter
    # was merely already loaded).
    from src.domains.shared.peer_release_sink import (
        install_ticket_releaser,
        releaser_is_installed,
    )
    from src.domains.workboard.release_adapter import release_tickets_between

    install_ticket_releaser(release_tickets_between)

    if not releaser_is_installed():
        raise RuntimeError(
            "the workboard did not claim the peer-release seam: a removed "
            "connection would leave its tickets assigned to somebody who can "
            "no longer reach them"
        )


def _install_consultation_sink() -> None:
    """Wire the consultation register into its seam, and prove it (ADR-270).

    The seam (``domains/shared/consultation_sink``) inverts the dependency so a
    feature domain never imports the register — but the register installs
    itself as an IMPORT SIDE EFFECT, and nothing guaranteed that import ever
    happened. Measured on dev 2026-09-07: along the exact import path the
    heartbeat sweep uses — the proactive runner, then
    ``heartbeat.consultations`` — ``sink_is_installed()`` answered **False**.
    The register worked in production only because the API happens to import
    the treatments router at boot; reorder that and every out-of-turn
    consultation is dropped by a no-op, in silence and with no signal at all.

    So the wiring is a DECLARED step, and the boot refuses a mute register.
    That is ADR-085's rule applied to a seam rather than a table: an
    observability subsystem that fails open is the one failure nobody notices.

    Raises:
        RuntimeError: If the register did not claim the seam.
    """
    # The adapter also installs itself at import, for every path that does not
    # go through the boot. Here the step INSTALLS: an import runs its side effect
    # once per process, so a module already imported wires nothing and the check
    # below would refuse a seam that was never claimed rather than claiming it
    # (measured 2026-09-10 — a boot guard raising in a worker where the adapter
    # was merely already loaded).
    from src.domains.agents.effects.treatment_recorder import treatment_recorder
    from src.domains.agents.effects.treatments import (
        record_out_of_turn_consultation,
    )
    from src.domains.shared.consultation_sink import (
        install_collector_factory,
        install_consultation_sink,
        sink_is_installed,
    )

    install_consultation_sink(record_out_of_turn_consultation)
    install_collector_factory(treatment_recorder)

    if not sink_is_installed():
        raise RuntimeError(
            "the consultation register did not claim its seam: every "
            "out-of-turn consultation would be dropped silently"
        )


def _validate_diagnostics_registries() -> None:
    """Boot gates of the diagnostics subsystem (ADR-085 pattern).

    The named-query catalogue is the ONLY producer of PromQL, so an undeclared
    placeholder or metric must refuse to boot rather than fail at query time;
    a check whose threshold field does not exist on Settings would silently
    compare against nothing.

    Raises:
        RuntimeError: If either registry is structurally broken.
    """
    try:
        from src.domains.diagnostics.query_catalogue import (
            assert_query_catalogue_completeness,
        )

        assert_query_catalogue_completeness()
    except AssertionError as exc:
        logger.error("diagnostics_query_catalogue_incomplete", error=str(exc), exc_info=True)
        raise RuntimeError(f"Diagnostics query catalogue incomplete: {exc}") from exc

    try:
        from src.domains.diagnostics.checks import assert_check_registry_completeness
        from src.domains.diagnostics.engine import assert_probe_coverage
        from src.domains.diagnostics.evidence_recipes import (
            assert_evidence_recipes_completeness,
        )

        assert_check_registry_completeness()
        assert_probe_coverage()
        # ADR-266: every incident a check can open has a declared evidence
        # recipe, and a recipe names only queries the catalogue serves.
        assert_evidence_recipes_completeness()
    except AssertionError as exc:
        logger.error("diagnostics_check_registry_incomplete", error=str(exc), exc_info=True)
        raise RuntimeError(f"Diagnostics check registry incomplete: {exc}") from exc

    # A WARNING, never a refusal: a diagnosis without its runbook is weaker, not
    # wrong, and a self-hoster must not be locked out for a missing mount.
    # Production ran for weeks with the mount point present and EMPTY (the
    # bundle never staged docs/runbooks) and nothing said so — every stored
    # diagnosis carried had_runbook=false (measured 2026-09-05).
    if getattr(settings, "diagnostics_enabled", False):
        from src.domains.diagnostics.diagnosis import count_runbooks

        if count_runbooks() == 0:
            logger.warning(
                "diagnostics_runbooks_missing",
                path=settings.diagnostics_runbooks_dir,
            )


def run_failfast_validations() -> None:
    """Run the fail-fast boot validations (die at boot, not at first request).

    Validates, in order: LLM configuration completeness, the provider
    usage-accounting registry (ADR-220), the paid-tool call ceilings, the
    embedding configuration (ADR-242), ToolErrorCode enum
    completeness, Draft Display Registry exhaustivity (ADR-085), Draft
    Preview Renderer exhaustivity (ADR-085 pattern), the evidence-driven
    expansion entity types (ADR-085 pattern), the HITL classifier few-shot
    coverage (ADR-085 pattern), the registry content-trust classification
    (ADR-085 pattern) and the PostgreSQL connection budget (F004).

    Raises:
        RuntimeError: If any validation fails (the app must not boot).
    """
    # Validate LLM configuration (fail-fast if config is incomplete)
    try:
        validate_llm_configuration()
    except ValueError as exc:
        logger.error("llm_configuration_invalid", error=str(exc), exc_info=True)
        raise RuntimeError(f"Invalid LLM configuration: {exc}") from exc

    # Validate the provider usage-accounting registry (ADR-220 / ADR-085: a
    # chat provider without a declared accounting mode is a silent hole in the
    # token ledger and the spend ceiling — refuse to boot).
    try:
        validate_provider_usage_capabilities()
    except RuntimeError as exc:
        logger.error("provider_usage_capabilities_invalid", error=str(exc), exc_info=True)
        raise

    # Validate the paid-tool call ceilings (same ADR-085 doctrine: a malformed
    # value silently dropping a cost protection must refuse to boot).
    try:
        validate_tool_call_run_limits()
    except RuntimeError as exc:
        logger.error("tool_call_run_limits_invalid", error=str(exc), exc_info=True)
        raise

    # Validate the embedding configuration (ADR-242 / ADR-085): a dimensionality
    # the pgvector column cannot hold makes every write fail at runtime, and an
    # undeclared model means nobody checked whether it honours task_type — the
    # property every retrieval threshold is calibrated on.
    try:
        validate_embedding_configuration()
    except RuntimeError as exc:
        logger.error("embedding_configuration_invalid", error=str(exc), exc_info=True)
        raise

    # Validate ToolErrorCode enum completeness (fail-fast if codes are missing)
    try:
        validate_tool_error_codes()
    except RuntimeError as exc:
        logger.error("tool_error_codes_invalid", error=str(exc), exc_info=True)
        raise

    # Validate Draft Display Registry exhaustivity (ADR-085: fail-fast if a
    # DraftType has been added without registering its display configuration).
    try:
        from src.domains.agents.drafts.display import assert_registry_completeness

        assert_registry_completeness()
    except AssertionError as exc:
        logger.error("draft_display_registry_incomplete", error=str(exc), exc_info=True)
        raise RuntimeError(f"Draft display registry incomplete: {exc}") from exc

    # Validate Draft Preview Renderer exhaustivity (ADR-085 pattern: fail-fast
    # if a DraftType has been added without registering its detailed-preview
    # renderer in the dispatch table).
    try:
        from src.domains.agents.drafts.preview_renderer import (
            assert_preview_renderer_completeness,
        )

        assert_preview_renderer_completeness()
    except AssertionError as exc:
        logger.error("draft_preview_renderer_incomplete", error=str(exc), exc_info=True)
        raise RuntimeError(f"Draft preview renderer registry incomplete: {exc}") from exc

    # Validate Draft Summary Renderer exhaustivity (ADR-085 pattern: the
    # cascade this replaced fell back to « Draft (tool_call) » for 9 of the 26
    # types, in English, in every language — an omission nothing could detect).
    try:
        from src.domains.agents.drafts.summary_renderer import (
            assert_summary_renderer_completeness,
        )

        assert_summary_renderer_completeness()
    except AssertionError as exc:
        logger.error("draft_summary_renderer_incomplete", error=str(exc), exc_info=True)
        raise RuntimeError(f"Draft summary renderer registry incomplete: {exc}") from exc

    # Validate evidence-driven expansion entity types (ADR-085 pattern:
    # fail-fast if an evidence domain maps to an ontology type without the
    # properties/source_domains that expansion relies on).
    try:
        from src.domains.agents.semantic.expansion_service import (
            assert_evidence_entity_types_complete,
        )

        assert_evidence_entity_types_complete()
    except RuntimeError as exc:
        logger.error("evidence_entity_registry_incomplete", error=str(exc), exc_info=True)
        raise

    # Validate HITL classifier few-shot coverage (ADR-085 pattern: fail-fast if
    # an action type can be announced to the classifier without an example block
    # behind it — it would silently degrade to the generic one).
    try:
        from src.domains.agents.services.hitl_classifier import (
            assert_classifier_examples_coverage,
        )

        assert_classifier_examples_coverage()
    except AssertionError as exc:
        logger.error("hitl_classifier_examples_incomplete", error=str(exc), exc_info=True)
        raise RuntimeError(f"HITL classifier examples incomplete: {exc}") from exc

    # Validate semantic-issue clarification questions (ADR-085 pattern: fail-fast
    # if a SemanticIssueType can be raised without a localized question behind
    # it — the safety-net clarification would degrade to a generic prompt, or
    # worse, to the issue's English technical description as it did in prod
    # 2026-08-02).
    try:
        from src.core.i18n_hitl import HitlMessages

        HitlMessages.assert_semantic_issue_questions_coverage()
    except AssertionError as exc:
        logger.error("semantic_issue_questions_incomplete", error=str(exc), exc_info=True)
        raise RuntimeError(f"Semantic issue clarification questions incomplete: {exc}") from exc

    # Validate registry content-trust classification (ADR-085 pattern: fail-fast
    # if a RegistryItemType has been added without declaring whether its payload
    # can carry third-party free text — it would reach the LLM unmarked).
    try:
        from src.domains.agents.data_registry.trust import (
            assert_trust_registry_completeness,
        )

        assert_trust_registry_completeness()
    except AssertionError as exc:
        logger.error("registry_trust_classification_incomplete", error=str(exc), exc_info=True)
        raise RuntimeError(f"Registry trust classification incomplete: {exc}") from exc

    # Validate the plural key every registry type is filed under (ADR-085
    # pattern: the readers fall back to `value.lower() + "s"`, which produced a
    # key contradicting the domain taxonomy and made a step output invisible).
    try:
        from src.domains.agents.tools.output import assert_registry_key_completeness

        assert_registry_key_completeness()
    except AssertionError as exc:
        logger.error("registry_result_key_incomplete", error=str(exc), exc_info=True)
        raise RuntimeError(f"Registry result key mapping incomplete: {exc}") from exc

    # Validate the system-settings registry (ADR-085 pattern: fail-fast if a
    # SystemSettingKey has been added without declaring its codec, default and
    # cache — reading it would silently return a hardcoded fallback nobody
    # can administer).
    try:
        # Importing the capability registry declares its settings specs (one
        # per switchable capability). It must happen BEFORE the assert below,
        # which is exactly what makes a missing declaration a boot failure
        # instead of a silent fallback.
        import src.domains.feature_switches.registry  # noqa: F401
        from src.domains.system_settings.registry import assert_registry_completeness

        assert_registry_completeness()
    except RuntimeError as exc:
        logger.error("system_settings_registry_incomplete", error=str(exc), exc_info=True)
        raise

    # Validate the memory-category vocabulary and the diagnostics registries
    # (ADR-085 pattern, both structural and I/O-free, so they run regardless of
    # any feature flag).
    _validate_memory_category_vocabulary()
    _validate_diagnostics_registries()
    _validate_redis_key_families()
    _install_consultation_sink()
    _install_proactive_notifier()
    _install_ticket_releaser()

    # Enforce the PostgreSQL connection budget (F004): fail-fast in production,
    # warn in development. The shipped prod profile fits (168 ≤ 195 usable), so an
    # overcommit in production is a genuinely mis-sized deployment — booting it
    # would intermittently exhaust the server, so we refuse to start instead.
    from src.core.config import settings
    from src.infrastructure.database.connection_budget import enforce_connection_budget

    for warning in enforce_connection_budget(settings):
        logger.warning("db_connection_budget_overcommit", detail=warning)


def init_response_feedback_hooks() -> None:
    """Wire the journals implementation into the response-feedback port (QW-5).

    Conversations must not import journals (domain-cycle ratchet, F009) — this
    startup step is the composition point allowed to see both domains. Runs
    unconditionally: the ``journals_enabled`` flag is checked at call time.
    """
    from src.domains.conversations.response_feedback import register_journal_feedback_hooks
    from src.domains.journals.feedback_hooks import JournalResponseFeedbackHooks

    register_journal_feedback_hooks(JournalResponseFeedbackHooks())
