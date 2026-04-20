"""
Centralized field names for database models, API responses, and state management.

This module provides constants for commonly used field names to:
- Prevent typos (IDE autocomplete)
- Enable easy refactoring (rename globally)
- Provide centralized documentation

Usage:
    from core.field_names import FIELD_USER_ID, FIELD_STATUS

    query = {"user_id": FIELD_USER_ID}  # Old
    query = {FIELD_USER_ID: user_value}  # New (typo-safe)

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-15
"""

# ============================================================
# DATABASE / MODEL FIELD NAMES
# ============================================================

# Identity & Authentication
FIELD_USER_ID = "user_id"
FIELD_SESSION_ID = "session_id"
FIELD_THREAD_ID = "thread_id"
FIELD_CONVERSATION_ID = "conversation_id"

# Agents & LangGraph
FIELD_RUN_ID = "run_id"
FIELD_TURN_ID = "turn_id"
FIELD_STEP_ID = "step_id"
FIELD_WAVE_ID = "wave_id"
FIELD_PLAN_ID = "plan_id"
FIELD_AGENT_NAME = "agent_name"
FIELD_AGENT_TYPE = "agent_type"
FIELD_NODE_NAME = "node_name"
FIELD_TOOL_NAME = "tool_name"

# LLM & Tokens
FIELD_TOKENS_IN = "tokens_in"
FIELD_TOKENS_OUT = "tokens_out"
FIELD_TOKENS_CACHE = "tokens_cache"
FIELD_COST_EUR = "cost_eur"
FIELD_MODEL_NAME = "model_name"

# Status & State
FIELD_STATUS = "status"
FIELD_ROLE = "role"
FIELD_ERROR_CODE = "error_code"
FIELD_ERROR_MESSAGE = "error_message"
FIELD_ERROR_TYPE = "error_type"
FIELD_IS_ACTIVE = "is_active"

# Content & Data
FIELD_CONTENT = "content"
FIELD_QUERY = "query"
FIELD_OUTPUT = "output"
FIELD_RESOURCE_NAME = "resource_name"
FIELD_INDEX = "index"  # Item index in lists (1-based)
FIELD_METADATA = "metadata"  # Metadata dictionaries (LangChain, LangGraph, custom)
FIELD_PARAMETERS = "parameters"  # Tool/function parameters
FIELD_RESULT = "result"  # Tool/agent result data

# Connectors & OAuth
FIELD_CONNECTOR = "connector"
FIELD_CONNECTOR_TYPE = "connector_type"

# Timestamps
FIELD_CREATED_AT = "created_at"
FIELD_CACHED_AT = "cached_at"
FIELD_TIMESTAMP = "timestamp"

# Counts & Totals
FIELD_TOTAL = "total"
FIELD_TOTAL_COUNT = "total_count"
FIELD_MESSAGE_COUNT = "message_count"

# Token Aggregation (conversation totals)
FIELD_TOTAL_TOKENS_IN = "total_tokens_in"
FIELD_TOTAL_TOKENS_OUT = "total_tokens_out"
FIELD_TOTAL_TOKENS_CACHE = "total_tokens_cache"
FIELD_TOTAL_COST_EUR = "total_cost_eur"

# Google API Tracking (Maps Platform)
FIELD_GOOGLE_API_REQUESTS = "google_api_requests"
FIELD_GOOGLE_API_COST_EUR = "google_api_cost_eur"
FIELD_GOOGLE_API_COST_USD = "google_api_cost_usd"

# Google API Aggregation (user statistics)
FIELD_TOTAL_GOOGLE_API_REQUESTS = "total_google_api_requests"
FIELD_TOTAL_GOOGLE_API_COST_EUR = "total_google_api_cost_eur"

# Google API Billing Cycle
FIELD_CYCLE_GOOGLE_API_REQUESTS = "cycle_google_api_requests"
FIELD_CYCLE_GOOGLE_API_COST_EUR = "cycle_google_api_cost_eur"

# HITL (Human-in-the-Loop)
FIELD_ACTION_REQUESTS = "action_requests"
FIELD_DECISION = "decision"
FIELD_INTERRUPT_DATA = "interrupt_data"
FIELD_TYPE = "type"  # Generic type field (HITL action type, etc.)
FIELD_DRAFT_ID = "draft_id"  # Draft identifier for draft_critique HITL

# Proactive Messages Metadata (interest/heartbeat notifications archived in
# conversation_messages.message_metadata JSONB)
FIELD_TARGET_ID = "target_id"  # Reference to the source entity (interest_id, heartbeat_id, ...)
FIELD_FEEDBACK_ENABLED = "feedback_enabled"  # Whether feedback buttons should be shown
FIELD_FEEDBACK_SUBMITTED = "feedback_submitted"  # Persisted after user submits feedback
FIELD_FEEDBACK_VALUE = "feedback_value"  # Feedback kind (thumbs_up/thumbs_down/block)

# Data Registry & Correlation (Correlated Display)
FIELD_REGISTRY_ID = "_registry_id"  # Internal registry item ID (enriched in structured_data)
FIELD_CORRELATION_PARENT_ID = "_correlation_parent_id"  # System param for FOR_EACH correlation
FIELD_CORRELATED_TO = "correlated_to"  # RegistryItemMeta field linking child to parent

# ============================================================
# USAGE LIMITS (per-user quotas)
# ============================================================
FIELD_TOKEN_LIMIT_PER_CYCLE = "token_limit_per_cycle"
FIELD_MESSAGE_LIMIT_PER_CYCLE = "message_limit_per_cycle"
FIELD_COST_LIMIT_PER_CYCLE = "cost_limit_per_cycle"
FIELD_TOKEN_LIMIT_ABSOLUTE = "token_limit_absolute"
FIELD_MESSAGE_LIMIT_ABSOLUTE = "message_limit_absolute"
FIELD_COST_LIMIT_ABSOLUTE = "cost_limit_absolute"
FIELD_IS_USAGE_BLOCKED = "is_usage_blocked"
FIELD_BLOCKED_REASON = "blocked_reason"
FIELD_USAGE_LIMIT_STATUS = "usage_limit_status"

# ============================================================
# IMAGE GENERATION (cost tracking)
# ============================================================
FIELD_IMAGE_GENERATION_REQUESTS = "image_generation_requests"
FIELD_IMAGE_GENERATION_COST_EUR = "image_generation_cost_eur"

# ============================================================
# FIELD GROUPS (for validation, serialization)
# ============================================================

# Identity fields (PII - sensitive data)
IDENTITY_FIELDS = frozenset(
    [
        FIELD_USER_ID,
        FIELD_SESSION_ID,
        FIELD_CONVERSATION_ID,
    ]
)

# LangGraph state fields
LANGGRAPH_STATE_FIELDS = frozenset(
    [
        FIELD_RUN_ID,
        FIELD_TURN_ID,
        FIELD_STEP_ID,
        FIELD_WAVE_ID,
        FIELD_PLAN_ID,
        FIELD_AGENT_NAME,
        FIELD_NODE_NAME,
    ]
)

# Token/Cost fields (metrics)
TOKEN_FIELDS = frozenset(
    [
        FIELD_TOKENS_IN,
        FIELD_TOKENS_OUT,
        FIELD_TOKENS_CACHE,
        FIELD_COST_EUR,
    ]
)

# Google API fields (metrics)
GOOGLE_API_FIELDS = frozenset(
    [
        FIELD_GOOGLE_API_REQUESTS,
        FIELD_GOOGLE_API_COST_EUR,
        FIELD_GOOGLE_API_COST_USD,
        FIELD_TOTAL_GOOGLE_API_REQUESTS,
        FIELD_TOTAL_GOOGLE_API_COST_EUR,
        FIELD_CYCLE_GOOGLE_API_REQUESTS,
        FIELD_CYCLE_GOOGLE_API_COST_EUR,
    ]
)

# Timestamp fields (for sorting, filtering)
TIMESTAMP_FIELDS = frozenset(
    [
        FIELD_CREATED_AT,
        FIELD_CACHED_AT,
        FIELD_TIMESTAMP,
    ]
)

# ============================================================
# VALIDATION HELPERS
# ============================================================


def is_identity_field(field_name: str) -> bool:
    """Check if field contains identity/PII data."""
    return field_name in IDENTITY_FIELDS


def is_token_field(field_name: str) -> bool:
    """Check if field contains token/cost metrics."""
    return field_name in TOKEN_FIELDS


def is_timestamp_field(field_name: str) -> bool:
    """Check if field is a timestamp."""
    return field_name in TIMESTAMP_FIELDS


def is_google_api_field(field_name: str) -> bool:
    """Check if field contains Google API metrics."""
    return field_name in GOOGLE_API_FIELDS


# ============================================================
# EXPORT
# ============================================================

__all__ = [
    # Field names
    "FIELD_USER_ID",
    "FIELD_SESSION_ID",
    "FIELD_THREAD_ID",
    "FIELD_CONVERSATION_ID",
    "FIELD_RUN_ID",
    "FIELD_TURN_ID",
    "FIELD_STEP_ID",
    "FIELD_WAVE_ID",
    "FIELD_PLAN_ID",
    "FIELD_AGENT_NAME",
    "FIELD_AGENT_TYPE",
    "FIELD_NODE_NAME",
    "FIELD_TOOL_NAME",
    "FIELD_TOKENS_IN",
    "FIELD_TOKENS_OUT",
    "FIELD_TOKENS_CACHE",
    "FIELD_COST_EUR",
    "FIELD_MODEL_NAME",
    "FIELD_STATUS",
    "FIELD_ROLE",
    "FIELD_ERROR_CODE",
    "FIELD_ERROR_MESSAGE",
    "FIELD_ERROR_TYPE",
    "FIELD_IS_ACTIVE",
    "FIELD_CONTENT",
    "FIELD_QUERY",
    "FIELD_OUTPUT",
    "FIELD_RESOURCE_NAME",
    "FIELD_INDEX",
    "FIELD_CONNECTOR",
    "FIELD_CONNECTOR_TYPE",
    "FIELD_CREATED_AT",
    "FIELD_CACHED_AT",
    "FIELD_TIMESTAMP",
    "FIELD_TOTAL",
    "FIELD_TOTAL_COUNT",
    "FIELD_MESSAGE_COUNT",
    "FIELD_TOTAL_TOKENS_IN",
    "FIELD_TOTAL_TOKENS_OUT",
    "FIELD_TOTAL_TOKENS_CACHE",
    "FIELD_TOTAL_COST_EUR",
    "FIELD_GOOGLE_API_REQUESTS",
    "FIELD_GOOGLE_API_COST_EUR",
    "FIELD_GOOGLE_API_COST_USD",
    "FIELD_TOTAL_GOOGLE_API_REQUESTS",
    "FIELD_TOTAL_GOOGLE_API_COST_EUR",
    "FIELD_CYCLE_GOOGLE_API_REQUESTS",
    "FIELD_CYCLE_GOOGLE_API_COST_EUR",
    "FIELD_METADATA",
    "FIELD_PARAMETERS",
    "FIELD_RESULT",
    "FIELD_ACTION_REQUESTS",
    "FIELD_DECISION",
    "FIELD_INTERRUPT_DATA",
    "FIELD_TYPE",
    "FIELD_DRAFT_ID",
    "FIELD_REGISTRY_ID",
    "FIELD_CORRELATION_PARENT_ID",
    "FIELD_CORRELATED_TO",
    # Field groups
    "IDENTITY_FIELDS",
    "LANGGRAPH_STATE_FIELDS",
    "TOKEN_FIELDS",
    "GOOGLE_API_FIELDS",
    "TIMESTAMP_FIELDS",
    # Usage Limits
    "FIELD_TOKEN_LIMIT_PER_CYCLE",
    "FIELD_MESSAGE_LIMIT_PER_CYCLE",
    "FIELD_COST_LIMIT_PER_CYCLE",
    "FIELD_TOKEN_LIMIT_ABSOLUTE",
    "FIELD_MESSAGE_LIMIT_ABSOLUTE",
    "FIELD_COST_LIMIT_ABSOLUTE",
    "FIELD_IS_USAGE_BLOCKED",
    "FIELD_BLOCKED_REASON",
    "FIELD_USAGE_LIMIT_STATUS",
    # Image Generation
    "FIELD_IMAGE_GENERATION_REQUESTS",
    "FIELD_IMAGE_GENERATION_COST_EUR",
    # Helpers
    "is_identity_field",
    "is_token_field",
    "is_google_api_field",
    "is_timestamp_field",
]
