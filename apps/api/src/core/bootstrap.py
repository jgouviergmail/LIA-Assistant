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


def register_tool_schemas() -> None:
    """
    Register all tool response schemas at application startup.

    Phase 2.1 - Schema Mismatch Resolution (Issue #32)

    This function populates the Tool Schema Registry with schemas for all tools
    in the system. Schemas are extracted automatically from formatter classes
    and registered with helpful reference examples.

    Purpose:
        - Enable dynamic schema injection into planner prompts
        - Enable pre-execution validation of step references
        - Provide single source of truth for tool response structures

    Architecture:
        - Extracts schemas from formatter FIELD_EXTRACTORS
        - Registers schemas in thread-safe singleton registry
        - Creates reference examples for planner documentation

    Timing:
        Called at application startup, after UTF-8 patch but before
        first request. Schemas are registered once and reused throughout
        application lifecycle.

    Observability:
        Logs registration progress and statistics.
        Check logs for:
        - schema_registration_start
        - schema_extracted (per tool)
        - schema_registered (per tool)
        - schema_registration_complete

    Examples:
        >>> # In main.py or startup event
        >>> register_tool_schemas()
        >>> # Now all tools have schemas registered
        >>>
        >>> # Verify registration
        >>> from src.domains.agents.tools.schema_registry import ToolSchemaRegistry
        >>> registry = ToolSchemaRegistry.get_instance()
        >>> assert len(registry.list_tools()) >= 3
        >>> assert registry.has_schema("search_contacts_tool")

    Best Practices (2025):
        - Fail-fast: Errors during registration will prevent startup
        - Structured logging: All registration events logged
        - Defensive: Handles missing formatters gracefully
    """
    from src.domains.agents.tools.schema_registration import register_all_tool_schemas

    try:
        logger.info(
            "tool_schema_registration_start",
            message="Starting tool schema registration at application startup",
        )

        # Register all tool schemas
        register_all_tool_schemas()

        # Get statistics for logging
        from src.domains.agents.tools.schema_registry import ToolSchemaRegistry

        registry = ToolSchemaRegistry.get_instance()
        stats = registry.get_stats()

        logger.info(
            "tool_schema_registration_complete",
            total_tools=stats["total_tools"],
            tools_with_examples=stats["tools_with_examples"],
            total_examples=stats["total_examples"],
            tools=registry.list_tools(),
            message=f"Successfully registered {stats['total_tools']} tool schemas",
        )

    except Exception as e:
        # Fail-fast: Schema registration errors prevent startup
        # This ensures we never run with incomplete schema registry
        logger.error(
            "tool_schema_registration_failed",
            error=str(e),
            error_type=type(e).__name__,
            message="Failed to register tool schemas at startup",
            exc_info=True,
        )
        raise RuntimeError(
            f"Tool schema registration failed: {e}. "
            f"Cannot start application without complete schema registry."
        ) from e


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
