"""
Prometheus metrics for business-level KPIs and product analytics.

Tracks conversation quality, cost efficiency, agent effectiveness, and user engagement.
Critical for product decisions, cost optimization, and ROI measurement.

Business Metrics Categories:
- Conversation cost & efficiency (cost per conversation, avg tokens/conversation)
- Conversation abandonment (when/why users stop engaging)
- Agent effectiveness (success rate, routing accuracy, tool usage)
- User engagement (messages per conversation, return rate)
- Feature adoption (tool usage, connector activation)

Reference:
- Product Analytics Best Practices
- SaaS Metrics (CAC, LTV, Churn, Engagement)
- Cost Optimization (FinOps for LLMs)
"""

from prometheus_client import Counter, Gauge, Histogram

from src.core.field_names import FIELD_NODE_NAME, FIELD_TOOL_NAME

# ============================================================================
# CONVERSATION COST METRICS
# ============================================================================

conversation_cost_usd = Histogram(
    "conversation_cost_usd",
    "Cost per conversation in USD (distribution)",
    ["agent_type"],
    # agent_type: the turn's execution mode (pipeline, react); generic without one,
    # unknown when the calculation failed
    # Buckets optimized for typical LLM conversation costs
    # $0.001 (1 mill) to $1 (expensive multi-turn conversations)
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

conversation_tokens_total = Histogram(
    "conversation_tokens_total",
    "Total tokens consumed per conversation (distribution)",
    ["agent_type"],
    # Tracks prompt + completion tokens across all turns
    buckets=[100, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000],
)

# ============================================================================
# CONVERSATION ABANDONMENT METRICS
# ============================================================================

conversation_abandonment_total = Counter(
    "conversation_abandonment_total",
    "Total conversations abandoned (user stopped responding)",
    ["abandonment_reason", "agent_type"],
    # abandonment_reason: timeout, user_reset, error, hitl_unanswered
    # Critical for identifying UX friction points
)

conversation_abandonment_at_message_count = Histogram(
    "conversation_abandonment_at_message_count",
    "Message count when conversations are abandoned",
    ["abandonment_reason"],
    # Identifies if users abandon early (1-2 messages) vs late (10+ messages)
    buckets=[1, 2, 3, 5, 10, 15, 20, 30, 50],
)

# ============================================================================
# AGENT EFFECTIVENESS METRICS
# ============================================================================


agent_success_rate_total = Counter(
    "agent_success_rate_total",
    "Total agent execution outcomes",
    ["agent_type", "outcome"],
    # agent_type: the turn's execution mode (pipeline, react); generic without one
    # (a failed calculation judges no agent, so it is never counted here)
    # outcome: success, failure, partial_success — judged on the CURRENT
    # turn's own evidence: the planner's verdict, the agents' results, the
    # ReAct loop's result, the drafts the person confirmed; a turn that left
    # no agent execution to read is not counted (business_metrics.OUTCOME_NO_AGENT)
)

agent_tool_usage_total = Counter(
    "agent_tool_usage_total",
    "Total tool invocations by agent and tool",
    ["agent_type", FIELD_TOOL_NAME, "outcome"],
    # outcome: success, failure, user_rejected
    # Tracks which tools are most used and their success rates
)

# ============================================================================
# USER ENGAGEMENT METRICS
# ============================================================================

user_return_rate_total = Counter(
    "user_return_rate_total",
    "Users returning to app after first conversation",
    ["time_window"],
    # time_window: 24h, 7d, 30d
    # Measures user retention and product stickiness
)

user_daily_conversations_total = Histogram(
    "user_daily_conversations_total",
    "Number of conversations per user per day",
    buckets=[1, 2, 3, 5, 10, 20, 50],
    # Identifies power users vs casual users
)

conversation_turns_total = Histogram(
    "conversation_turns_total",
    "Number of user-agent turns per conversation",
    ["agent_type"],
    # A turn = 1 user message + 1 agent response
    # High turn count indicates engaged users
    buckets=[1, 2, 3, 5, 7, 10, 15, 20, 30],
)

# ============================================================================
# FEATURE ADOPTION METRICS
# ============================================================================

connector_activation_rate = Gauge(
    "connector_activation_rate",
    "Percentage of users with at least one active connector (0-1)",
    ["connector_type"],
    # connector_type: google_contacts, gmail, google_drive, etc.
    # Measures feature adoption
    multiprocess_mode="mostrecent",
)

# ============================================================================
# COST EFFICIENCY METRICS
# ============================================================================

cost_per_successful_conversation_usd = Histogram(
    "cost_per_successful_conversation_usd",
    "Model cost in USD of a successful turn at its answer, from its run's own accounting",
    ["agent_type"],
    # One observation per successful TURN — the outcome is the turn's —
    # never the thread's running total. Critical for ROI calculation.
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

token_efficiency_ratio = Histogram(
    "token_efficiency_ratio",
    "Ratio of output tokens to input tokens (creativity indicator)",
    ["agent_type", FIELD_NODE_NAME],
    # High ratio = agent is verbose (may indicate poor prompts)
    # Low ratio = agent is concise
    buckets=[0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0],
)
