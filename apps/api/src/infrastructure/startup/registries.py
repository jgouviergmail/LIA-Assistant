"""Startup steps: registries and fail-fast boot validations.

Groups the lifespan steps that guarantee every registry is complete and
populated before the first request: eager SQLAlchemy model imports, boot-time
completeness gates (ADR-085 family) and tool schema registration.

Extracted verbatim from ``src.main.lifespan`` (ADR-123): same structlog
events, same exception handling. The lifespan remains the single
orchestration point — these functions are only called from there.
"""

import structlog

from src.core.bootstrap import (
    register_tool_schemas,
    validate_llm_configuration,
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

    Validates, in order: LLM configuration completeness, ToolErrorCode enum
    completeness, Draft Display Registry exhaustivity (ADR-085), Draft
    Preview Renderer exhaustivity (ADR-085 pattern) and the evidence-driven
    expansion entity types (ADR-085 pattern).

    Raises:
        RuntimeError: If any validation fails (the app must not boot).
    """
    # Validate LLM configuration (fail-fast if config is incomplete)
    try:
        validate_llm_configuration()
    except ValueError as exc:
        logger.error("llm_configuration_invalid", error=str(exc), exc_info=True)
        raise RuntimeError(f"Invalid LLM configuration: {exc}") from exc

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


def init_tool_schemas() -> None:
    """Register tool schemas (Phase 2.1 - Issue #32).

    Must be called early to populate the schema registry before first request.

    Raises:
        RuntimeError: If tool schema registration fails.
    """
    try:
        register_tool_schemas()
    except RuntimeError as exc:
        logger.error("tool_schema_registration_failed", error=str(exc), exc_info=True)
        raise RuntimeError(f"Failed to register tool schemas: {exc}") from exc
