#!/usr/bin/env python
"""
Comprehensive Configuration Validator for LIA API.

Sprint 18.1 - Developer Experience Tooling
Created: 2025-12-18

Features:
- Validates .env against .env.example for missing/extra variables
- Type validation (boolean, int, float, JSON)
- Range validation (e.g., circuit_breaker_timeout_seconds: 10-600)
- Deprecated settings detection
- Service connectivity checks
- Pydantic config model validation

Usage:
    python scripts/validate_config.py
    python scripts/validate_config.py --verbose
    python scripts/validate_config.py --skip-services
    python scripts/validate_config.py --fix  # Generate missing vars template
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# Configure UTF-8 encoding for Windows console
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class Severity(Enum):
    """Validation issue severity levels."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class ValidationIssue:
    """A single validation issue."""

    severity: Severity
    category: str
    variable: str
    message: str
    suggestion: str | None = None


@dataclass
class ValidationResult:
    """Complete validation result."""

    issues: list[ValidationIssue] = field(default_factory=list)
    env_vars_loaded: int = 0
    env_vars_expected: int = 0

    @property
    def has_errors(self) -> bool:
        return any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == Severity.WARNING for i in self.issues)

    def add(
        self,
        severity: Severity,
        category: str,
        variable: str,
        message: str,
        suggestion: str | None = None,
    ) -> None:
        self.issues.append(ValidationIssue(severity, category, variable, message, suggestion))


# ============================================================================
# TYPE VALIDATORS
# ============================================================================


def is_bool(value: str) -> bool:
    """Check if value is a valid boolean."""
    return value.lower() in ("true", "false", "1", "0", "yes", "no")


def is_int(value: str) -> bool:
    """Check if value is a valid integer."""
    try:
        int(value)
        return True
    except ValueError:
        return False


def is_float(value: str) -> bool:
    """Check if value is a valid float."""
    try:
        float(value)
        return True
    except ValueError:
        return False


def is_json(value: str) -> bool:
    """Check if value is valid JSON."""
    if not value or value == "{}":
        return True
    try:
        json.loads(value)
        return True
    except json.JSONDecodeError:
        return False


def is_url(value: str) -> bool:
    """Check if value looks like a URL."""
    return value.startswith(("http://", "https://", "redis://", "postgresql"))


def is_provider(value: str) -> bool:
    """Check if value is a valid LLM provider."""
    return value.lower() in ("openai", "anthropic", "deepseek", "perplexity", "ollama", "google")


# ============================================================================
# CONFIGURATION RULES
# ============================================================================

# Variables that must be boolean
BOOL_VARS = {
    "DEBUG",
    "SESSION_COOKIE_SECURE",
    "SESSION_COOKIE_HTTPONLY",
    "LLM_CACHE_ENABLED",
    "TOOL_CONTEXT_ENABLED",
    "TOOL_APPROVAL_ENABLED",
    "SEMANTIC_VALIDATION_ENABLED",
    "RATE_LIMIT_ENABLED",
    "CIRCUIT_BREAKER_ENABLED",
    "GOOGLE_APIS_CIRCUIT_BREAKER_ENABLED",
    "OPENAI_CIRCUIT_BREAKER_ENABLED",
    "EXTERNAL_APIS_CIRCUIT_BREAKER_ENABLED",
    "ENABLE_TOKEN_FALLBACK",
    "ENABLE_HIERARCHICAL_PLANNER",
    "LANGFUSE_ENABLED",
    "LANGFUSE_DEBUG",
    "LANGCHAIN_CALLBACKS_BACKGROUND",
    "EVALUATOR_HALLUCINATION_REQUIRE_GROUND_TRUTH",
    "EVALUATOR_PIPELINE_SEND_TO_LANGFUSE",
    "ENABLE_SUMMARIZATION_MIDDLEWARE",
    "ENABLE_RETRY_MIDDLEWARE",
    "ENABLE_FALLBACK_MIDDLEWARE",
    "ENABLE_TOOL_RETRY_MIDDLEWARE",
    "ENABLE_CALL_LIMIT_MIDDLEWARE",
    "ENABLE_CONTEXT_EDITING_MIDDLEWARE",
}

# Variables that must be integers with optional ranges
INT_VARS = {
    "API_PORT": (1, 65535),
    "DATABASE_POOL_SIZE": (1, 100),
    "DATABASE_MAX_OVERFLOW": (0, 100),
    "REDIS_SESSION_DB": (0, 15),
    "REDIS_CACHE_DB": (0, 15),
    "API_MAX_ITEMS_PER_REQUEST": (1, 100),
    "AGENT_MAX_ITERATIONS": (1, 50),
    "MAX_MESSAGES_HISTORY": (1, 10000),
    "MAX_TOKENS_HISTORY": (1000, 100000000),
    "AGENT_HISTORY_KEEP_LAST": (1, 200),
    "MAX_CONTEXT_BATCH_SIZE": (1, 100),
    "MAX_AGENT_RESULTS": (1, 100),
    "DEFAULT_MESSAGE_WINDOW_SIZE": (1, 50),
    "ROUTER_MESSAGE_WINDOW_SIZE": (1, 50),
    "PLANNER_MESSAGE_WINDOW_SIZE": (1, 50),
    "RESPONSE_MESSAGE_WINDOW_SIZE": (1, 50),
    "TOOL_CONTEXT_MAX_ITEMS": (1, 100),
    "TOOL_CONTEXT_DETAILS_MAX_ITEMS": (1, 50),
    "TOOL_APPROVAL_CLEANUP_DAYS": (1, 30),
    "SSE_HEARTBEAT_INTERVAL": (1, 60),
    "LLM_CACHE_TTL_SECONDS": (10, 3600),
    "LLM_PRICING_CACHE_TTL_SECONDS": (60, 86400),
    "LANGFUSE_FLUSH_INTERVAL": (1, 900),  # Up to 15 minutes
    # Circuit Breaker
    "CIRCUIT_BREAKER_FAILURE_THRESHOLD": (1, 50),
    "CIRCUIT_BREAKER_SUCCESS_THRESHOLD": (1, 20),
    "CIRCUIT_BREAKER_TIMEOUT_SECONDS": (10, 600),
    "CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS": (1, 10),
    # Rate Limits
    "RATE_LIMIT_PER_MINUTE": (1, 1000),
    "RATE_LIMIT_BURST": (1, 100),
    "RATE_LIMIT_CONTACTS_SEARCH_CALLS": (1, 100),
    "RATE_LIMIT_CONTACTS_SEARCH_WINDOW": (1, 3600),
    "RATE_LIMIT_CONTACTS_LIST_CALLS": (1, 100),
    "RATE_LIMIT_CONTACTS_LIST_WINDOW": (1, 3600),
    "RATE_LIMIT_CONTACTS_DETAILS_CALLS": (1, 100),
    "RATE_LIMIT_CONTACTS_DETAILS_WINDOW": (1, 3600),
    # Planner
    "PLANNER_MAX_STEPS": (1, 50),
    "PLANNER_MAX_REPLANS": (1, 20),
    "PLANNER_TIMEOUT_SECONDS": (5, 120),
    # Token thresholds (flexible for different model context windows)
    "TOKEN_THRESHOLD_SAFE": (1000, 200000),
    "TOKEN_THRESHOLD_WARNING": (1000, 200000),
    "TOKEN_THRESHOLD_CRITICAL": (1000, 200000),
    "TOKEN_THRESHOLD_MAX": (1000, 200000),
    # HITL
    "HITL_PENDING_DATA_TTL_SECONDS": (60, 86400),
    # Middleware
    "RETRY_MAX_ATTEMPTS": (1, 10),
    "TOOL_RETRY_MAX_ATTEMPTS": (1, 10),
    "MODEL_CALL_THREAD_LIMIT": (10, 1000),
    "MODEL_CALL_RUN_LIMIT": (5, 100),
    "CONTEXT_EDIT_MAX_TOOL_RESULT_TOKENS": (100, 10000),
    "SUMMARIZATION_KEEP_MESSAGES": (3, 50),
    # Jinja
    "JINJA_MAX_RECURSION_DEPTH": (5, 50),
}

# Variables that must be floats with optional ranges
FLOAT_VARS = {
    "HTTP_TIMEOUT_OAUTH": (1.0, 60.0),
    "HTTP_TIMEOUT_TOKEN": (1.0, 60.0),
    "HTTP_TIMEOUT_EXTERNAL_API": (1.0, 60.0),
    "HTTP_TIMEOUT_CURRENCY_API": (1.0, 60.0),
    "SEMANTIC_VALIDATION_TIMEOUT_SECONDS": (0.5, 30.0),
    "SEMANTIC_VALIDATION_CONFIDENCE_THRESHOLD": (0.0, 1.0),
    "TOOL_CONTEXT_CONFIDENCE_THRESHOLD": (0.0, 1.0),
    "ROUTER_CONFIDENCE_THRESHOLD": (0.0, 1.0),
    "DOMAIN_FILTERING_CONFIDENCE_THRESHOLD": (0.0, 1.0),
    "HITL_CLASSIFIER_CONFIDENCE_THRESHOLD": (0.0, 1.0),
    "HITL_AMBIGUOUS_CONFIDENCE_THRESHOLD": (0.0, 1.0),
    "HITL_FUZZY_MATCH_AMBIGUITY_THRESHOLD": (0.0, 0.5),
    "HITL_LOW_CONFIDENCE_THRESHOLD": (0.0, 1.0),
    "PLANNER_MAX_COST_USD": (0.01, 100.0),
    "LANGFUSE_SAMPLE_RATE": (0.0, 1.0),
    "SUMMARIZATION_TRIGGER_FRACTION": (0.3, 0.95),
    "RETRY_BACKOFF_FACTOR": (1.0, 10.0),
    "TOOL_RETRY_BACKOFF_FACTOR": (1.0, 10.0),
    # LLM Temperature
    "ROUTER_LLM_TEMPERATURE": (0.0, 2.0),
    "PLANNER_LLM_TEMPERATURE": (0.0, 2.0),
    "RESPONSE_LLM_TEMPERATURE": (0.0, 2.0),
    "CONTACTS_AGENT_LLM_TEMPERATURE": (0.0, 2.0),
    "EMAILS_AGENT_LLM_TEMPERATURE": (0.0, 2.0),
    "CALENDAR_AGENT_LLM_TEMPERATURE": (0.0, 2.0),
    "DRIVE_AGENT_LLM_TEMPERATURE": (0.0, 2.0),
    "TASKS_AGENT_LLM_TEMPERATURE": (0.0, 2.0),
    "WEATHER_AGENT_LLM_TEMPERATURE": (0.0, 2.0),
    "WIKIPEDIA_AGENT_LLM_TEMPERATURE": (0.0, 2.0),
    "PERPLEXITY_AGENT_LLM_TEMPERATURE": (0.0, 2.0),
    "PLACES_AGENT_LLM_TEMPERATURE": (0.0, 2.0),
    "QUERY_AGENT_LLM_TEMPERATURE": (0.0, 2.0),
    "HITL_CLASSIFIER_LLM_TEMPERATURE": (0.0, 2.0),
    "HITL_QUESTION_GENERATOR_LLM_TEMPERATURE": (0.0, 2.0),
    "HITL_PLAN_APPROVAL_QUESTION_LLM_TEMPERATURE": (0.0, 2.0),
    "SEMANTIC_VALIDATOR_LLM_TEMPERATURE": (0.0, 2.0),
    # Evaluators
    "EVALUATOR_LLM_TEMPERATURE": (0.0, 2.0),
    "EVALUATOR_LATENCY_EXCELLENT_THRESHOLD_MS": (0.0, 10000.0),
    "EVALUATOR_LATENCY_GOOD_THRESHOLD_MS": (0.0, 10000.0),
    "EVALUATOR_LATENCY_ACCEPTABLE_THRESHOLD_MS": (0.0, 10000.0),
    "EVALUATOR_LATENCY_SLOW_THRESHOLD_MS": (0.0, 30000.0),
}

# Variables that must be valid JSON
JSON_VARS = {
    "ROUTER_LLM_PROVIDER_CONFIG",
    "PLANNER_LLM_PROVIDER_CONFIG",
    "RESPONSE_LLM_PROVIDER_CONFIG",
    "CONTACTS_AGENT_LLM_PROVIDER_CONFIG",
    "EMAILS_AGENT_LLM_PROVIDER_CONFIG",
    "CALENDAR_AGENT_LLM_PROVIDER_CONFIG",
    "DRIVE_AGENT_LLM_PROVIDER_CONFIG",
    "TASKS_AGENT_LLM_PROVIDER_CONFIG",
    "WEATHER_AGENT_LLM_PROVIDER_CONFIG",
    "WIKIPEDIA_AGENT_LLM_PROVIDER_CONFIG",
    "PERPLEXITY_AGENT_LLM_PROVIDER_CONFIG",
    "PLACES_AGENT_LLM_PROVIDER_CONFIG",
    "QUERY_AGENT_LLM_PROVIDER_CONFIG",
    "HITL_CLASSIFIER_LLM_PROVIDER_CONFIG",
    "HITL_QUESTION_GENERATOR_LLM_PROVIDER_CONFIG",
    "HITL_PLAN_APPROVAL_QUESTION_LLM_PROVIDER_CONFIG",
    "SEMANTIC_VALIDATOR_LLM_PROVIDER_CONFIG",
    "HIERARCHICAL_STAGE1_LLM_PROVIDER_CONFIG",
    "HIERARCHICAL_STAGE2_LLM_PROVIDER_CONFIG",
    "HIERARCHICAL_STAGE3_LLM_PROVIDER_CONFIG",
}

# Variables that must be valid LLM providers
PROVIDER_VARS = {
    "ROUTER_LLM_PROVIDER",
    "PLANNER_LLM_PROVIDER",
    "RESPONSE_LLM_PROVIDER",
    "CONTACTS_AGENT_LLM_PROVIDER",
    "EMAILS_AGENT_LLM_PROVIDER",
    "CALENDAR_AGENT_LLM_PROVIDER",
    "DRIVE_AGENT_LLM_PROVIDER",
    "TASKS_AGENT_LLM_PROVIDER",
    "WEATHER_AGENT_LLM_PROVIDER",
    "WIKIPEDIA_AGENT_LLM_PROVIDER",
    "PERPLEXITY_AGENT_LLM_PROVIDER",
    "PLACES_AGENT_LLM_PROVIDER",
    "QUERY_AGENT_LLM_PROVIDER",
    "HITL_CLASSIFIER_LLM_PROVIDER",
    "HITL_QUESTION_GENERATOR_LLM_PROVIDER",
    "HITL_PLAN_APPROVAL_QUESTION_LLM_PROVIDER",
    "SEMANTIC_VALIDATOR_LLM_PROVIDER",
    "HIERARCHICAL_STAGE1_LLM_PROVIDER",
    "HIERARCHICAL_STAGE2_LLM_PROVIDER",
    "HIERARCHICAL_STAGE3_LLM_PROVIDER",
}

# Deprecated variables (with migration path)
DEPRECATED_VARS = {
    "GOOGLE_PLACES_API_KEY": "Use GOOGLE_API_KEY instead (consolidated API key)",
    "JWT_SECRET_KEY": "Renamed to SECRET_KEY for clarity",
}

# Required variables (must be set and not placeholder)
REQUIRED_VARS = {
    "DATABASE_URL",
    "SECRET_KEY",
    "FERNET_KEY",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REDIRECT_URI",
    "OPENAI_API_KEY",
}

# Variables with CHANGE_ME placeholders that should be filled
PLACEHOLDER_PATTERN = re.compile(r"CHANGE_ME")

# Optional API keys (don't warn if missing)
OPTIONAL_API_KEYS = {
    "PERPLEXITY_API_KEY",
    "OPENWEATHERMAP_API_KEY",
    "GOOGLE_PLACES_API_KEY",  # Deprecated
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_GEMINI_API_KEY",
    "OPENAI_ORGANIZATION_ID",
    "ALERTMANAGER_SLACK_WEBHOOK_CRITICAL",
    "ALERTMANAGER_SLACK_WEBHOOK_WARNING",
    "ALERTMANAGER_SLACK_WEBHOOK_SECURITY",
    "ALERTMANAGER_PAGERDUTY_ROUTING_KEY",
}


# ============================================================================
# PARSING FUNCTIONS
# ============================================================================


def parse_env_example(env_example_path: Path) -> dict[str, str | None]:
    """
    Parse .env.example to extract all variable names and default values.

    Returns:
        Dict mapping variable names to their default values (None if no default)
    """
    variables: dict[str, str | None] = {}

    if not env_example_path.exists():
        return variables

    with open(env_example_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Parse VAR=value or VAR= (empty value)
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()

                # Skip commented-out variables
                if key.startswith("#"):
                    continue

                # Handle ${VAR} references - extract the base variable name
                value = value.strip()
                variables[key] = value if value else None

    return variables


def get_current_env() -> dict[str, str]:
    """Get all current environment variables."""
    return dict(os.environ)


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================


def validate_types(env: dict[str, str], result: ValidationResult) -> None:
    """Validate variable types (bool, int, float, JSON, provider)."""

    # Boolean validation
    for var in BOOL_VARS:
        if var in env and env[var]:
            if not is_bool(env[var]):
                result.add(
                    Severity.ERROR,
                    "Type",
                    var,
                    f"Expected boolean (true/false), got '{env[var]}'",
                    "Use 'true' or 'false' (case-insensitive)",
                )

    # Integer validation with ranges
    for var, range_tuple in INT_VARS.items():
        if var in env and env[var]:
            if not is_int(env[var]):
                result.add(
                    Severity.ERROR,
                    "Type",
                    var,
                    f"Expected integer, got '{env[var]}'",
                )
            elif range_tuple:
                min_val, max_val = range_tuple
                val = int(env[var])
                if val < min_val or val > max_val:
                    result.add(
                        Severity.WARNING,
                        "Range",
                        var,
                        f"Value {val} outside recommended range [{min_val}, {max_val}]",
                        f"Consider value between {min_val} and {max_val}",
                    )

    # Float validation with ranges
    for var, range_tuple in FLOAT_VARS.items():
        if var in env and env[var]:
            if not is_float(env[var]):
                result.add(
                    Severity.ERROR,
                    "Type",
                    var,
                    f"Expected float, got '{env[var]}'",
                )
            elif range_tuple:
                min_val, max_val = range_tuple
                val = float(env[var])
                if val < min_val or val > max_val:
                    result.add(
                        Severity.WARNING,
                        "Range",
                        var,
                        f"Value {val} outside recommended range [{min_val}, {max_val}]",
                        f"Consider value between {min_val} and {max_val}",
                    )

    # JSON validation
    for var in JSON_VARS:
        if var in env and env[var]:
            if not is_json(env[var]):
                result.add(
                    Severity.ERROR,
                    "Type",
                    var,
                    f"Expected valid JSON, got '{env[var]}'",
                    'Use valid JSON format, e.g., {} or {"key": "value"}',
                )

    # Provider validation
    for var in PROVIDER_VARS:
        if var in env and env[var]:
            if not is_provider(env[var]):
                result.add(
                    Severity.ERROR,
                    "Type",
                    var,
                    f"Invalid LLM provider '{env[var]}'",
                    "Use: openai, anthropic, deepseek, perplexity, ollama, or google",
                )


def validate_required(env: dict[str, str], result: ValidationResult) -> None:
    """Validate required variables are set and not placeholders."""

    for var in REQUIRED_VARS:
        if var not in env or not env[var]:
            result.add(
                Severity.ERROR,
                "Required",
                var,
                "Required variable is not set",
                f"Set {var} in your .env file",
            )
        elif PLACEHOLDER_PATTERN.search(env[var]):
            result.add(
                Severity.ERROR,
                "Placeholder",
                var,
                f"Variable still contains placeholder: '{env[var]}'",
                "Replace CHANGE_ME_* with actual value",
            )


def validate_deprecated(env: dict[str, str], result: ValidationResult) -> None:
    """Check for deprecated variables."""

    for var, migration in DEPRECATED_VARS.items():
        if var in env and env[var]:
            result.add(
                Severity.WARNING,
                "Deprecated",
                var,
                "Variable is deprecated",
                migration,
            )


def validate_missing_expected(
    env: dict[str, str],
    expected: dict[str, str | None],
    result: ValidationResult,
) -> None:
    """Check for variables in .env.example but missing in current env."""

    for var, default in expected.items():
        if var not in env:
            # Optional API keys - just info
            if var in OPTIONAL_API_KEYS:
                result.add(
                    Severity.INFO,
                    "Optional",
                    var,
                    "Optional API key not set (feature will be disabled)",
                )
            # Variables that have sensible defaults - just info
            elif default and not PLACEHOLDER_PATTERN.search(default):
                result.add(
                    Severity.INFO,
                    "Missing",
                    var,
                    (
                        f"Using default: {default[:50]}..."
                        if len(default) > 50
                        else f"Using default: {default}"
                    ),
                )
            else:
                result.add(
                    Severity.WARNING,
                    "Missing",
                    var,
                    "Variable from .env.example not set",
                    f"Consider adding {var} to your .env file",
                )


def validate_circuit_breaker(env: dict[str, str], result: ValidationResult) -> None:
    """Validate circuit breaker configuration consistency."""

    cb_enabled = env.get("CIRCUIT_BREAKER_ENABLED", "true").lower() == "true"

    if cb_enabled:
        # Check that thresholds make sense
        failure_threshold = int(env.get("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
        success_threshold = int(env.get("CIRCUIT_BREAKER_SUCCESS_THRESHOLD", "3"))
        timeout = int(env.get("CIRCUIT_BREAKER_TIMEOUT_SECONDS", "60"))
        half_open_max = int(env.get("CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS", "3"))

        if success_threshold > half_open_max:
            result.add(
                Severity.WARNING,
                "CircuitBreaker",
                "CIRCUIT_BREAKER_SUCCESS_THRESHOLD",
                f"Success threshold ({success_threshold}) > half-open max calls ({half_open_max})",
                "Circuit can never close from half-open state. "
                "Set SUCCESS_THRESHOLD <= HALF_OPEN_MAX_CALLS",
            )

        if timeout < 30 and failure_threshold < 3:
            result.add(
                Severity.WARNING,
                "CircuitBreaker",
                "CIRCUIT_BREAKER_TIMEOUT_SECONDS",
                "Very aggressive circuit breaker settings (fast open, fast retry)",
                "This may cause circuit to oscillate. Consider increasing timeout or threshold.",
            )


def validate_llm_config(env: dict[str, str], result: ValidationResult) -> None:
    """Validate LLM configuration consistency."""

    # Check that temperature is appropriate for deterministic tasks
    deterministic_agents = ["ROUTER", "PLANNER", "SEMANTIC_VALIDATOR"]
    for agent in deterministic_agents:
        temp_var = f"{agent}_LLM_TEMPERATURE"
        if temp_var in env:
            temp = float(env[temp_var])
            if temp > 0.5:
                result.add(
                    Severity.WARNING,
                    "LLM",
                    temp_var,
                    f"High temperature ({temp}) for {agent} (typically deterministic)",
                    f"Consider temperature <= 0.3 for {agent} tasks",
                )


def validate_security(env: dict[str, str], result: ValidationResult) -> None:
    """Validate security-related configuration."""

    # Check SECRET_KEY length
    secret_key = env.get("SECRET_KEY", "")
    if secret_key and len(secret_key) < 32:
        result.add(
            Severity.ERROR,
            "Security",
            "SECRET_KEY",
            f"SECRET_KEY too short ({len(secret_key)} chars, minimum 32)",
            "Generate with: openssl rand -base64 32",
        )

    # Check session cookie security in production
    environment = env.get("ENVIRONMENT", "development")
    if environment == "production":
        if env.get("SESSION_COOKIE_SECURE", "").lower() != "true":
            result.add(
                Severity.ERROR,
                "Security",
                "SESSION_COOKIE_SECURE",
                "SESSION_COOKIE_SECURE should be 'true' in production",
                "Set SESSION_COOKIE_SECURE=true for HTTPS",
            )

        if env.get("DEBUG", "").lower() == "true":
            result.add(
                Severity.WARNING,
                "Security",
                "DEBUG",
                "DEBUG=true in production environment",
                "Set DEBUG=false in production",
            )


# ============================================================================
# SERVICE CONNECTIVITY CHECKS
# ============================================================================


def check_database(env: dict[str, str]) -> tuple[bool, str]:
    """Check PostgreSQL connectivity."""
    try:
        import asyncio

        import asyncpg

        async def test_conn():
            db_url = env.get("DATABASE_URL")
            if not db_url:
                return False, "DATABASE_URL not set"

            # Convert SQLAlchemy-style URL to asyncpg format
            if db_url.startswith("postgresql+asyncpg://"):
                db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

            try:
                conn = await asyncpg.connect(db_url, timeout=5.0)
                await conn.close()
                return True, "Connected"
            except Exception as e:
                return False, str(e)

        return asyncio.run(test_conn())
    except ImportError:
        return True, "asyncpg not installed, skipping"
    except Exception as e:
        return False, str(e)


def check_redis(env: dict[str, str]) -> tuple[bool, str]:
    """Check Redis connectivity."""
    try:
        import redis

        redis_url = env.get("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(redis_url, socket_timeout=5.0)
        r.ping()
        return True, f"Connected ({redis_url})"
    except ImportError:
        return True, "redis package not installed, skipping"
    except Exception as e:
        return False, str(e)


# ============================================================================
# PYDANTIC MODEL VALIDATION
# ============================================================================


def validate_pydantic_models(result: ValidationResult) -> None:
    """Validate configuration against Pydantic models."""
    try:
        from src.core.config import settings

        # If we can import settings without error, basic validation passed
        result.add(
            Severity.INFO,
            "Pydantic",
            "settings",
            "Pydantic models loaded successfully",
        )
    except ModuleNotFoundError as e:
        # Running from script context without proper PYTHONPATH
        result.add(
            Severity.INFO,
            "Pydantic",
            "settings",
            f"Skipped Pydantic validation (module not in path): {e}",
        )
    except ImportError as e:
        # Missing dependency
        result.add(
            Severity.WARNING,
            "Pydantic",
            "settings",
            f"Pydantic validation skipped (import error): {e}",
            "Run 'pip install -r requirements.txt' to install dependencies",
        )
    except Exception as e:
        # Actual configuration error
        result.add(
            Severity.ERROR,
            "Pydantic",
            "settings",
            f"Pydantic settings validation failed: {e}",
            "Check src/core/config/ for configuration errors",
        )


# ============================================================================
# REPORT GENERATION
# ============================================================================


def print_report(result: ValidationResult, verbose: bool = False) -> None:
    """Print validation report to console."""

    print("=" * 70)
    print("Configuration Validation Report - LIA API")
    print("=" * 70)
    print()

    # Group issues by severity
    errors = [i for i in result.issues if i.severity == Severity.ERROR]
    warnings = [i for i in result.issues if i.severity == Severity.WARNING]
    infos = [i for i in result.issues if i.severity == Severity.INFO]

    # Summary
    print(f"Variables loaded: {result.env_vars_loaded}")
    print(f"Variables in .env.example: {result.env_vars_expected}")
    print()

    if errors:
        print(f"[ERRORS: {len(errors)}]")
        print("-" * 40)
        for issue in errors:
            print(f"  {issue.variable}")
            print(f"    {issue.message}")
            if issue.suggestion:
                print(f"    Suggestion: {issue.suggestion}")
        print()

    if warnings:
        print(f"[WARNINGS: {len(warnings)}]")
        print("-" * 40)
        for issue in warnings:
            print(f"  {issue.variable}")
            print(f"    {issue.message}")
            if issue.suggestion and verbose:
                print(f"    Suggestion: {issue.suggestion}")
        print()

    if verbose and infos:
        print(f"[INFO: {len(infos)}]")
        print("-" * 40)
        for issue in infos:
            print(f"  {issue.variable}: {issue.message}")
        print()

    # Final status
    print("=" * 70)
    if result.has_errors:
        print("VALIDATION FAILED - Fix errors before deployment")
        print("=" * 70)
    elif result.has_warnings:
        print("VALIDATION PASSED WITH WARNINGS - Review before production")
        print("=" * 70)
    else:
        print("VALIDATION PASSED - Configuration is valid")
        print("=" * 70)


def generate_fix_template(
    env: dict[str, str],
    expected: dict[str, str | None],
) -> str:
    """Generate template for missing variables."""

    missing = []
    for var in expected:
        if var not in env:
            default = expected[var]
            if default and PLACEHOLDER_PATTERN.search(default):
                missing.append(f"{var}={default}")
            elif default:
                missing.append(f"# {var}={default}  # Has default, optional")
            else:
                missing.append(f"{var}=")

    if not missing:
        return "# No missing variables - configuration is complete!"

    return (
        "# Missing variables from .env.example\n"
        "# Add these to your .env file:\n\n" + "\n".join(missing)
    )


# ============================================================================
# MAIN
# ============================================================================


def main() -> int:
    """Run configuration validation."""

    parser = argparse.ArgumentParser(description="Validate LIA API configuration")
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show all issues including INFO level",
    )
    parser.add_argument(
        "--skip-services",
        action="store_true",
        help="Skip service connectivity checks (database, redis)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Generate template for missing variables",
    )
    args = parser.parse_args()

    # Load .env if exists
    try:
        from dotenv import load_dotenv

        env_file = Path(__file__).parent.parent / ".env"
        if not env_file.exists():
            # Try root .env
            env_file = Path(__file__).parent.parent.parent.parent / ".env"

        if env_file.exists():
            load_dotenv(env_file)
            print(f"Loaded .env from {env_file}")
        else:
            print("No .env file found - using environment variables only")
    except ImportError:
        print("python-dotenv not installed, using environment variables only")

    # Get current environment
    env = get_current_env()

    # Parse .env.example
    env_example_path = Path(__file__).parent.parent.parent.parent / ".env.example"
    expected = parse_env_example(env_example_path)

    if args.fix:
        print("\n" + generate_fix_template(env, expected))
        return 0

    # Initialize result
    result = ValidationResult()
    result.env_vars_loaded = len(env)
    result.env_vars_expected = len(expected)

    # Run validations
    print("\nRunning validations...")

    validate_required(env, result)
    validate_types(env, result)
    validate_deprecated(env, result)
    validate_missing_expected(env, expected, result)
    validate_circuit_breaker(env, result)
    validate_llm_config(env, result)
    validate_security(env, result)
    validate_pydantic_models(result)

    # Service checks
    if not args.skip_services:
        print("\nChecking service connectivity...")

        ok, msg = check_database(env)
        if ok:
            result.add(Severity.INFO, "Service", "PostgreSQL", msg)
        else:
            result.add(Severity.ERROR, "Service", "PostgreSQL", f"Connection failed: {msg}")

        ok, msg = check_redis(env)
        if ok:
            result.add(Severity.INFO, "Service", "Redis", msg)
        else:
            result.add(Severity.WARNING, "Service", "Redis", f"Connection failed: {msg}")

    # Print report
    print()
    print_report(result, verbose=args.verbose)

    return 1 if result.has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
