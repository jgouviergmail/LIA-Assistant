"""
Centralized LangGraph state keys for agent orchestration.

This module provides constants for LangGraph state management keys to:
- Prevent typos in state access (IDE autocomplete)
- Enable easy refactoring (rename state keys globally)
- Provide centralized documentation of state schema

Usage:
    from domains.agents.state_keys import STATE_AGENT_RESULTS, STATE_ROUTING_HISTORY

    # Old (typo-prone)
    state["agent_results"] = results

    # New (typo-safe)
    state[STATE_AGENT_RESULTS] = results

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-15
"""

# ============================================================
# LANGGRAPH STATE KEYS
# ============================================================

# Agent Results & Execution
STATE_AGENT_RESULTS = "agent_results"
STATE_COMPLETED_STEPS = "completed_steps"
STATE_ACTION_REQUESTS = "action_requests"

# Routing & Navigation
STATE_ROUTING_HISTORY = "routing_history"
STATE_ROUTER_DECISION = "router_decision"

# Turn & Context
STATE_CURRENT_TURN_ID = "current_turn_id"
STATE_CURRENT_ITEM = "current_item"
STATE_LAST_QUERY = "last_query"

# HITL & Approval
STATE_REJECTION_REASON = "rejection_reason"
STATE_PLAN_APPROVAL = "plan_approval"

# Metadata & Configuration
STATE_MESSAGE_METADATA = "message_metadata"
STATE_ROUTER_SYSTEM_PROMPT = "router_system_prompt"
STATE_DATA_SOURCE = "data_source"
STATE_STEP_INDEX = "step_index"

# ============================================================
# STATE SCHEMA DOCUMENTATION
# ============================================================

STATE_SCHEMA = {
    STATE_AGENT_RESULTS: {
        "type": "dict[str, Any]",
        "description": "Results from agent executions, keyed by agent name",
        "example": {"contacts_agent": {"status": "success", "data": [...]}},
    },
    STATE_COMPLETED_STEPS: {
        "type": "list[str]",
        "description": "List of completed step IDs in execution plan",
        "example": ["step_001", "step_002"],
    },
    STATE_ACTION_REQUESTS: {
        "type": "list[dict]",
        "description": "Pending action requests from user (HITL)",
        "example": [{"action": "approve", "target": "tool_call_123"}],
    },
    STATE_ROUTING_HISTORY: {
        "type": "list[str]",
        "description": "History of node routing decisions",
        "example": ["router", "planner", "task_orchestrator"],
    },
    STATE_ROUTER_DECISION: {
        "type": "dict",
        "description": "Latest routing decision from router node",
        "example": {"target": "contacts_agent", "confidence": 0.95},
    },
    STATE_CURRENT_TURN_ID: {
        "type": "int",
        "description": "Current conversation turn ID",
        "example": 42,
    },
    STATE_CURRENT_ITEM: {
        "type": "dict | None",
        "description": "Current context item being processed",
        "example": {"id": "contact_123", "name": "John Doe"},
    },
    STATE_LAST_QUERY: {
        "type": "str",
        "description": "Last user query/message",
        "example": "Find contacts in Paris",
    },
    STATE_REJECTION_REASON: {
        "type": "str | None",
        "description": "Reason for plan/tool rejection (HITL)",
        "example": "User declined to modify contact",
    },
    STATE_PLAN_APPROVAL: {
        "type": "dict | None",
        "description": "Plan approval status from HITL",
        "example": {"status": "approved", "modified": False},
    },
    STATE_MESSAGE_METADATA: {
        "type": "dict",
        "description": "Metadata attached to messages",
        "example": {"source": "web", "timestamp": "2025-11-15T10:00:00Z"},
    },
    STATE_ROUTER_SYSTEM_PROMPT: {
        "type": "str",
        "description": "System prompt for router LLM",
        "example": "You are a routing agent...",
    },
    STATE_DATA_SOURCE: {
        "type": "str",
        "description": "Source of data being processed",
        "example": "google_contacts",
    },
    STATE_STEP_INDEX: {
        "type": "int",
        "description": "Current step index in execution plan",
        "example": 2,
    },
}

# ============================================================
# STATE KEY GROUPS
# ============================================================

CORE_STATE_KEYS: frozenset[str] = frozenset(
    {
        STATE_CURRENT_TURN_ID,
        STATE_ROUTING_HISTORY,
        STATE_ROUTER_DECISION,
        STATE_LAST_QUERY,
        STATE_CURRENT_ITEM,
    }
)

EXECUTION_STATE_KEYS: frozenset[str] = frozenset(
    {
        STATE_AGENT_RESULTS,
        STATE_COMPLETED_STEPS,
        STATE_STEP_INDEX,
    }
)

HITL_STATE_KEYS: frozenset[str] = frozenset(
    {
        STATE_ACTION_REQUESTS,
        STATE_REJECTION_REASON,
        STATE_PLAN_APPROVAL,
    }
)

METADATA_STATE_KEYS: frozenset[str] = frozenset(
    {
        STATE_MESSAGE_METADATA,
        STATE_ROUTER_SYSTEM_PROMPT,
        STATE_DATA_SOURCE,
    }
)

ALL_STATE_KEYS: frozenset[str] = frozenset(
    {
        STATE_AGENT_RESULTS,
        STATE_COMPLETED_STEPS,
        STATE_ACTION_REQUESTS,
        STATE_ROUTING_HISTORY,
        STATE_ROUTER_DECISION,
        STATE_CURRENT_TURN_ID,
        STATE_CURRENT_ITEM,
        STATE_LAST_QUERY,
        STATE_REJECTION_REASON,
        STATE_PLAN_APPROVAL,
        STATE_MESSAGE_METADATA,
        STATE_ROUTER_SYSTEM_PROMPT,
        STATE_DATA_SOURCE,
        STATE_STEP_INDEX,
    }
)

# ============================================================
# VALIDATION HELPERS
# ============================================================


def validate_state_key(key: str | None) -> bool:
    """Check if a key is a valid state key."""
    if key is None:
        return False
    return key in ALL_STATE_KEYS


def is_core_state_key(key: str | None) -> bool:
    """Check if a key belongs to core state keys."""
    if key is None:
        return False
    return key in CORE_STATE_KEYS


def is_execution_state_key(key: str | None) -> bool:
    """Check if a key belongs to execution state keys."""
    if key is None:
        return False
    return key in EXECUTION_STATE_KEYS


def is_hitl_state_key(key: str | None) -> bool:
    """Check if a key belongs to HITL state keys."""
    if key is None:
        return False
    return key in HITL_STATE_KEYS


def get_state_key_schema(key: str | None) -> dict[str, object] | None:
    """Get schema documentation for a state key."""
    if key is None:
        return None
    return STATE_SCHEMA.get(key)  # type: ignore[return-value]


# ============================================================
# EXPORT
# ============================================================

__all__ = [
    # State keys
    "STATE_AGENT_RESULTS",
    "STATE_COMPLETED_STEPS",
    "STATE_ACTION_REQUESTS",
    "STATE_ROUTING_HISTORY",
    "STATE_ROUTER_DECISION",
    "STATE_CURRENT_TURN_ID",
    "STATE_CURRENT_ITEM",
    "STATE_LAST_QUERY",
    "STATE_REJECTION_REASON",
    "STATE_PLAN_APPROVAL",
    "STATE_MESSAGE_METADATA",
    "STATE_ROUTER_SYSTEM_PROMPT",
    "STATE_DATA_SOURCE",
    "STATE_STEP_INDEX",
    # Schema
    "STATE_SCHEMA",
    # Groups
    "ALL_STATE_KEYS",
    "CORE_STATE_KEYS",
    "EXECUTION_STATE_KEYS",
    "HITL_STATE_KEYS",
    "METADATA_STATE_KEYS",
    # Helpers
    "validate_state_key",
    "is_core_state_key",
    "is_execution_state_key",
    "is_hitl_state_key",
    "get_state_key_schema",
]
