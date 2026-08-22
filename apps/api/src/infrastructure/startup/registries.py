"""Startup steps: registries and fail-fast boot validations.

Groups the lifespan steps that guarantee every registry is complete and
populated before the first request: eager SQLAlchemy model imports and
boot-time completeness gates (ADR-085 family).

Extracted verbatim from ``src.main.lifespan`` (ADR-123): same structlog
events, same exception handling. The lifespan remains the single
orchestration point — these functions are only called from there.
"""

import structlog

from src.core.bootstrap import (
    validate_embedding_configuration,
    validate_llm_configuration,
    validate_provider_usage_capabilities,
    validate_tool_call_run_limits,
    validate_tool_error_codes,
)

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
