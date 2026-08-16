"""
Application bootstrap functions.

Provides testable initialization functions for:
- LLM configuration validation
- Rate limiter configuration
- Environment validation

These functions are extracted from main.py to enable:
1. Unit testing of startup logic
2. Consistent initialization across different entry points
3. Clear separation of concerns
"""

import structlog

from src.core.config import settings

logger = structlog.get_logger(__name__)


def validate_llm_configuration() -> None:
    """
    Validate that all required LLM configurations are present.

    Checks that LLM_DEFAULTS (code constants) covers critical pipeline types.
    Configuration is resolved from LLM_DEFAULTS + DB overrides (LLMConfigOverrideCache).

    This implements a fail-fast strategy: better to fail at startup with a clear
    error message than to fail during runtime with a cryptic error.

    Raises:
        ValueError: If any required LLM type is missing from LLM_DEFAULTS.
    """
    from src.domains.llm_config.constants import LLM_DEFAULTS

    # Critical LLM types that must have defaults defined
    required_llm_types = [
        "router",
        "response",
        "planner",
        "contacts_agent",
        "hitl_classifier",
        "hitl_question_generator",
    ]

    missing_types = [t for t in required_llm_types if t not in LLM_DEFAULTS]

    if missing_types:
        missing_str = ", ".join(missing_types)
        raise ValueError(
            f"Missing LLM_DEFAULTS entries for critical types: {missing_str}. "
            f"Add them to src/domains/llm_config/constants.py LLM_DEFAULTS."
        )

    # Log successful validation with effective models from LLM_DEFAULTS
    logger.info(
        "llm_configuration_validated",
        router_model=LLM_DEFAULTS["router"].model,
        response_model=LLM_DEFAULTS["response"].model,
        planner_model=LLM_DEFAULTS["planner"].model,
        contacts_agent_model=LLM_DEFAULTS["contacts_agent"].model,
        hitl_classifier_model=LLM_DEFAULTS["hitl_classifier"].model,
        hitl_question_generator_model=LLM_DEFAULTS["hitl_question_generator"].model,
        total_llm_types=len(LLM_DEFAULTS),
    )


def validate_llm_defaults_against_matrix() -> None:
    """Sanity check: every LLM_DEFAULTS entry must be compatible with its
    model's reasoning_widget on ``llm_models``. Fail-fast at boot if any
    drift exists (e.g. a future LLM_DEFAULTS edit that didn't keep the
    matrix in sync).

    Reuses the same ``validate_reasoning_effort`` function as the admin
    write path, so the parametrized matrix tests in
    ``test_reasoning_validation.py`` also cover the boot-time path.

    Raises:
        RuntimeError: When any LLM_DEFAULTS entry has a ``reasoning_effort``
        incompatible with its model's ``reasoning_widget`` /
        ``reasoning_enum_values`` / ``reasoning_budget_range``.

    Note:
        Must be called AFTER ``ModelCapabilitiesCache.load_from_db()`` so the
        cache is populated. Called from ``main.py`` lifespan startup.
    """
    from fastapi import HTTPException

    from src.domains.llm.models import LLMModelKindEnum
    from src.domains.llm_config.constants import LLM_DEFAULTS, LLM_TYPES_REGISTRY
    from src.domains.llm_config.reasoning_validation import (
        validate_reasoning_effort,
        validate_thinking_token_budget,
    )
    from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache

    if not ModelCapabilitiesCache.is_loaded():
        raise RuntimeError(
            "validate_llm_defaults_against_matrix() called before "
            "ModelCapabilitiesCache.load_from_db(). Fix the lifespan order in main.py."
        )

    errors: list[str] = []
    for llm_type, cfg in LLM_DEFAULTS.items():
        # Skip LLM types whose required_kind != "chat" (image_generation uses
        # image_generation_pricing, not llm_models). The reasoning matrix
        # check only applies to chat-kind LLM types.
        metadata = LLM_TYPES_REGISTRY.get(llm_type)
        if metadata is not None and metadata.required_kind != LLMModelKindEnum.chat:
            continue

        caps = ModelCapabilitiesCache.get(cfg.model)
        if caps is None:
            errors.append(
                f"  - {llm_type}: model {cfg.model!r} not present in llm_models catalogue"
            )
            continue
        try:
            validate_reasoning_effort(caps, cfg.reasoning_effort)
            # Thinking × completion-budget coherence: a default that enables
            # substantial reasoning must also carry a max_tokens that survives
            # it (same rule as the admin write path — prod 2026-07-29).
            validate_thinking_token_budget(
                llm_type=llm_type,
                effective=cfg,
                floor=settings.llm_thinking_max_tokens_floor,
            )
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, dict) else {"msg": str(e.detail)}
            errors.append(f"  - {llm_type} (model={cfg.model}): {detail.get('msg', detail)}")

    if errors:
        raise RuntimeError(
            "LLM_DEFAULTS contains entries incompatible with the model "
            "catalogue:\n" + "\n".join(errors) + "\n"
            "Update LLM_DEFAULTS in apps/api/src/domains/llm_config/constants.py "
            "to match the matrix in llm_pricing_seed.sql / llm_models."
        )

    logger.info(
        "llm_defaults_matrix_validated",
        total_types=len(LLM_DEFAULTS),
    )


def validate_critical_configuration() -> None:
    """
    Validate all critical environment variables before deployment.

    Extends LLM validation to include:
    - Database connection (PostgreSQL)
    - Redis connection
    - Security secrets
    - OAuth configuration

    Raises:
        ValueError: If any critical configuration is missing.
    """
    missing_configs = []

    # Database
    if not settings.database_url:
        missing_configs.append("DATABASE_URL")

    # Redis
    if not settings.redis_url:
        missing_configs.append("REDIS_URL")

    # Security
    if not settings.secret_key or settings.secret_key == "change-me-in-production":
        missing_configs.append("SECRET_KEY (must be set to a secure value)")

    if not settings.fernet_key:
        missing_configs.append("FERNET_KEY")

    # OAuth (required for Google integration if credentials are partially configured)
    has_google_client_id = bool(settings.google_client_id)
    has_google_client_secret = bool(settings.google_client_secret)

    # If one is set, both must be set
    if has_google_client_id != has_google_client_secret:
        if not has_google_client_id:
            missing_configs.append("GOOGLE_CLIENT_ID")
        if not has_google_client_secret:
            missing_configs.append("GOOGLE_CLIENT_SECRET")

    if missing_configs:
        missing_vars = ", ".join(missing_configs)
        raise ValueError(
            f"Missing critical configuration variables: {missing_vars}. "
            f"Please set these in your .env file. See .env.example for reference."
        )

    logger.info(
        "critical_configuration_validated",
        database_configured=bool(settings.database_url),
        redis_configured=bool(settings.redis_url),
        oauth_configured=bool(settings.google_client_id and settings.google_client_secret),
    )


def log_rate_limiting_status() -> None:
    """
    Log rate limiting configuration status.

    Logs whether rate limiting is enabled and the configured limits.
    """
    if settings.rate_limit_enabled:
        logger.info(
            "rate_limiting_enabled",
            default_limit=f"{settings.rate_limit_per_minute}/minute",
            burst=settings.rate_limit_burst,
        )
    else:
        logger.warning("rate_limiting_disabled")


def log_event_loop_configuration() -> None:
    """
    Log event loop configuration details.

    Important for Windows compatibility with psycopg v3 which requires
    SelectorEventLoop instead of ProactorEventLoop.
    """
    import asyncio
    import sys

    # Get event loop policy (always available)
    policy = asyncio.get_event_loop_policy()

    # Try to get current loop info, handle case where no loop is running
    try:
        loop = asyncio.get_running_loop()
        loop_type = type(loop).__name__
    except RuntimeError:
        # No running loop - this is expected during startup before async context
        loop_type = "NotRunning"

    logger.info(
        "event_loop_configured",
        platform=sys.platform,
        loop_type=loop_type,
        policy_type=type(policy).__name__,
        is_windows=sys.platform == "win32",
        psycopg_compatible=(
            "Selector" in loop_type
            if sys.platform == "win32" and loop_type != "NotRunning"
            else True
        ),
    )


def validate_provider_usage_capabilities() -> None:
    """Every chat provider must declare how its token usage is accounted.

    ADR-220 (ADR-085 doctrine): a provider able to serve a streamed slot
    without a ``PROVIDER_USAGE_CAPABILITIES`` entry is a silent accounting
    hole — the request would omit the usage ask and the ledger, the spend
    ceiling and the dashboards would depend on unrequested provider
    generosity. Refuse to boot instead.

    Raises:
        RuntimeError: If a chat provider is missing from the registry, if the
            registry names an unknown provider, or if a value is out of the
            bounded vocabulary.
    """
    from typing import get_args

    from src.domains.llm_config.constants import PROVIDER_USAGE_CAPABILITIES
    from src.infrastructure.llm.providers.adapter import ProviderType

    chat_providers = set(get_args(ProviderType))
    declared = set(PROVIDER_USAGE_CAPABILITIES)
    missing = sorted(chat_providers - declared)
    unknown = sorted(declared - chat_providers)
    if missing or unknown:
        raise RuntimeError(
            "PROVIDER_USAGE_CAPABILITIES drift: "
            f"missing={missing} unknown={unknown} — every chat provider must "
            "declare its usage accounting mode (ADR-220)."
        )
    allowed = {"stream_usage_flag", "native", "excluded"}
    invalid = {p: v for p, v in PROVIDER_USAGE_CAPABILITIES.items() if v not in allowed}
    if invalid:
        raise RuntimeError(f"PROVIDER_USAGE_CAPABILITIES holds out-of-vocabulary values: {invalid}")


def validate_tool_call_run_limits() -> None:
    """The paid-tool call ceilings must parse, or the app refuses to boot.

    ``tool_call_run_limits`` is a settings-driven string ("tool:limit,…"). A
    malformed value silently dropping a paid-tool ceiling would remove a cost
    protection without anyone noticing — same doctrine as
    :func:`validate_provider_usage_capabilities` (ADR-085: silent fallbacks on
    configuration are how protections die invisibly).

    Raises:
        RuntimeError: If the setting cannot be parsed.
    """
    from src.core.config import settings
    from src.infrastructure.llm.middleware_config import parse_tool_call_run_limits

    try:
        parse_tool_call_run_limits(settings.tool_call_run_limits)
    except ValueError as exc:
        raise RuntimeError(f"Invalid tool_call_run_limits setting: {exc}") from exc


def validate_tool_error_codes() -> None:
    """
    Validate that all ToolErrorCode values used in the codebase exist in the enum.

    This is a fail-fast check to catch missing enum values at startup rather than
    at runtime. The function verifies that commonly used error codes exist.

    Raises:
        RuntimeError: If any expected error code is missing from ToolErrorCode.

    Example:
        >>> validate_tool_error_codes()  # Should pass silently if all codes exist
    """
    from src.domains.agents.tools.common import ToolErrorCode

    # List of error codes that MUST exist (used in validator.py and other critical paths)
    required_codes = [
        "INVALID_INPUT",
        "MISSING_REQUIRED_PARAM",
        "INVALID_PARAM_VALUE",
        "CONSTRAINT_VIOLATION",
        "EXTERNAL_API_ERROR",
        "TIMEOUT",
        "RATE_LIMIT_EXCEEDED",
        "UNAUTHORIZED",
        "FORBIDDEN",
        "NOT_FOUND",
        "INTERNAL_ERROR",
        "CONFIGURATION_ERROR",
        "DEPENDENCY_ERROR",
        "EMPTY_RESULT",
        "INVALID_RESPONSE_FORMAT",
        "TEMPLATE_EMPTY_RESULT",
        "TEMPLATE_RECURSION_LIMIT",
        "NOT_IMPLEMENTED",  # Added for StepType.HUMAN/REPLAN validation
    ]

    missing_codes = []
    for code in required_codes:
        if not hasattr(ToolErrorCode, code):
            missing_codes.append(code)

    if missing_codes:
        missing_str = ", ".join(missing_codes)
        raise RuntimeError(
            f"Missing ToolErrorCode values: {missing_str}. "
            f"These codes are used in critical paths and must be defined in "
            f"src.domains.agents.tools.common.ToolErrorCode"
        )

    logger.info(
        "tool_error_codes_validated",
        total_codes=len(required_codes),
        all_present=True,
    )
