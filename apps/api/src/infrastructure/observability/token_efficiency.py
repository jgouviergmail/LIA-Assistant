"""
Token Efficiency Helper - Extract and track LLM token efficiency ratio.

Phase 3.2 - Business Metrics - Step 2.4

Provides helper function to extract usage_metadata from TokenTrackingCallback
and track token_efficiency_ratio (output_tokens / input_tokens).

This ratio helps identify:
- Verbose agents (high ratio >1.5) - may indicate poor prompts
- Concise agents (low ratio <0.5) - optimal efficiency
- Balanced agents (ratio ~1.0) - typical conversational responses

Usage:
    from src.infrastructure.observability.token_efficiency import track_token_efficiency

    # In node after LLM call
    router_output = await _call_router_llm(messages, config=config)
    track_token_efficiency(config, node_name="router", agent_type="generic")
"""

import structlog
from langchain_core.runnables import RunnableConfig

from src.infrastructure.observability.metrics_business import token_efficiency_ratio

logger = structlog.get_logger(__name__)


def track_token_efficiency(
    config: RunnableConfig | None,
    node_name: str,
    agent_type: str = "generic",
) -> None:
    """
    Extract usage_metadata from TokenTrackingCallback and track token efficiency ratio.

    This function extracts token usage from callbacks in the config (similar to
    cache decorator pattern), calculates the efficiency ratio (output/input),
    and records it to the token_efficiency_ratio Prometheus histogram.

    Args:
        config: RunnableConfig containing callbacks with TokenTrackingCallback
        node_name: Name of the node (router, planner, response)
        agent_type: Type of agent for metrics (contacts, emails, generic, etc.)

    Returns:
        None

    Example:
        >>> config = RunnableConfig(callbacks=[TokenTrackingCallback(...)])
        >>> router_output = await _call_router_llm(messages, config=config)
        >>> track_token_efficiency(config, node_name="router", agent_type="generic")
        # Metric: token_efficiency_ratio{agent_type="generic", node_name="router"} = 0.75

    Notes:
        - Safely handles missing config or callbacks (no-op)
        - Logs warning if no usage_metadata found
        - Avoids division by zero (requires input_tokens > 0)
        - Does NOT clear _last_usage_metadata (cache decorator handles that)
    """
    if not config:
        logger.debug(
            "token_efficiency_no_config",
            node_name=node_name,
            msg="No config provided, skipping token efficiency tracking",
        )
        return

    if "callbacks" not in config:
        logger.debug(
            "token_efficiency_no_callbacks",
            node_name=node_name,
            msg="No callbacks in config, skipping token efficiency tracking",
        )
        return

    # Extract usage_metadata from TokenTrackingCallback (same pattern as cache decorator)
    usage_metadata = None
    callbacks = config.get("callbacks")

    # Type guard: ensure callbacks is iterable (list of callbacks)
    if callbacks is not None and isinstance(callbacks, list):
        for callback in callbacks:
            if hasattr(callback, "_last_usage_metadata"):
                usage_metadata = callback._last_usage_metadata
                break

    if not usage_metadata:
        logger.debug(
            "token_efficiency_no_usage",
            node_name=node_name,
            agent_type=agent_type,
            msg="No usage_metadata found in callbacks",
        )
        return

    # Extract input/output tokens
    input_tokens = usage_metadata.get("input_tokens", 0)
    output_tokens = usage_metadata.get("output_tokens", 0)

    # Validate input_tokens > 0 to avoid division by zero
    if input_tokens <= 0:
        logger.warning(
            "token_efficiency_zero_input",
            node_name=node_name,
            agent_type=agent_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            msg="Input tokens is zero or negative, skipping efficiency tracking",
        )
        return

    # Calculate efficiency ratio
    efficiency_ratio = output_tokens / input_tokens

    # Track metric
    token_efficiency_ratio.labels(agent_type=agent_type, node_name=node_name).observe(
        efficiency_ratio
    )

    logger.debug(
        "token_efficiency_tracked",
        node_name=node_name,
        agent_type=agent_type,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        efficiency_ratio=round(efficiency_ratio, 3),
    )


def extract_agent_type_from_router_output(next_node: str, intention: str) -> str:
    """
    Extract agent_type from router output for token efficiency tracking.

    Maps router decision (next_node, intention) to agent_type.

    Args:
        next_node: Next node from router decision (planner, response, etc.)
        intention: Intention from router (contacts_lookup, conversational, etc.)

    Returns:
        Agent type string (contacts, emails, generic)

    Example:
        >>> extract_agent_type_from_router_output("planner", "contacts_lookup")
        "contacts"
        >>> extract_agent_type_from_router_output("response", "conversational")
        "generic"

    Notes:
        - Router itself uses agent_type="generic" (no specific domain)
        - Intention provides hint about likely agent (contacts_lookup → contacts)
        - Fallback to "generic" if unknown pattern
    """
    # Router node itself is always "generic" (no specific domain)
    # Intent provides hint but router doesn't execute the actual agent

    # Pattern: intention often includes agent name prefix
    # contacts_lookup, contacts_search → contacts
    # email_search, email_lookup → emails
    # conversational, clarification → generic

    intention_lower = intention.lower()

    if "contact" in intention_lower:
        return "contacts"
    elif "email" in intention_lower or "mail" in intention_lower:
        return "emails"
    elif "event" in intention_lower:
        return "events"
    elif "drive" in intention_lower or "file" in intention_lower:
        return "drive"
    else:
        # Generic for conversational, clarification, unknown
        return "generic"
