"""
Agents configuration module.

Contains settings for:
- SSE (Server-Sent Events)
- State Management (LangGraph)
- Message Windowing
- Agent Iteration Limits
- Human-in-the-Loop (HITL) configuration
- Router configuration
- Planner configuration (including hierarchical planner)
- Context Resolution
- Prompt Versioning

Phase: PHASE 2.1 - Config Split
Created: 2025-11-20
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings

from src.core.constants import (
    AGENT_HISTORY_KEEP_LAST_DEFAULT,
    AGENT_MAX_ITERATIONS_DEFAULT,
    AGENT_MAX_ITERATIONS_MAX,
    # Context Compaction
    COMPACTION_CHUNK_MAX_TOKENS_DEFAULT,
    COMPACTION_ENABLED_DEFAULT,
    COMPACTION_MIN_MESSAGES_DEFAULT,
    COMPACTION_PRESERVE_RECENT_MESSAGES_DEFAULT,
    COMPACTION_THRESHOLD_RATIO_DEFAULT,
    COMPACTION_TOKEN_THRESHOLD_DEFAULT,
    CONTACTS_AGENT_PROMPT_VERSION_DEFAULT,
    DEFAULT_MESSAGE_WINDOW_SIZE,
    EMAILS_AGENT_PROMPT_VERSION_DEFAULT,
    FOR_EACH_APPROVAL_THRESHOLD,
    FOR_EACH_MAX_DEFAULT,
    FOR_EACH_MAX_HARD_LIMIT,
    FOR_EACH_WARNING_THRESHOLD,
    HEARTBEAT_ACTIVITY_COOLDOWN_MINUTES_DEFAULT,
    HEARTBEAT_CONTEXT_CALENDAR_HOURS_DEFAULT,
    HEARTBEAT_CONTEXT_EMAILS_MAX_DEFAULT,
    HEARTBEAT_CONTEXT_MEMORY_LIMIT_DEFAULT,
    HEARTBEAT_CONTEXT_TASKS_DAYS_DEFAULT,
    HEARTBEAT_GLOBAL_COOLDOWN_HOURS_DEFAULT,
    HEARTBEAT_INACTIVE_SKIP_DAYS_DEFAULT,
    HEARTBEAT_NOTIFICATION_BATCH_SIZE_DEFAULT,
    HEARTBEAT_NOTIFICATION_INTERVAL_MINUTES_DEFAULT,
    HEARTBEAT_WEATHER_RAIN_THRESHOLD_HIGH_DEFAULT,
    HEARTBEAT_WEATHER_RAIN_THRESHOLD_LOW_DEFAULT,
    HEARTBEAT_WEATHER_TEMP_CHANGE_THRESHOLD_DEFAULT,
    HEARTBEAT_WEATHER_WIND_THRESHOLD_DEFAULT,
    HITL_CLASSIFIER_PROMPT_VERSION_DEFAULT,
    HITL_PLAN_APPROVAL_QUESTION_PROMPT_VERSION_DEFAULT,
    HITL_QUESTION_GENERATOR_PROMPT_VERSION_DEFAULT,
    INSUFFICIENT_CONTENT_MIN_CHARS_THRESHOLD_DEFAULT,
    INTEREST_NOTIFY_INTERVAL_MINUTES_DEFAULT,
    MAX_MESSAGES_HISTORY_DEFAULT,
    MAX_TOKENS_HISTORY_DEFAULT,
    # Hybrid Memory Search
    MEMORY_BM25_CACHE_MAX_USERS_DEFAULT,
    MEMORY_HYBRID_ALPHA_DEFAULT,
    MEMORY_HYBRID_BOOST_THRESHOLD_DEFAULT,
    MEMORY_HYBRID_MIN_SCORE_DEFAULT,
    ORCHESTRATOR_MESSAGE_WINDOW_SIZE_DEFAULT,
    PLAN_PATTERN_REDIS_PREFIX,
    PLANNER_LLM_FREQUENCY_PENALTY_DEFAULT,
    PLANNER_LLM_MAX_TOKENS_DEFAULT,
    PLANNER_LLM_PRESENCE_PENALTY_DEFAULT,
    PLANNER_LLM_TOP_P_DEFAULT,
    PLANNER_MAX_COST_USD_DEFAULT,
    PLANNER_MAX_REPLANS_DEFAULT,
    PLANNER_MAX_STEPS_DEFAULT,
    PLANNER_MAX_STEPS_HARD_LIMIT,
    PLANNER_MESSAGE_WINDOW_SIZE_DEFAULT,
    PLANNER_PROMPT_VERSION_DEFAULT,
    PLANNER_TIMEOUT_SECONDS,
    PROACTIVE_CROSS_TYPE_COOLDOWN_MINUTES_DEFAULT,
    RESPONSE_MESSAGE_WINDOW_SIZE_DEFAULT,
    RESPONSE_PROMPT_VERSION_DEFAULT,
    ROUTER_MESSAGE_WINDOW_SIZE_DEFAULT,
    ROUTER_PROMPT_VERSION_DEFAULT,
    SEMANTIC_VALIDATOR_PROMPT_VERSION_DEFAULT,
    SSE_HEARTBEAT_INTERVAL_DEFAULT,
    # Sub-Agents (F6)
    SUB_AGENTS_ENABLED_DEFAULT,
    SUBAGENT_DEFAULT_MAX_ITERATIONS_DEFAULT,
    SUBAGENT_DEFAULT_TIMEOUT_DEFAULT,
    SUBAGENT_MAX_CONCURRENT_DEFAULT,
    SUBAGENT_MAX_CONSECUTIVE_FAILURES_DEFAULT,
    SUBAGENT_MAX_DEPTH_DEFAULT,
    SUBAGENT_MAX_PER_USER_DEFAULT,
    SUBAGENT_MAX_TOKEN_BUDGET_DEFAULT,
    SUBAGENT_MAX_TOTAL_TOKENS_PER_DAY_DEFAULT,
    SUBAGENT_STALE_RECOVERY_INTERVAL_DEFAULT,
    TOKEN_THRESHOLD_CRITICAL_DEFAULT,
    TOKEN_THRESHOLD_MAX_DEFAULT,
    TOKEN_THRESHOLD_SAFE_DEFAULT,
    TOKEN_THRESHOLD_WARNING_DEFAULT,
    # V3 Architecture Constants
    V3_DISPLAY_ENABLED,
    V3_DISPLAY_MAX_ITEMS_PER_DOMAIN,
    V3_DISPLAY_SHOW_ACTION_BUTTONS,
    V3_DISPLAY_VIEWPORT_MOBILE_MAX_WIDTH,
    V3_DOMAIN_CALIBRATED_PRIMARY_MIN,
    V3_DOMAIN_MIN_RANGE_FOR_DISCRIMINATION,
    V3_DOMAIN_SCORE_DELTA_MIN,
    V3_DOMAIN_SECONDARY_THRESHOLD,
    V3_DOMAIN_SOFTMAX_TEMPERATURE,
    V3_EXECUTOR_CIRCUIT_BREAKER_THRESHOLD,
    V3_EXECUTOR_MAX_RECOVERY_PER_STEP,
    V3_EXECUTOR_MAX_TOTAL_RECOVERIES,
    V3_EXECUTOR_RECOVERY_TIMEOUT_MS,
    V3_FEEDBACK_LOOP_CONFIDENCE_THRESHOLD,
    V3_FEEDBACK_LOOP_MAX_RECORDS,
    V3_FEEDBACK_LOOP_MIN_SAMPLES,
    V3_RELEVANCE_MINIMUM_THRESHOLD,
    V3_RELEVANCE_PRIMARY_THRESHOLD,
    V3_ROUTER_PROMPT_VERSION,
    V3_ROUTING_CHAT_OVERRIDE_THRESHOLD,
    V3_ROUTING_CHAT_SEMANTIC_THRESHOLD,
    V3_ROUTING_CROSS_DOMAIN_THRESHOLD,
    V3_ROUTING_HIGH_SEMANTIC_THRESHOLD,
    V3_ROUTING_MIN_CONFIDENCE,
    V3_SMART_PLANNER_PROMPT_VERSION,
    V3_TOOL_CALIBRATED_PRIMARY_MIN,
    V3_TOOL_SOFTMAX_TEMPERATURE,
)


class AgentsSettings(BaseSettings):
    """Agent orchestration and LLM interaction settings."""

    # ========================================================================
    # SSE (Server-Sent Events) Configuration
    # ========================================================================
    sse_heartbeat_interval: int = Field(
        default=SSE_HEARTBEAT_INTERVAL_DEFAULT,
        gt=0,
        description="SSE heartbeat interval in seconds (prevents timeout)",
    )

    # ========================================================================
    # State Management (LangGraph)
    # ========================================================================
    max_messages_history: int = Field(
        default=MAX_MESSAGES_HISTORY_DEFAULT,
        gt=0,
        description="Max number of messages to keep in conversation history",
    )
    max_tokens_history: int = Field(
        default=MAX_TOKENS_HISTORY_DEFAULT,
        gt=0,
        description="Max tokens to keep in conversation history (truncation)",
    )
    agent_history_keep_last: int = Field(
        default=AGENT_HISTORY_KEEP_LAST_DEFAULT,
        gt=0,
        description="Number of recent messages to keep in agent LLM input (preserves tool results for context)",
    )

    # ========================================================================
    # Memory Management (Cleanup & LRU Eviction)
    # ========================================================================
    # Controls memory retention for agent results, routing history, and data registry
    # These limits prevent unbounded memory growth in long-running conversations
    max_agent_results: int = Field(
        default=10,  # Imported from domains.agents.constants
        ge=1,
        le=100,
        description="Max agent_results to keep in state (cleanup per turn, prevents memory bloat)",
    )
    max_routing_history: int = Field(
        default=30,  # Imported from domains.agents.constants
        ge=1,
        le=200,
        description="Max routing history entries to keep (cleanup per turn)",
    )
    registry_max_items: int = Field(
        default=100,  # From REGISTRY_MAX_ITEMS_DEFAULT
        ge=10,
        le=1000,
        description="Max items in data registry (LRU eviction for cross-turn references)",
    )

    # ========================================================================
    # Message Windowing (Performance Optimization)
    # ========================================================================
    # Controls how many conversation TURNS to keep when sending to LLMs
    # Reduces token count and latency without losing contextual accuracy
    # Store preserves full business context independently
    default_message_window_size: int = Field(
        default=DEFAULT_MESSAGE_WINDOW_SIZE,
        ge=1,
        le=100,
        description="Default window size (turns) for message windowing (1 turn = user + assistant)",
    )
    router_message_window_size: int = Field(
        default=ROUTER_MESSAGE_WINDOW_SIZE_DEFAULT,
        ge=1,
        le=50,
        description="Router window size: minimal context for fast routing decisions (default: 4 turns)",
    )
    planner_message_window_size: int = Field(
        default=PLANNER_MESSAGE_WINDOW_SIZE_DEFAULT,
        ge=1,
        le=50,
        description="Planner window size: moderate context for plan generation (default: 4 turns)",
    )
    response_message_window_size: int = Field(
        default=RESPONSE_MESSAGE_WINDOW_SIZE_DEFAULT,
        ge=1,
        le=100,
        description="Response window size: rich context for creative synthesis (default: 10 turns)",
    )
    orchestrator_message_window_size: int = Field(
        default=ORCHESTRATOR_MESSAGE_WINDOW_SIZE_DEFAULT,
        ge=1,
        le=50,
        description="Orchestrator window size: minimal context for plan execution (default: 4 turns)",
    )

    # ========================================================================
    # Agent Iteration Limits (Security)
    # ========================================================================
    agent_max_iterations: int = Field(
        default=AGENT_MAX_ITERATIONS_DEFAULT,
        gt=0,
        le=AGENT_MAX_ITERATIONS_MAX,
        description="Max iterations for ReAct agents (security: prevents infinite loops & cost explosion)",
    )

    # ========================================================================
    # Node Timeouts (Sprint 17.4 - Gold-Grade Production)
    # ========================================================================
    # LLM call timeouts for each node type - prevents runaway operations
    router_llm_timeout_seconds: float = Field(
        default=5.0,
        ge=1.0,
        le=30.0,
        description="Timeout for router LLM call (fast routing decision)",
    )
    response_llm_timeout_seconds: float = Field(
        default=60.0,
        ge=5.0,
        le=180.0,
        description="Timeout for response node LLM call (synthesis, longer due to streaming)",
    )
    task_orchestrator_execution_timeout_seconds: float = Field(
        default=120.0,
        ge=30.0,
        le=600.0,
        description="Max execution time for task orchestrator (all steps combined)",
    )
    hitl_max_wait_seconds: int = Field(
        default=900,
        ge=60,
        le=3600,
        description="Max time to wait for HITL user response (15 min default)",
    )

    # ========================================================================
    # LangChain Agent Middleware (P0 Migration - Chantier 7)
    # ========================================================================
    # Middleware for agent LLM calls - retry, summarization, etc.
    # See: src/infrastructure/llm/middleware_config.py

    # NOTE: ModelRetryMiddleware is always enabled (automatic retry on transient failures)

    retry_max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum retry attempts for ModelRetryMiddleware (default: 3)",
    )
    retry_backoff_factor: float = Field(
        default=2.0,
        ge=1.0,
        le=10.0,
        description=(
            "Exponential backoff factor for retries. "
            "Wait time = backoff_factor^attempt seconds (default: 2.0 → 2s, 4s, 8s)"
        ),
    )

    # NOTE: SummarizationMiddleware is always enabled (context compression when approaching limits)

    summarization_model: str = Field(
        default="gpt-4.1-nano",
        description=(
            "LLM model for context summarization (fast, cheap model recommended). "
            "Default: gpt-4.1-nano for optimal speed/cost balance."
        ),
    )
    summarization_trigger_fraction: float = Field(
        default=0.7,
        ge=0.3,
        le=0.95,
        description=(
            "Fraction of max context to trigger summarization (0.7 = 70% of limit). "
            "Lower = more aggressive compression, Higher = less compression."
        ),
    )
    summarization_keep_messages: int = Field(
        default=10,
        ge=3,
        le=50,
        description=(
            "Number of recent messages to keep verbatim (not summarized). "
            "Ensures recent context is preserved for tool results and continuity."
        ),
    )

    # ========================================================================
    # ModelFallbackMiddleware - Multi-Provider Resilience
    # ========================================================================
    # Automatic fallback to alternative providers on errors (rate limits, outages)

    # NOTE: ModelFallbackMiddleware is always enabled (automatic provider failover)

    fallback_models: str = Field(
        default="claude-sonnet-4-5,deepseek-chat",
        description=(
            "Comma-separated list of fallback models (in priority order). "
            "Used when primary model fails. Default: Anthropic → DeepSeek."
        ),
    )

    # ========================================================================
    # ToolRetryMiddleware - Tool Execution Resilience
    # ========================================================================
    # Automatic retry of failed tool calls (Google API transient errors, etc.)

    # NOTE: ToolRetryMiddleware is always enabled (automatic tool call retries)

    tool_retry_max_attempts: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Maximum retry attempts for failed tool calls (default: 3)",
    )
    tool_retry_backoff_factor: float = Field(
        default=1.5,
        ge=1.0,
        le=5.0,
        description=(
            "Exponential backoff factor for tool retries. "
            "Wait time = backoff_factor^attempt seconds (default: 1.5 → 1.5s, 2.25s, 3.4s)"
        ),
    )

    # ========================================================================
    # ModelCallLimitMiddleware - Cost & Loop Protection
    # ========================================================================
    # Enforces maximum model calls per thread/run to prevent infinite loops

    # NOTE: ModelCallLimitMiddleware is always enabled (cost protection)

    model_call_thread_limit: int = Field(
        default=100,
        ge=10,
        le=500,
        description=(
            "Maximum LLM calls per conversation thread (default: 100). "
            "Prevents runaway conversations from consuming excessive tokens."
        ),
    )
    model_call_run_limit: int = Field(
        default=20,
        ge=5,
        le=50,
        description=(
            "Maximum LLM calls per single agent run (default: 20). "
            "Safety limit for single request execution depth."
        ),
    )

    # ========================================================================
    # ContextEditingMiddleware - Tool Result Pruning
    # ========================================================================
    # Automatically trims verbose tool outputs to manage context size

    # NOTE: ContextEditingMiddleware is always enabled (tool result pruning)

    context_edit_max_tool_result_tokens: int = Field(
        default=2000,
        ge=500,
        le=10000,
        description=(
            "Maximum tokens per tool result before truncation (default: 2000). "
            "Tool outputs exceeding this limit are summarized or truncated."
        ),
    )

    # ========================================================================
    # Human-in-the-Loop (HITL) Tool Approval
    # ========================================================================
    # Migration Note (2025-11): Moved to manifest-driven architecture
    # Tool approval requirements now defined in tool manifests (permissions.hitl_required)
    tool_approval_cleanup_days: int = Field(
        default=7,
        gt=0,
        description="Days before cleaning up abandoned tool approvals",
    )

    # ========================================================================
    # HITL Semantic Validation (2025-11-25 - Phase 2 OPTIMPLAN)
    # ========================================================================
    # Validates that execution plans semantically match user intent
    # NOTE: Semantic validation is always enabled (detects cardinality mismatches, etc.)

    semantic_validation_timeout_seconds: float = Field(
        default=10.0,
        ge=0.5,
        le=30.0,
        description=(
            "Timeout for semantic validation (optimistic validation). "
            "If validation exceeds this timeout, assumes plan is valid (fail-open). "
            "Default: 10.0s - increased for proper CARDINALITY_MISMATCH detection (Issue #60)."
        ),
    )
    semantic_validation_confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description=(
            "Confidence threshold for semantic validation clarifications. "
            "Only trigger clarification if LLM confidence < this threshold AND issues found. "
            "Higher = less strict (fewer clarifications), Lower = more strict. "
            "Default: 0.7 - balanced between catching real issues and avoiding over-questioning."
        ),
    )

    # ========================================================================
    # HITL Insufficient Content Detection (Pre-LLM Clarification)
    # ========================================================================
    # Detects when user requests mutation tools (send_email, create_event, etc.)
    # without providing necessary content (subject, body, title).
    # Triggers HITL clarification BEFORE LLM planning to save tokens.
    # Example: "send an email to marie" → asks "What would you like to write?"
    insufficient_content_min_chars_threshold: int = Field(
        default=INSUFFICIENT_CONTENT_MIN_CHARS_THRESHOLD_DEFAULT,
        ge=10,
        le=100,
        description=(
            "Minimum remaining characters after pattern removal to consider content sufficient. "
            "If user's request has more than this many characters after removing recipient "
            "patterns (e.g., 'to marie'), we assume they provided inline content. "
            "Example: 'send email to marie wishing happy birthday' → sufficient (>30 chars). "
            "Higher = more clarifications, Lower = more tolerant."
        ),
    )

    # ========================================================================
    # Plan Pattern Learning (2026-01-12 - Dynamic learning from successes/failures)
    # ========================================================================
    # Learns from planner outcomes to improve future plans and skip validation
    plan_pattern_training_enabled: bool = Field(
        default=True,
        description=(
            "Enable pattern training (recording). When enabled, the system records "
            "plan successes/failures to Redis (fire-and-forget). "
            "Set to False to freeze learning while still using existing patterns. "
            "NOTE: Plan pattern learning is always enabled."
        ),
    )

    # Bayesian prior: Beta(α, β) - initial confidence = α/(α+β)
    plan_pattern_prior_alpha: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Bayesian prior alpha. Default Beta(2,1) = 67% initial confidence.",
    )
    plan_pattern_prior_beta: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Bayesian prior beta. Higher values = more conservative learning.",
    )

    # Decision thresholds for suggestions
    plan_pattern_min_obs_suggest: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Minimum observations (K-anonymity) before suggesting a pattern.",
    )
    plan_pattern_min_conf_suggest: float = Field(
        default=0.75,
        ge=0.5,
        le=0.95,
        description="Minimum confidence (0-1) to suggest a pattern. Default 75%.",
    )

    # Decision thresholds for validation bypass (stricter)
    plan_pattern_min_obs_bypass: int = Field(
        default=10,
        ge=5,
        le=50,
        description="Minimum observations before allowing validation bypass.",
    )
    plan_pattern_min_conf_bypass: float = Field(
        default=0.90,
        ge=0.8,
        le=0.99,
        description="Minimum confidence (0-1) to bypass validation. Default 90%.",
    )

    # Performance limits
    plan_pattern_max_suggestions: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum patterns injected in prompt (token budget).",
    )
    plan_pattern_suggestion_timeout_ms: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Timeout (ms) for Redis lookup. Fail-open on timeout.",
    )
    plan_pattern_local_cache_ttl_s: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="Local cache TTL (seconds) to reduce Redis calls.",
    )

    # Redis storage
    plan_pattern_redis_prefix: str = Field(
        default=PLAN_PATTERN_REDIS_PREFIX,
        description="Redis key prefix for pattern storage.",
    )
    plan_pattern_redis_ttl_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Pattern expiration in days (TTL).",
    )

    # ========================================================================
    # Semantic Linking - Cross-domain parameter linking (2026-01)
    # ========================================================================
    # Enables automatic suggestions for parameter sources based on semantic_type
    # matching between tool outputs and inputs.
    semantic_linking_enabled: bool = Field(
        default=True,
        description=(
            "Enable semantic linking for automatic parameter source suggestions. "
            "When enabled, the planner receives hints about cross-domain parameter linking "
            "based on semantic_type matching in tool manifests."
        ),
    )
    semantic_expansion_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description=(
            "Toggle threshold for semantic domain expansion (0.0-1.0). "
            "Values < 1.0: enable expansion (add providers from source_domains). "
            "Value = 1.0: disable expansion (no providers added). "
            "Default: 0.7 - enables expansion for cross-domain queries."
        ),
    )
    semantic_linking_max_suggestions: int = Field(
        default=5,
        ge=1,
        le=20,
        description=(
            "Maximum semantic linking suggestions per parameter in planner context. "
            "Limits token usage while providing useful cross-domain hints."
        ),
    )

    # ========================================================================
    # Text Compaction - Token Optimization for Embedded Data (2026-01)
    # ========================================================================
    # Post-Jinja evaluation compaction of embedded data structures in text parameters.
    # When planner uses $steps.X.places in content_instruction, Jinja evaluates to
    # full Python repr (~2000 tokens/place). Text compaction detects and compacts
    # these embedded structures using payload_to_text() (~60 tokens/place).
    text_compaction_enabled: bool = Field(
        default=True,
        description=(
            "Enable automatic compaction of embedded data structures in text parameters. "
            "Detects Python data structures in content_instruction, body, etc. and "
            "compacts them using payload_to_text() to reduce token usage."
        ),
    )
    text_compaction_min_size: int = Field(
        default=200,
        ge=50,
        le=2000,
        description=(
            "Minimum size (characters) for a data structure to be compacted. "
            "Smaller structures don't yield significant token savings."
        ),
    )
    text_compaction_max_items: int = Field(
        default=3,
        ge=1,
        le=10,
        description=(
            "Maximum items to show per list in compacted format. "
            "Excess items are summarized with (+N) suffix."
        ),
    )
    text_compaction_max_field_length: int = Field(
        default=40,
        ge=10,
        le=200,
        description=(
            "Maximum length for field values in compacted format. "
            "Longer values are truncated with ellipsis."
        ),
    )

    # ========================================================================
    # Context Compaction — Intelligent History Summarization (2026-03)
    # ========================================================================
    # LLM-based compaction of conversation history when token count exceeds
    # a dynamic threshold derived from the response model's context window.
    # The compaction node runs before the router and replaces old messages
    # with a summary preserving critical identifiers (UUIDs, URLs, IDs).
    compaction_enabled: bool = Field(
        default=COMPACTION_ENABLED_DEFAULT,
        description="Enable intelligent context compaction via LLM summarization.",
    )
    compaction_threshold_ratio: float = Field(
        default=COMPACTION_THRESHOLD_RATIO_DEFAULT,
        ge=0.1,
        le=0.9,
        description=(
            "Ratio of the response LLM's context window used as compaction trigger. "
            "E.g., 0.4 with a 200k model triggers at 80k tokens."
        ),
    )
    compaction_token_threshold: int = Field(
        default=COMPACTION_TOKEN_THRESHOLD_DEFAULT,
        ge=0,
        description=(
            "Absolute token threshold override. "
            "0 = use dynamic ratio (compaction_threshold_ratio * response model context window)."
        ),
    )
    compaction_preserve_recent_messages: int = Field(
        default=COMPACTION_PRESERVE_RECENT_MESSAGES_DEFAULT,
        ge=2,
        le=50,
        description="Number of recent messages to preserve (never compacted).",
    )
    compaction_chunk_max_tokens: int = Field(
        default=COMPACTION_CHUNK_MAX_TOKENS_DEFAULT,
        ge=1000,
        le=100000,
        description="Maximum tokens per chunk sent to the compaction LLM for summarization.",
    )
    compaction_min_messages: int = Field(
        default=COMPACTION_MIN_MESSAGES_DEFAULT,
        ge=5,
        le=200,
        description=(
            "Minimum number of messages before considering compaction. "
            "Fast-path: skip token counting if fewer messages than this."
        ),
    )

    # ========================================================================
    # Adaptive Re-Planning (INTELLIPLANNER Phase E - 2025-12-03)
    # ========================================================================
    # Intelligent recovery from execution failures (empty results, partial failures)
    adaptive_replanning_max_attempts: int = Field(
        default=3,
        ge=1,
        le=5,
        description=(
            "Maximum re-planning attempts before giving up. "
            "Each attempt may modify search criteria or strategy. "
            "Default: 3 - allows recovery while preventing infinite loops."
        ),
    )
    adaptive_replanning_empty_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description=(
            "Fraction of empty results that triggers re-planning consideration. "
            "0.8 = trigger if 80%+ of successful steps returned no results. "
            "Higher = less sensitive (fewer re-plans), Lower = more sensitive."
        ),
    )

    # ========================================================================
    # Hybrid Memory Search (BM25 + Semantic) - 2026-01
    # ========================================================================
    # Combines keyword-based (BM25) and semantic (pgvector) search for improved recall.
    # Reference: infrastructure/store/bm25_index.py, infrastructure/store/semantic_store.py
    memory_hybrid_enabled: bool = Field(
        default=True,
        description=(
            "Enable hybrid BM25+semantic search for memories. "
            "When disabled, falls back to semantic-only search."
        ),
    )
    memory_hybrid_alpha: float = Field(
        default=MEMORY_HYBRID_ALPHA_DEFAULT,
        ge=0.0,
        le=1.0,
        description=(
            "Weight for semantic score in hybrid search (0.0-1.0). "
            "Formula: final_score = alpha * semantic + (1-alpha) * bm25. "
            "Higher = more semantic, Lower = more keyword matching."
        ),
    )
    memory_hybrid_min_score: float = Field(
        default=MEMORY_HYBRID_MIN_SCORE_DEFAULT,
        ge=0.0,
        le=1.0,
        description=("Minimum combined score for inclusion in hybrid search results."),
    )
    memory_hybrid_boost_threshold: float = Field(
        default=MEMORY_HYBRID_BOOST_THRESHOLD_DEFAULT,
        ge=0.0,
        le=1.0,
        description=(
            "Threshold for 'both high' bonus. "
            "If both semantic and BM25 scores exceed this, apply 10% boost."
        ),
    )
    memory_bm25_cache_max_users: int = Field(
        default=MEMORY_BM25_CACHE_MAX_USERS_DEFAULT,
        ge=10,
        le=1000,
        description=(
            "Maximum users in BM25 local cache (LRU eviction). "
            "Higher = more memory usage, fewer cache misses."
        ),
    )

    # ========================================================================
    # HITL Plan-Level Approval Strategies (2025-11-09)
    # ========================================================================
    # Approval strategies for plan-level HITL before execution
    approval_cost_threshold_usd: float = Field(
        default=5.00,
        ge=0.0,
        description="Cost threshold for plan approval (plans above this require approval)",
    )
    approval_auto_approve_roles: list[str] = Field(
        default=["admin", "power_user"],
        description="User roles that can auto-approve plans without HITL",
    )
    approval_sensitive_classifications: list[str] = Field(
        default=["CONFIDENTIAL", "RESTRICTED"],
        description="Data classifications that trigger approval requirement",
    )

    # ========================================================================
    # HITL Conversational Classifier Configuration
    # ========================================================================
    hitl_classifier_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(default="openai", description="LLM provider for HITL classifier")
    hitl_classifier_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for HITL classifier (JSON string)",
    )
    hitl_classifier_llm_model: str = Field(
        default="",
        description="Deprecated: use LLM_DEFAULTS. LLM model for HITL classifier.",
    )
    hitl_classifier_llm_temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Temperature for HITL classifier (0.2 for deterministic classification)",
    )
    hitl_classifier_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p (nucleus sampling) for HITL classifier",
    )
    hitl_classifier_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for HITL classifier",
    )
    hitl_classifier_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for HITL classifier",
    )
    hitl_classifier_llm_max_tokens: int = Field(
        default=300,
        ge=1,
        description="Max tokens for HITL classifier response",
    )
    hitl_classifier_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description=(
            "Reasoning effort for HITL classifier LLM (OpenAI o-series/GPT-5 only). "
            "Controls reasoning depth: minimal=sub-second (GPT-5), low=1-3s, medium=5-15s, high=30+s. "
            "Recommended: 'minimal' for HITL classifier (fast classification, deterministic)."
        ),
    )
    hitl_classifier_confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Confidence threshold for HITL classification (below = ask clarification)",
    )

    # ========================================================================
    # HITL Ambiguity Detection Configuration
    # ========================================================================
    hitl_ambiguous_confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Confidence threshold for ambiguous HITL responses (below = ask user for clarification)",
    )
    hitl_fuzzy_match_ambiguity_threshold: float = Field(
        default=0.05,
        ge=0.0,
        le=0.5,
        description="Threshold for fuzzy match ambiguity detection (if scores within this %, consider ambiguous)",
    )
    hitl_low_confidence_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Threshold for low confidence rejection inference. "
            "When inferring rejection type, if classifier confidence < this threshold, "
            "the rejection is categorized as 'low_confidence' (needs clarification). "
            "Issue #60 Fix: Was hardcoded to 0.5."
        ),
    )

    # ========================================================================
    # HITL Question Generator Configuration (Conversational Clarifications)
    # ========================================================================
    hitl_question_generator_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(default="anthropic", description="LLM provider for HITL question generator")
    hitl_question_generator_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for HITL question generator (JSON string)",
    )
    hitl_question_generator_llm_model: str = Field(
        default="",
        description="Deprecated: use LLM_DEFAULTS. LLM model for HITL question generator.",
    )
    hitl_question_generator_llm_temperature: float = Field(
        default=0.5,
        ge=0.0,
        le=2.0,
        description="Temperature for HITL question generator (0.5 for creative questions)",
    )
    hitl_question_generator_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p (nucleus sampling) for HITL question generator",
    )
    hitl_question_generator_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for HITL question generator (reduce repetition)",
    )
    hitl_question_generator_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for HITL question generator (encourage diversity)",
    )
    hitl_question_generator_llm_max_tokens: int = Field(
        default=500,
        gt=0,
        description=(
            "Max tokens for HITL question generator response. "
            "Keep low (500) to generate SHORT confirmation questions, not essays. "
            "Tool-level HITL questions should be 1-2 sentences."
        ),
    )
    hitl_question_generator_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description=(
            "Reasoning effort for HITL question generator LLM (OpenAI o-series/GPT-5 only). "
            "Controls reasoning depth: minimal=sub-second (GPT-5), low=1-3s, medium=5-15s, high=30+s. "
            "Recommended: 'minimal' for HITL question generator (fast clarification questions, deterministic)."
        ),
    )

    # ========================================================================
    # HITL Plan Approval Question Generator Configuration (Plan-level Explanations)
    # ========================================================================
    hitl_plan_approval_question_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(
        default="openai", description="LLM provider for HITL plan approval question generator"
    )
    hitl_plan_approval_question_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for HITL plan approval question generator (JSON string)",
    )
    hitl_plan_approval_question_llm_model: str = Field(
        default="",
        description="Deprecated: use LLM_DEFAULTS. LLM model for HITL plan approval question generator.",
    )
    hitl_plan_approval_question_llm_temperature: float = Field(
        default=0.5,
        ge=0.0,
        le=2.0,
        description="Temperature for HITL plan approval question generator (0.5 for creative)",
    )
    hitl_plan_approval_question_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p (nucleus sampling) for HITL plan approval question generator",
    )
    hitl_plan_approval_question_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for HITL plan approval question generator (reduce repetition)",
    )
    hitl_plan_approval_question_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for HITL plan approval question generator (encourage diversity)",
    )
    hitl_plan_approval_question_llm_max_tokens: int = Field(
        default=500,
        gt=0,
        description=(
            "Max tokens for HITL plan approval question generator response. "
            "Keep low (500) to generate concise plan summaries, not verbose explanations. "
            "Plan-level HITL questions should be 2-4 sentences with bullet points."
        ),
    )
    hitl_plan_approval_question_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description=(
            "Reasoning effort for HITL plan approval question generator LLM (OpenAI o-series/GPT-5 only). "
            "Controls reasoning depth: minimal=sub-second (GPT-5), low=1-3s, medium=5-15s, high=30+s. "
            "Recommended: 'minimal' for plan approval questions (clear explanations, deterministic)."
        ),
    )

    # ========================================================================
    # Router Debug Logging
    # ========================================================================
    router_debug_log_enabled: bool = Field(
        default=False,
        description="Enable separate debug log for router reasoning",
    )
    router_debug_log_path: str = Field(
        default="/var/log/lia/router_debug.log",
        description="Path to router debug log file",
    )

    # ========================================================================
    # Router Confidence Thresholds
    # ========================================================================
    router_confidence_high: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="High confidence threshold for router decisions",
    )
    router_confidence_medium: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Medium confidence threshold for router decisions",
    )
    router_confidence_low: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Low confidence threshold for router decisions",
    )

    # ========================================================================
    # Token Overflow Fallback Configuration (Phase B)
    # ========================================================================
    # Progressive fallback thresholds for catalogue reduction when token count exceeds limits.
    # Reduces token usage by filtering catalogue based on detected domains.
    token_threshold_safe: int = Field(
        default=TOKEN_THRESHOLD_SAFE_DEFAULT,
        gt=0,
        description="Safe zone - full catalogue (no reduction needed). GPT-4.1-mini supports 128k context.",
    )
    token_threshold_warning: int = Field(
        default=TOKEN_THRESHOLD_WARNING_DEFAULT,
        gt=0,
        description="Warning zone - filter to detected domains only",
    )
    token_threshold_critical: int = Field(
        default=TOKEN_THRESHOLD_CRITICAL_DEFAULT,
        gt=0,
        description="Critical zone - reduce descriptions to minimal",
    )
    token_threshold_max: int = Field(
        default=TOKEN_THRESHOLD_MAX_DEFAULT,
        gt=0,
        description="Maximum zone - emergency fallback (primary domain only)",
    )

    # ========================================================================
    # Planner Configuration (Phase 5 - Multi-Agent Orchestration)
    # ========================================================================
    planner_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(default="openai", description="LLM provider for planner")
    planner_llm_provider_config: str = Field(
        default="{}", description="Advanced provider-specific config for planner (JSON string)"
    )
    planner_llm_model: str = Field(
        default="",
        description="Deprecated: use LLM_DEFAULTS. LLM model for planner node.",
    )
    planner_llm_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Temperature for planner (0.0 = deterministic, precise plan generation)",
    )
    planner_llm_top_p: float = Field(
        default=PLANNER_LLM_TOP_P_DEFAULT,
        ge=0.0,
        le=1.0,
        description="Top-p sampling for planner LLM",
    )
    planner_llm_frequency_penalty: float = Field(
        default=PLANNER_LLM_FREQUENCY_PENALTY_DEFAULT,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for planner LLM",
    )
    planner_llm_presence_penalty: float = Field(
        default=PLANNER_LLM_PRESENCE_PENALTY_DEFAULT,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for planner LLM",
    )
    planner_llm_max_tokens: int = Field(
        default=PLANNER_LLM_MAX_TOKENS_DEFAULT,
        gt=0,
        description="Max tokens for planner LLM response (ExecutionPlan JSON)",
    )
    planner_llm_reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = (
        Field(
            default="medium",
            description=(
                "Reasoning effort for planner LLM (OpenAI o-series/GPT-5 only). "
                "Controls reasoning depth: minimal=sub-second (GPT-5), low=1-3s, medium=5-15s, high=30+s. "
                "Recommended: 'medium' for planner (thorough multi-agent orchestration)."
            ),
        )
    )
    planner_max_steps: int = Field(
        default=PLANNER_MAX_STEPS_DEFAULT,
        gt=0,
        le=PLANNER_MAX_STEPS_HARD_LIMIT,
        description="Maximum steps allowed in a plan (security & cost control)",
    )
    planner_max_cost_usd: float = Field(
        default=PLANNER_MAX_COST_USD_DEFAULT,
        gt=0.0,
        description="Default budget limit per plan in USD",
    )
    planner_max_replans: int = Field(
        default=PLANNER_MAX_REPLANS_DEFAULT,
        ge=0,
        description="Maximum replanning attempts (Phase 2 feature)",
    )
    planner_timeout_seconds: int = Field(
        default=PLANNER_TIMEOUT_SECONDS,
        gt=0,
        description="Timeout for planner LLM response in seconds",
    )

    # FOR_EACH iteration pattern configuration
    for_each_max_default: int = Field(
        default=FOR_EACH_MAX_DEFAULT,
        gt=0,
        le=FOR_EACH_MAX_HARD_LIMIT,
        description=(
            f"Default maximum items for for_each iteration (safety limit). "
            f"Hard limit: {FOR_EACH_MAX_HARD_LIMIT}. "
            "Individual steps can override with for_each_max parameter."
        ),
    )
    for_each_max_hard_limit: int = Field(
        default=FOR_EACH_MAX_HARD_LIMIT,
        gt=0,
        le=1000,
        description=(
            "Absolute maximum for for_each_max (schema validation limit). "
            "Values above this will be auto-corrected if planner_auto_correct_for_each_max=True."
        ),
    )
    planner_auto_correct_for_each_max: bool = Field(
        default=True,
        description=(
            "Auto-correct for_each_max values exceeding hard limit instead of failing. "
            "When True, values are capped to for_each_max_hard_limit with a warning log. "
            "Enables defensive programming against non-deterministic LLM outputs."
        ),
    )
    for_each_mutation_threshold: int = Field(
        default=1,
        ge=1,
        le=100,
        description=(
            "Minimum number of mutations to trigger HITL confirmation. "
            "Default=1 means ANY mutation FOR_EACH requires approval. "
            "Set to 3 for less intrusive behavior (only 3+ items trigger HITL)."
        ),
    )
    for_each_approval_threshold: int = Field(
        default=FOR_EACH_APPROVAL_THRESHOLD,
        ge=1,
        le=100,
        description=(
            "Threshold for non-mutation for_each to require HITL approval. "
            "Default=5 means 5+ iterations on read-only operations need approval."
        ),
    )
    for_each_warning_threshold: int = Field(
        default=FOR_EACH_WARNING_THRESHOLD,
        ge=1,
        le=1000,
        description=(
            "Warning level threshold for non-mutation for_each iterations. "
            "Default=10 means 10+ iterations trigger warning-level HITL."
        ),
    )
    planner_prompt_version: str = Field(
        default=PLANNER_PROMPT_VERSION_DEFAULT,
        description="Planner system prompt version (for A/B testing and rollbacks)",
    )
    # ========================================================================
    # Context Resolution (Turn-based context management)
    # ========================================================================
    context_reference_resolution_enabled: bool = Field(
        default=True,
        description="Enable reference resolution for follow-up questions (e.g., 'et le deuxième?')",
    )
    context_reference_confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score for reference resolution (0.0-1.0)",
    )
    context_active_window_turns: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of previous turns to consider for active context",
    )
    context_resolution_timeout_ms: int = Field(
        default=500,
        gt=0,
        description="Timeout for context resolution in milliseconds",
    )

    # ========================================================================
    # Context Tools (Batch Operations)
    # ========================================================================
    MAX_CONTEXT_BATCH_SIZE: int = Field(
        default=10,
        ge=1,
        le=100,
        description=(
            "Maximum items returned by get_context_list tool (batch operations). "
            "Limits batch size to prevent OOM and timeout issues. "
            "Range: 1-100, default: 10."
        ),
    )

    # ========================================================================
    # Long-Term Memory (Psychological Profiling)
    # ========================================================================
    # LangMem-powered memory system for building user psychological profiles.
    # Memories are semantic-searched and injected into conversation context.
    # Background extraction runs asynchronously after each response.
    memory_extraction_enabled: bool = Field(
        default=True,
        description=(
            "Enable background psychoanalytical extraction from conversations. "
            "Runs asynchronously after each response to detect and store "
            "implicit information about the user (emotions, relationships, patterns)."
        ),
    )
    memory_max_results: int = Field(
        default=10,
        ge=1,
        le=50,
        description=(
            "Maximum memories to retrieve per semantic search. "
            "Higher values provide more context but increase token usage."
        ),
    )
    memory_min_search_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum similarity score for memory retrieval (0.0-1.0). "
            "Higher values = stricter matching, fewer but more relevant memories. "
            "Default 0.5 balances precision and recall for conversational memory."
        ),
    )
    memory_extraction_llm_model: str = Field(
        default="gpt-4.1-mini",
        description=(
            "LLM model for background memory extraction. "
            "Use a fast, cost-effective model (extraction runs frequently). "
            "Default: gpt-4.1-mini for optimal cost/quality balance."
        ),
    )
    memory_extraction_llm_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description=(
            "Temperature for memory extraction LLM. "
            "Lower = more consistent extraction, Higher = more creative detection."
        ),
    )
    memory_extraction_max_tokens: int = Field(
        default=1000,
        ge=100,
        le=4000,
        description="Max tokens for memory extraction LLM response.",
    )
    memory_extraction_message_max_chars: int = Field(
        default=3000,
        ge=500,
        le=10000,
        description=(
            "Max characters per message for memory extraction. "
            "Longer messages are truncated. Default: 3000 (good balance cost/coverage)."
        ),
    )
    memory_extraction_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description=(
            "Top-p (nucleus sampling) for memory extraction LLM. "
            "Default: 1.0 (use temperature only for sampling, recommended for extraction)."
        ),
    )
    memory_extraction_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description=(
            "Frequency penalty for memory extraction LLM. "
            "Default: 0.0 (no penalty, extraction benefits from consistent patterns)."
        ),
    )
    memory_extraction_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description=(
            "Presence penalty for memory extraction LLM. "
            "Default: 0.0 (no penalty, extraction should detect all relevant information)."
        ),
    )
    memory_extraction_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description="Reasoning effort for memory extraction LLM (OpenAI o-series/GPT-5 only).",
    )
    memory_embedding_model: str = Field(
        default="intfloat/multilingual-e5-small",
        description=(
            "Embedding model for semantic memory search. "
            "For local: intfloat/multilingual-e5-small (384 dims, 100 languages). "
            "For OpenAI: text-embedding-3-small (1536 dims)."
        ),
    )
    memory_embedding_dimensions: int = Field(
        default=384,
        ge=256,
        le=3072,
        description=(
            "Embedding dimensions for pgvector index. "
            "E5-small: 384, E5-base: 768, text-embedding-3-small: 1536."
        ),
    )

    # ========================================================================
    # Long-Term Memory - Purge Configuration (Phase 6)
    # ========================================================================
    # Controls automatic cleanup of old, unused memories.
    # Uses a hybrid strategy: usage_count + importance + emotional_weight + age.
    memory_max_age_days: int = Field(
        default=180,
        ge=1,
        le=730,
        description=(
            "Maximum age (in days) before a memory becomes eligible for purge. "
            "Default: 180 days (6 months). Memories younger than this are never purged."
        ),
    )
    memory_min_usage_count: int = Field(
        default=3,
        ge=1,
        le=100,
        description=(
            "Minimum usage count for protection from purge. "
            "Memories used >= this many times get a boost in retention score."
        ),
    )
    memory_purge_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description=(
            "Retention score threshold below which memories are purged (0.0-1.0). "
            "Score = 0.4*usage + 0.3*importance + 0.3*recency. "
            "Lower threshold = more aggressive purge."
        ),
    )
    memory_cleanup_hour: int = Field(
        default=4,
        ge=0,
        le=23,
        description="Hour (UTC) for daily memory cleanup job. Default: 4 AM UTC.",
    )
    memory_cleanup_minute: int = Field(
        default=0,
        ge=0,
        le=59,
        description="Minute for daily memory cleanup job. Default: 0.",
    )
    memory_relevance_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum semantic search score to count as a 'relevant' access. "
            "Only accesses with score >= this value increment usage_count. "
            "Prevents inflation from low-relevance retrievals."
        ),
    )
    memory_retention_weight_usage: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description=(
            "Weight for usage_count in retention score calculation. "
            "Higher = more importance to frequently accessed memories."
        ),
    )
    memory_retention_weight_importance: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description=(
            "Weight for importance field in retention score calculation. "
            "Higher = more importance to high-importance memories."
        ),
    )
    memory_retention_weight_recency: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description=(
            "Weight for recency in retention score calculation. "
            "Higher = more importance to recent memories."
        ),
    )
    # ========================================================================
    # Memory Reference Resolution (Pre-Planner Entity Resolution)
    # ========================================================================
    # Resolves relational references ("my brother") to entity names ("john doe")
    # before the planner generates the execution plan.
    # Uses LLM micro-call for robust multilingual resolution.
    # NOTE: Memory reference resolution is always enabled

    memory_reference_resolution_timeout_ms: int = Field(
        default=2000,
        ge=100,
        le=10000,
        description=(
            "Timeout for memory reference resolution LLM call in milliseconds. "
            "If exceeded, returns original query (fail-safe). "
            "Default: 2000ms. Increase if LLM calls timeout frequently."
        ),
    )
    memory_reference_resolution_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(
        default="openai",
        description="LLM provider for memory reference resolution",
    )
    memory_reference_resolution_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for memory reference resolution (JSON string)",
    )
    memory_reference_resolution_llm_model: str = Field(
        default="gpt-4.1-mini",
        description=(
            "LLM model for memory reference resolution micro-call. "
            "Use a fast, cheap model (extraction is simple). "
            "Default: gpt-4.1-mini. Consider gpt-4.1-nano if available."
        ),
    )
    memory_reference_resolution_llm_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Temperature for memory reference resolution (0.0 = deterministic extraction)",
    )
    memory_reference_resolution_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p (nucleus sampling) for memory reference resolution",
    )
    memory_reference_resolution_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for memory reference resolution",
    )
    memory_reference_resolution_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for memory reference resolution",
    )
    memory_reference_resolution_llm_max_tokens: int = Field(
        default=250,
        gt=0,
        description=(
            "Max output tokens for memory reference resolution. "
            "Default: 250 (JSON response with resolved_query + multiple mappings)."
        ),
    )
    memory_reference_resolution_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description=(
            "Reasoning effort for memory reference resolution (OpenAI o-series only). "
            "None = disabled. For simple name extraction, reasoning is not needed."
        ),
    )

    # NOTE: force_planner_routing removed - debug flag no longer needed
    # NOTE: recipient_resolution_enabled removed - always enabled, no toggle needed

    # ========================================================================
    # Prompt Versioning (All Agents & Nodes)
    # ========================================================================
    router_prompt_version: str = Field(
        default=ROUTER_PROMPT_VERSION_DEFAULT,
        description="Router system prompt version (for A/B testing and rollbacks)",
    )
    # NOTE: Dynamic domain injection is now always enabled.
    # Domains are generated at runtime from DOMAIN_REGISTRY in domain_taxonomy.py.
    # This is the single source of truth for domain definitions.
    response_prompt_version: str = Field(
        default=RESPONSE_PROMPT_VERSION_DEFAULT,
        description="Response node system prompt version (for A/B testing and rollbacks)",
    )
    contacts_agent_prompt_version: str = Field(
        default=CONTACTS_AGENT_PROMPT_VERSION_DEFAULT,
        description="Contacts agent system prompt version (for A/B testing and rollbacks)",
    )
    emails_agent_prompt_version: str = Field(
        default=EMAILS_AGENT_PROMPT_VERSION_DEFAULT,
        description="Gmail agent system prompt version (for A/B testing and rollbacks)",
    )
    hitl_classifier_prompt_version: str = Field(
        default=HITL_CLASSIFIER_PROMPT_VERSION_DEFAULT,
        description="HITL classifier system prompt version (for A/B testing and rollbacks)",
    )
    hitl_question_generator_prompt_version: str = Field(
        default=HITL_QUESTION_GENERATOR_PROMPT_VERSION_DEFAULT,
        description="HITL question generator prompt version (tool-level, for A/B testing)",
    )
    hitl_plan_approval_question_prompt_version: str = Field(
        default=HITL_PLAN_APPROVAL_QUESTION_PROMPT_VERSION_DEFAULT,
        description="HITL plan approval question prompt version (plan-level, for A/B testing)",
    )
    semantic_validator_prompt_version: str = Field(
        default=SEMANTIC_VALIDATOR_PROMPT_VERSION_DEFAULT,
        description="Semantic validator prompt version (plan validation, for A/B testing)",
    )

    # ========================================================================
    # VALIDATORS - Empty String to None Conversion
    # ========================================================================
    # Pydantic-settings reads env vars as strings. Empty strings ("") are NOT
    # automatically converted to None for Optional fields with Literal types.
    # This validator ensures empty strings in .env are treated as None.

    # ========================================================================
    # Semantic Tool Selector (Router Enhancement)
    # ========================================================================
    # SemanticToolSelector provides domain hints to the router using embeddings.
    # Used for semantic domain detection in router_node.
    semantic_tool_selector_hard_threshold: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description=(
            "Hard threshold for semantic tool selection (high confidence). "
            "Tools with similarity >= this threshold are directly injected. "
            "Default: 0.70 for precise matching."
        ),
    )
    semantic_tool_selector_soft_threshold: float = Field(
        default=0.60,
        ge=0.0,
        le=1.0,
        description=(
            "Soft threshold for semantic tool selection (uncertainty zone). "
            "Tools between soft and hard thresholds are included with lower confidence. "
            "Default: 0.60 for broader matching."
        ),
    )
    semantic_tool_selector_max_tools: int = Field(
        default=8,
        ge=1,
        le=20,
        description=(
            "Maximum tools to return from semantic selection. "
            "Limits tool catalogue size to prevent context overflow. "
            "Default: 8 (good balance between capability and context size)."
        ),
    )
    # Tool Softmax Calibration (same pipeline as domain selector)
    v3_tool_softmax_temperature: float = Field(
        default=V3_TOOL_SOFTMAX_TEMPERATURE,
        ge=0.01,
        le=1.0,
        description=(
            "Softmax temperature for tool score calibration. "
            "Amplifies small score differences for better discrimination. "
            "Lower = sharper discrimination (0.1 recommended with stretching)."
        ),
    )
    v3_tool_calibrated_primary_min: float = Field(
        default=V3_TOOL_CALIBRATED_PRIMARY_MIN,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum calibrated score for primary tool (after softmax). "
            "Primary tool is accepted only if calibrated_score >= this threshold."
        ),
    )

    # Semantic Tool Selector - Hybrid Scoring (CORRECTION 7)
    v3_tool_selector_hybrid_alpha: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description=(
            "Weight for description score in hybrid scoring. "
            "0.6 = 60% description, 40% keywords. "
            "Set to 0.0 to use keywords only."
        ),
    )
    v3_tool_selector_hybrid_mode: str = Field(
        default="first_line",
        description=(
            "Description extraction mode for embedding: "
            "'first_line' (default, ~60-150 chars), 'full', 'truncate'."
        ),
    )
    v3_tool_selector_hybrid_enabled: bool = Field(
        default=True,
        description=(
            "Enable hybrid scoring (description + keywords). "
            "Set to False for keywords-only legacy mode."
        ),
    )

    # ========================================================================
    # Semantic Domain Selector
    # ========================================================================
    semantic_domain_hard_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="High confidence domain match threshold",
    )
    semantic_domain_soft_threshold: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        description="Uncertainty zone domain threshold",
    )
    semantic_domain_max_domains: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Max domains to return",
    )

    # ========================================================================
    # Semantic Intent Detector
    # ========================================================================
    semantic_intent_fallback_threshold: float = Field(
        default=0.50,
        ge=0.0,
        le=1.0,
        description="Below this, use fallback 'full' intent",
    )
    semantic_intent_high_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="High confidence threshold for intent detection",
    )

    # ========================================================================
    # Semantic Fallback
    # ========================================================================
    semantic_fallback_threshold: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Fallback to perplexity/wikipedia when confidence < this",
    )

    # ========================================================================
    # Query Engine
    # ========================================================================
    query_engine_similarity_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Similarity threshold for duplicate detection",
    )

    # ========================================================================
    # Semantic Pivot LLM Configuration (Query Translation for Embeddings)
    # ========================================================================
    # Translates user queries to English before embedding matching.
    # Uses a fast, cheap model (gpt-4.1-mini) for optimal latency.
    # This dramatically improves embedding-based tool selection since
    # embeddings work best in English (dominant training language).
    semantic_pivot_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(
        default="openai",
        description="LLM provider for semantic pivot translation (query to English)",
    )
    semantic_pivot_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for semantic pivot (JSON string)",
    )
    semantic_pivot_llm_model: str = Field(
        default="gpt-4.1-mini",
        description=(
            "LLM model for semantic pivot translation. "
            "Use a fast, cheap model (translation is simple). "
            "Default: gpt-4.1-mini for optimal speed/cost balance."
        ),
    )
    semantic_pivot_llm_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Temperature for semantic pivot (0.0 = deterministic translation)",
    )
    semantic_pivot_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p (nucleus sampling) for semantic pivot",
    )
    semantic_pivot_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for semantic pivot",
    )
    semantic_pivot_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for semantic pivot",
    )
    semantic_pivot_llm_max_tokens: int = Field(
        default=100,
        gt=0,
        description=(
            "Max tokens for semantic pivot response (short translated query). "
            "Default: 100 (translations are brief, e.g., 'Get my last 2 emails')."
        ),
    )
    semantic_pivot_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description=(
            "Reasoning effort for semantic pivot LLM (OpenAI o-series/GPT-5 only). "
            "Recommended: None or 'minimal' for fast translation."
        ),
    )

    # ========================================================================
    # Broadcast Translation LLM Configuration
    # ========================================================================
    # Translates admin broadcast messages to each user's preferred language.
    # Uses gpt-4.1-nano for cost-effective translation.
    broadcast_translator_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(
        default="openai",
        description="LLM provider for broadcast message translation",
    )
    broadcast_translator_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for broadcast translator (JSON string)",
    )
    broadcast_translator_llm_model: str = Field(
        default="gpt-5-mini",
        description="LLM model for broadcast translation. gpt-5-mini for quality + reasoning.",
    )
    broadcast_translator_llm_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Temperature for broadcast translation. Low value for consistent translations.",
    )
    broadcast_translator_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p (nucleus sampling) for broadcast translation",
    )
    broadcast_translator_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for broadcast translation",
    )
    broadcast_translator_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for broadcast translation",
    )
    broadcast_translator_llm_max_tokens: int = Field(
        default=500,
        gt=0,
        description="Max tokens for broadcast translation response. 500 sufficient for typical messages.",
    )
    broadcast_translator_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default="minimal",
        description="Reasoning effort for broadcast translator LLM (OpenAI o-series/GPT-5 only).",
    )

    # ========================================================================
    # V3 ARCHITECTURE CONFIGURATION
    # ========================================================================
    # Configurable parameters for v3 components: Intelligence, Autonomy, Relevance
    # All defaults are imported from src.core.constants (V3_* constants)
    # These can be overridden via .env for tuning without code changes.

    # ------------------------------------------------------------------------
    # V3 Routing (QueryAnalyzerService)
    # ------------------------------------------------------------------------
    v3_routing_chat_semantic_threshold: float = Field(
        default=V3_ROUTING_CHAT_SEMANTIC_THRESHOLD,
        ge=0.0,
        le=1.0,
        description=(
            "Semantic score threshold below which queries are routed to chat. "
            "Queries with semantic_score < this value are considered simple conversation."
        ),
    )
    v3_routing_high_semantic_threshold: float = Field(
        default=V3_ROUTING_HIGH_SEMANTIC_THRESHOLD,
        ge=0.0,
        le=1.0,
        description=(
            "Semantic score threshold above which queries are routed to planner with high confidence. "
            "Queries with semantic_score >= this value trigger tool-based execution."
        ),
    )
    v3_routing_min_confidence: float = Field(
        default=V3_ROUTING_MIN_CONFIDENCE,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum confidence score for planner route. "
            "Used as floor when determining routing confidence."
        ),
    )
    v3_routing_chat_override_threshold: float = Field(
        default=V3_ROUTING_CHAT_OVERRIDE_THRESHOLD,
        ge=0.0,
        le=1.0,
        description=(
            "Chat intent confidence threshold for domain override. "
            "When intent is 'chat' with confidence >= this threshold, domain detection is ignored. "
            "This prevents false-positive domain matches (e.g., 'conversational greeting' matching "
            "'email conversation' keyword) from triggering expensive planner calls (~9000 tokens)."
        ),
    )
    v3_routing_cross_domain_threshold: float = Field(
        default=V3_ROUTING_CROSS_DOMAIN_THRESHOLD,
        ge=0.0,
        le=1.0,
        description=(
            "Cross-domain reference threshold. "
            "When user references an item from domain A but asks for info from domain B, "
            "if domain B detection score >= this threshold, route to domain B instead of A. "
            "Example: 'search info about the restaurant of the 2nd appointment' routes to places, not calendar."
        ),
    )

    # ------------------------------------------------------------------------
    # V3 Domain Selection (SemanticDomainSelector)
    # ------------------------------------------------------------------------
    v3_domain_score_delta_min: float = Field(
        default=V3_DOMAIN_SCORE_DELTA_MIN,
        ge=0.0,
        le=0.5,
        description=(
            "Minimum score delta between top domain and others for multi-domain selection. "
            "Domains with score < (top_score - delta) are filtered out. "
            "Example: top=0.87, delta=0.05 → only domains with score >= 0.82 are kept. "
            "This prevents false-positive multi-domain detection (e.g., emails when contacts is primary)."
        ),
    )
    v3_domain_secondary_threshold: float = Field(
        default=V3_DOMAIN_SECONDARY_THRESHOLD,
        ge=0.0,
        le=1.0,
        description=(
            "Absolute minimum score for secondary domains (2nd, 3rd, etc.). "
            "1st domain: accepted if score >= soft_threshold (0.65). "
            "2nd+ domains: must have score >= THIS threshold AND pass delta check. "
            "This prevents low-relevance domains from being included just because "
            "their score is within delta of the top domain. "
            "Example: top=0.85, secondary=0.80 → tasks(0.82) accepted, places(0.78) rejected."
        ),
    )
    v3_domain_softmax_temperature: float = Field(
        default=V3_DOMAIN_SOFTMAX_TEMPERATURE,
        ge=0.01,
        le=1.0,
        description=(
            "Softmax temperature for domain score calibration. "
            "Amplifies small score differences for better discrimination. "
            "Lower = sharper discrimination (0.05 recommended). "
            "T=1.0 disables calibration. T=0.05 transforms [0.83,0.86] into [0.05,0.65]."
        ),
    )
    v3_domain_min_range_for_discrimination: float = Field(
        default=V3_DOMAIN_MIN_RANGE_FOR_DISCRIMINATION,
        ge=0.0,
        le=0.2,
        description=(
            "Minimum raw score range for meaningful discrimination. "
            "If all domain scores are within this range, they're treated as equally relevant "
            "and softmax calibration won't artificially create a winner. "
            "Example: range=0.03 means [0.87, 0.86, 0.85] are considered equally relevant. "
            "This prevents the 'winner-takes-all' effect when embeddings can't discriminate."
        ),
    )
    v3_domain_calibrated_primary_min: float = Field(
        default=V3_DOMAIN_CALIBRATED_PRIMARY_MIN,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum calibrated score for primary domain (after softmax). "
            "Primary domain is accepted only if calibrated_score >= this threshold."
        ),
    )

    # ------------------------------------------------------------------------
    # V3 Executor (AutonomousExecutor)
    # ------------------------------------------------------------------------
    v3_executor_max_recovery_per_step: int = Field(
        default=V3_EXECUTOR_MAX_RECOVERY_PER_STEP,
        ge=1,
        le=10,
        description=(
            "Maximum recovery attempts per individual execution step. "
            "Higher values = more resilient but potentially longer execution."
        ),
    )
    v3_executor_max_total_recoveries: int = Field(
        default=V3_EXECUTOR_MAX_TOTAL_RECOVERIES,
        ge=1,
        le=20,
        description=(
            "Maximum total recovery attempts across entire plan execution. "
            "Hard limit to prevent infinite recovery loops."
        ),
    )
    v3_executor_recovery_timeout_ms: int = Field(
        default=V3_EXECUTOR_RECOVERY_TIMEOUT_MS,
        ge=1000,
        le=120000,
        description=(
            "Global timeout for recovery operations in milliseconds. "
            "Prevents runaway recovery attempts."
        ),
    )
    v3_executor_circuit_breaker_threshold: int = Field(
        default=V3_EXECUTOR_CIRCUIT_BREAKER_THRESHOLD,
        ge=1,
        le=10,
        description=(
            "Circuit breaker threshold: after N consecutive failures, stop trying. "
            "Prevents cascading failures in execution."
        ),
    )

    # ------------------------------------------------------------------------
    # V3 Relevance Engine
    # ------------------------------------------------------------------------
    v3_relevance_primary_threshold: float = Field(
        default=V3_RELEVANCE_PRIMARY_THRESHOLD,
        ge=0.0,
        le=1.0,
        description=(
            "Score threshold for primary results (highly relevant). "
            "Results with score >= this are marked as primary."
        ),
    )
    v3_relevance_minimum_threshold: float = Field(
        default=V3_RELEVANCE_MINIMUM_THRESHOLD,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum score threshold for results. "
            "Results with score < this are filtered out completely."
        ),
    )

    # ------------------------------------------------------------------------
    # V3 Feedback Loop
    # ------------------------------------------------------------------------
    v3_feedback_loop_max_records: int = Field(
        default=V3_FEEDBACK_LOOP_MAX_RECORDS,
        ge=100,
        le=10000,
        description=(
            "Maximum recovery pattern records to keep in memory. "
            "Used for learning from past recovery strategies."
        ),
    )
    v3_feedback_loop_min_samples: int = Field(
        default=V3_FEEDBACK_LOOP_MIN_SAMPLES,
        ge=1,
        le=20,
        description=(
            "Minimum samples needed before suggesting a recovery strategy. "
            "Prevents premature strategy recommendations."
        ),
    )
    v3_feedback_loop_confidence_threshold: float = Field(
        default=V3_FEEDBACK_LOOP_CONFIDENCE_THRESHOLD,
        ge=0.0,
        le=1.0,
        description=(
            "Confidence threshold for strategy suggestions. "
            "Only suggest strategies with confidence >= this value."
        ),
    )

    # ------------------------------------------------------------------------
    # V3 Display
    # ------------------------------------------------------------------------
    v3_display_enabled: bool = Field(
        default=V3_DISPLAY_ENABLED,
        description=(
            "Enable v3 display formatting with conversational sandwich pattern. "
            "When False, falls back to legacy JSON + few-shot formatting."
        ),
    )
    v3_display_max_items_per_domain: int = Field(
        default=V3_DISPLAY_MAX_ITEMS_PER_DOMAIN,
        ge=1,
        le=20,
        description=(
            "Maximum items per domain in multi-domain responses. "
            "Limits visual clutter while showing most relevant results."
        ),
    )
    v3_display_viewport_mobile_max_width: int = Field(
        default=V3_DISPLAY_VIEWPORT_MOBILE_MAX_WIDTH,
        ge=320,
        le=768,
        description="Maximum viewport width considered as mobile (pixels). Above this = desktop.",
    )
    v3_display_show_action_buttons: bool = Field(
        default=V3_DISPLAY_SHOW_ACTION_BUTTONS,
        description=(
            "Show action buttons below HTML cards (reply, archive, directions, etc.). "
            "When False: action buttons are hidden in all HTML card components. "
            "Useful for production environments where actions aren't yet implemented."
        ),
    )

    # ------------------------------------------------------------------------
    # V3 Prompt Versions
    # ------------------------------------------------------------------------
    v3_router_prompt_version: str = Field(
        default=V3_ROUTER_PROMPT_VERSION,
        description="Prompt version for v3 router (for A/B testing and rollbacks).",
    )
    v3_smart_planner_prompt_version: str = Field(
        default=V3_SMART_PLANNER_PROMPT_VERSION,
        description="Prompt version for v3 smart planner (for A/B testing and rollbacks).",
    )

    # ------------------------------------------------------------------------
    # Interest Learning System (Proactive Notifications)
    # ------------------------------------------------------------------------
    # Interest Learning System configuration

    # Feature toggles
    interest_extraction_enabled: bool = Field(
        default=True,
        description=(
            "Enable interest extraction from conversations. "
            "Fire-and-forget LLM analysis runs after each response_node."
        ),
    )
    interest_notifications_enabled: bool = Field(
        default=True,
        description=(
            "Enable proactive interest notification scheduler. "
            "Runs every 15 minutes to send personalized content to users."
        ),
    )

    # ========================================================================
    # Knowledge Enrichment (Brave Search API)
    # ========================================================================
    # Enriches responses with up-to-date information from Brave Search.
    # Runs in parallel with other response_node operations (non-blocking).
    knowledge_enrichment_enabled: bool = Field(
        default=True,
        description=(
            "Enable knowledge enrichment via Brave Search API. "
            "Injects up-to-date web/news results into response context. "
            "Requires user to configure Brave Search connector with API key."
        ),
    )

    # Scheduler configuration
    interest_notification_interval_minutes: int = Field(
        default=INTEREST_NOTIFY_INTERVAL_MINUTES_DEFAULT,
        ge=5,
        le=60,
        description="Interval between notification scheduler runs (minutes).",
    )
    interest_notification_batch_size: int = Field(
        default=50,
        ge=10,
        le=200,
        description="Number of users to process per scheduler run.",
    )

    # Interest selection
    interest_top_percent: float = Field(
        default=0.2,
        ge=0.1,
        le=1.0,
        description=(
            "Top N% of interests to consider for notifications. "
            "0.2 = top 20% by effective weight. Ensures variety and relevance."
        ),
    )

    # Cooldowns
    interest_global_cooldown_hours: int = Field(
        default=2,
        ge=1,
        le=12,
        description="Minimum hours between any two interest notifications for a user.",
    )
    interest_per_topic_cooldown_hours: int = Field(
        default=24,
        ge=12,
        le=168,
        description="Minimum hours before re-notifying the same interest topic.",
    )
    interest_activity_cooldown_minutes: int = Field(
        default=5,
        ge=1,
        le=30,
        description=(
            "Don't send notifications if user sent a message within N minutes. "
            "Prevents interrupting active conversations."
        ),
    )

    # Weight evolution (Bayesian)
    interest_prior_alpha: int = Field(
        default=2,
        ge=1,
        le=10,
        description=(
            "Bayesian prior alpha (positive). "
            "Beta(α, β) prior: initial confidence = α/(α+β). "
            "Default: 2 for Beta(2,1) = 67% initial confidence."
        ),
    )
    interest_prior_beta: int = Field(
        default=1,
        ge=1,
        le=10,
        description=(
            "Bayesian prior beta (negative). "
            "Beta(α, β) prior: initial confidence = α/(α+β). "
            "Default: 1 for Beta(2,1) = 67% initial confidence."
        ),
    )
    interest_dormant_threshold_days: int = Field(
        default=30,
        ge=7,
        le=90,
        description=(
            "Days with weight below 0.5 before marking interest as dormant. "
            "Dormant interests are excluded from notifications."
        ),
    )
    interest_deletion_threshold_days: int = Field(
        default=90,
        ge=30,
        le=365,
        description="Days dormant before automatic deletion.",
    )
    interest_decay_rate_per_day: float = Field(
        default=0.01,
        ge=0.001,
        le=0.1,
        description=(
            "Weight decay rate per day without mention. "
            "0.01 = -1% per day. Interests must be reinforced to stay relevant."
        ),
    )

    # Content limits
    interest_content_max_length: int = Field(
        default=500,
        ge=100,
        le=2000,
        description="Maximum characters for notification content.",
    )
    interest_content_lookback_days: int = Field(
        default=30,
        ge=7,
        le=90,
        description="Lookback period in days for content deduplication.",
    )
    interest_dedup_search_limit: int = Field(
        default=20,
        ge=5,
        le=100,
        description="Maximum embeddings to check for similarity during deduplication.",
    )

    # Deduplication
    interest_dedup_similarity_threshold: float = Field(
        default=0.8,
        ge=0.5,
        le=0.95,
        description=(
            "Embedding similarity threshold for interest merging. "
            "Interests with similarity > threshold are consolidated."
        ),
    )
    interest_content_similarity_threshold: float = Field(
        default=0.92,
        ge=0.7,
        le=0.98,
        description=(
            "Similarity threshold for notification content deduplication. "
            "Content with cosine similarity >= threshold is considered duplicate. "
            "E5-small embeddings produce 0.7-0.85 for same-topic different-content, "
            "so values below 0.85 will block most new content. "
            "Recommended: 0.90-0.95."
        ),
    )

    # ========================================================================
    # Heartbeat Autonome (Proactive Notifications)
    # Feature flag: HEARTBEAT_ENABLED must be true in .env to register scheduler job.
    # Pattern identical to CHANNELS_ENABLED, MCP_ENABLED.
    # ========================================================================
    heartbeat_enabled: bool = Field(
        default=False,
        description="Global feature flag for heartbeat proactive notifications.",
    )

    # Scheduler
    heartbeat_notification_interval_minutes: int = Field(
        default=HEARTBEAT_NOTIFICATION_INTERVAL_MINUTES_DEFAULT,
        ge=10,
        le=120,
        description="Interval between heartbeat scheduler runs (minutes).",
    )
    heartbeat_notification_batch_size: int = Field(
        default=HEARTBEAT_NOTIFICATION_BATCH_SIZE_DEFAULT,
        ge=10,
        le=200,
        description="Number of users to process per heartbeat scheduler run.",
    )

    # Cooldowns
    heartbeat_global_cooldown_hours: int = Field(
        default=HEARTBEAT_GLOBAL_COOLDOWN_HOURS_DEFAULT,
        ge=1,
        le=12,
        description="Minimum hours between any two heartbeat notifications for a user.",
    )
    heartbeat_activity_cooldown_minutes: int = Field(
        default=HEARTBEAT_ACTIVITY_COOLDOWN_MINUTES_DEFAULT,
        ge=5,
        le=60,
        description=(
            "Don't send heartbeat if user sent a message within N minutes. "
            "Prevents interrupting active conversations."
        ),
    )

    # Cross-type proactive cooldown (applies to ALL proactive task types)
    proactive_cross_type_cooldown_minutes: int = Field(
        default=PROACTIVE_CROSS_TYPE_COOLDOWN_MINUTES_DEFAULT,
        ge=5,
        le=120,
        description=(
            "Minimum minutes between any two proactive notifications of different types "
            "(e.g., interest + heartbeat). Prevents notification bursts."
        ),
    )

    # LLM models
    heartbeat_decision_llm_provider: str = Field(
        default="openai",
        description="LLM provider for heartbeat decision phase (structured output).",
    )
    heartbeat_decision_llm_model: str = Field(
        default="gpt-5-mini",
        description="LLM model for heartbeat decision phase (reasoning-capable).",
    )
    heartbeat_message_llm_provider: str = Field(
        default="anthropic",
        description="LLM provider for heartbeat message generation phase.",
    )
    heartbeat_message_llm_model: str = Field(
        default="claude-sonnet-4-6",
        description="LLM model for heartbeat message generation (personality-aware).",
    )

    # Context aggregation
    heartbeat_context_calendar_hours: int = Field(
        default=HEARTBEAT_CONTEXT_CALENDAR_HOURS_DEFAULT,
        ge=1,
        le=24,
        description="Hours ahead to look for calendar events.",
    )
    heartbeat_context_tasks_days: int = Field(
        default=HEARTBEAT_CONTEXT_TASKS_DAYS_DEFAULT,
        ge=1,
        le=7,
        description="Days ahead to look for pending Google Tasks.",
    )
    heartbeat_context_memory_limit: int = Field(
        default=HEARTBEAT_CONTEXT_MEMORY_LIMIT_DEFAULT,
        ge=1,
        le=20,
        description="Maximum number of user memories to include in context.",
    )
    heartbeat_context_emails_max: int = Field(
        default=HEARTBEAT_CONTEXT_EMAILS_MAX_DEFAULT,
        ge=1,
        le=10,
        description="Maximum number of unread emails to include in heartbeat context.",
    )

    # Weather change detection thresholds
    heartbeat_weather_rain_threshold_high: float = Field(
        default=HEARTBEAT_WEATHER_RAIN_THRESHOLD_HIGH_DEFAULT,
        ge=0.3,
        le=0.9,
        description="Probability of precipitation above which rain is considered likely.",
    )
    heartbeat_weather_rain_threshold_low: float = Field(
        default=HEARTBEAT_WEATHER_RAIN_THRESHOLD_LOW_DEFAULT,
        ge=0.1,
        le=0.5,
        description="Probability of precipitation below which rain is considered clearing.",
    )
    heartbeat_weather_temp_change_threshold: float = Field(
        default=HEARTBEAT_WEATHER_TEMP_CHANGE_THRESHOLD_DEFAULT,
        ge=2.0,
        le=15.0,
        description="Temperature change in degrees C that triggers a notification.",
    )
    heartbeat_weather_wind_threshold: float = Field(
        default=HEARTBEAT_WEATHER_WIND_THRESHOLD_DEFAULT,
        ge=8.0,
        le=25.0,
        description="Wind speed in m/s above which a wind alert is triggered.",
    )

    # Early-exit optimization
    heartbeat_inactive_skip_days: int = Field(
        default=HEARTBEAT_INACTIVE_SKIP_DAYS_DEFAULT,
        ge=1,
        le=30,
        description=(
            "Skip heartbeat processing if user has not logged in for more than N days. "
            "Saves LLM tokens for inactive users."
        ),
    )

    @field_validator(
        "hitl_classifier_llm_reasoning_effort",
        "hitl_question_generator_llm_reasoning_effort",
        "hitl_plan_approval_question_llm_reasoning_effort",
        "planner_llm_reasoning_effort",
        "semantic_pivot_llm_reasoning_effort",
        "memory_extraction_llm_reasoning_effort",
        "memory_reference_resolution_llm_reasoning_effort",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, v: Any) -> Any:
        """
        Convert empty strings to None for reasoning_effort fields.

        Environment variables with empty values (VAR=) are read as "" (empty string).
        Since reasoning_effort accepts Literal[...] | None, we convert "" to None.

        This is a common pattern for optional enum/literal fields in pydantic-settings.

        Args:
            v: Raw value from environment or settings

        Returns:
            None if empty string, otherwise original value
        """
        if v == "" or v is None:
            return None
        return v

    # ========================================================================
    # Sub-Agents (F6 — Persistent Specialized Sub-Agents)
    # ========================================================================
    sub_agents_enabled: bool = Field(
        default=SUB_AGENTS_ENABLED_DEFAULT,
        description="Enable the sub-agents system (feature flag).",
    )
    subagent_max_per_user: int = Field(
        default=SUBAGENT_MAX_PER_USER_DEFAULT,
        ge=1,
        le=50,
        description="Maximum number of sub-agents per user.",
    )
    subagent_max_concurrent: int = Field(
        default=SUBAGENT_MAX_CONCURRENT_DEFAULT,
        ge=1,
        le=10,
        description="Maximum concurrent sub-agent executions per user.",
    )
    subagent_max_depth: int = Field(
        default=SUBAGENT_MAX_DEPTH_DEFAULT,
        ge=1,
        le=1,
        description="Maximum sub-agent nesting depth (V1: always 1).",
    )
    subagent_default_timeout: int = Field(
        default=SUBAGENT_DEFAULT_TIMEOUT_DEFAULT,
        ge=10,
        le=600,
        description="Default execution timeout in seconds.",
    )
    subagent_default_max_iterations: int = Field(
        default=SUBAGENT_DEFAULT_MAX_ITERATIONS_DEFAULT,
        ge=1,
        le=15,
        description="Default max LLM iterations per sub-agent execution.",
    )
    # Sub-agent LLM model is configured via Admin > LLM Configuration > Sub-Agent
    # (type "subagent" in LLM_TYPES_REGISTRY / LLM_DEFAULTS)
    subagent_max_token_budget: int = Field(
        default=SUBAGENT_MAX_TOKEN_BUDGET_DEFAULT,
        ge=1000,
        le=500000,
        description="Maximum tokens per single sub-agent execution.",
    )
    subagent_max_total_tokens_per_day: int = Field(
        default=SUBAGENT_MAX_TOTAL_TOKENS_PER_DAY_DEFAULT,
        ge=10000,
        le=5000000,
        description="Maximum total tokens for all sub-agent executions per user per day.",
    )
    subagent_max_consecutive_failures: int = Field(
        default=SUBAGENT_MAX_CONSECUTIVE_FAILURES_DEFAULT,
        ge=1,
        le=10,
        description="Auto-disable sub-agent after N consecutive failures.",
    )
    subagent_stale_recovery_interval_seconds: int = Field(
        default=SUBAGENT_STALE_RECOVERY_INTERVAL_DEFAULT,
        ge=30,
        le=600,
        description="Interval in seconds for the stale sub-agent recovery job.",
    )


# =============================================================================
# V3 CONFIGURATION MODELS (Pydantic BaseModel with validation)
# =============================================================================
# These models provide type-safe, validated configuration objects for v3 services.
# They are populated from AgentsSettings fields via factory functions.


class V3RoutingConfig(BaseModel):
    """
    Configuration for QueryAnalyzerService routing decisions.

    Controls how queries are routed between chat and planner based on semantic scores.
    """

    chat_semantic_threshold: float = Field(
        ge=0.0, le=1.0, description="Threshold below which queries route to chat"
    )
    high_semantic_threshold: float = Field(
        ge=0.0, le=1.0, description="Threshold above which queries route to planner"
    )
    min_confidence: float = Field(
        ge=0.0, le=1.0, description="Minimum confidence for planner route"
    )
    chat_override_threshold: float = Field(
        ge=0.0,
        le=1.0,
        description="Chat intent confidence for domain override (prevents false-positive domain matches)",
    )
    cross_domain_threshold: float = Field(
        ge=0.0,
        le=1.0,
        description="Minimum score for cross-domain reference detection (route to detected domain instead of source)",
    )

    model_config = ConfigDict(frozen=True)


class V3ExecutorConfig(BaseModel):
    """
    Configuration for AutonomousExecutor self-healing execution.

    Controls recovery behavior, circuit breaker, and timeout settings.
    """

    max_recovery_per_step: int = Field(ge=1, le=10, description="Max recoveries per step")
    max_total_recoveries: int = Field(ge=1, le=20, description="Max total recoveries")
    recovery_timeout_ms: int = Field(ge=1000, le=120000, description="Recovery timeout in ms")
    circuit_breaker_threshold: int = Field(ge=1, le=10, description="Circuit breaker threshold")

    model_config = ConfigDict(frozen=True)


class V3RelevanceConfig(BaseModel):
    """
    Configuration for RelevanceEngine result ranking.

    Controls thresholds for primary and minimum relevance scores.
    """

    primary_threshold: float = Field(
        ge=0.0, le=1.0, description="Threshold for primary (high relevance) results"
    )
    minimum_threshold: float = Field(
        ge=0.0, le=1.0, description="Minimum threshold (below = filtered out)"
    )

    model_config = ConfigDict(frozen=True)


class V3FeedbackLoopConfig(BaseModel):
    """
    Configuration for FeedbackLoopService learning from recovery patterns.

    Controls memory limits and confidence thresholds for strategy suggestions.
    """

    max_records: int = Field(ge=100, le=10000, description="Max recovery records to keep")
    min_samples: int = Field(ge=1, le=20, description="Min samples before suggesting")
    confidence_threshold: float = Field(
        ge=0.0, le=1.0, description="Confidence threshold for suggestions"
    )

    model_config = ConfigDict(frozen=True)


class V3DisplayConfig(BaseModel):
    """
    Configuration for display/formatting components.

    Controls response presentation: items per domain, viewport breakpoints.
    """

    enabled: bool = Field(default=True, description="Enable v3 display formatting")
    max_items_per_domain: int = Field(ge=1, le=20, description="Max items per domain")
    viewport_mobile_max_width: int = Field(
        ge=320, le=768, description="Mobile max width px (above=desktop)"
    )
    use_html_rendering: bool = Field(
        default=False,
        description="Use HTML rendering instead of Markdown",
    )
    show_action_buttons: bool = Field(
        default=True,
        description="Show action buttons below HTML cards (reply, archive, etc.)",
    )

    model_config = ConfigDict(frozen=True)


class V3PromptConfig(BaseModel):
    """
    Configuration for v3 prompt versions.

    Controls which prompt versions are used for v3 router and planner.
    """

    router_version: str = Field(description="V3 router prompt version")
    planner_version: str = Field(description="V3 smart planner prompt version")

    model_config = ConfigDict(frozen=True)


# =============================================================================
# V3 CONFIGURATION FACTORY FUNCTIONS
# =============================================================================
# These functions retrieve v3 configuration from settings and return validated models.
# They provide a clean API for v3 services to access their configuration.


def get_v3_routing_config() -> V3RoutingConfig:
    """
    Get V3 routing configuration for QueryAnalyzerService.

    Returns:
        V3RoutingConfig with validated thresholds from settings.
    """
    from src.core.config import get_settings

    settings = get_settings()
    return V3RoutingConfig(
        chat_semantic_threshold=settings.v3_routing_chat_semantic_threshold,
        high_semantic_threshold=settings.v3_routing_high_semantic_threshold,
        min_confidence=settings.v3_routing_min_confidence,
        chat_override_threshold=settings.v3_routing_chat_override_threshold,
        cross_domain_threshold=settings.v3_routing_cross_domain_threshold,
    )


def get_v3_executor_config() -> V3ExecutorConfig:
    """
    Get V3 executor configuration for AutonomousExecutor.

    Returns:
        V3ExecutorConfig with validated safeguards from settings.
    """
    from src.core.config import get_settings

    settings = get_settings()
    return V3ExecutorConfig(
        max_recovery_per_step=settings.v3_executor_max_recovery_per_step,
        max_total_recoveries=settings.v3_executor_max_total_recoveries,
        recovery_timeout_ms=settings.v3_executor_recovery_timeout_ms,
        circuit_breaker_threshold=settings.v3_executor_circuit_breaker_threshold,
    )


def get_v3_relevance_config() -> V3RelevanceConfig:
    """
    Get V3 relevance configuration for RelevanceEngine.

    Returns:
        V3RelevanceConfig with validated thresholds from settings.
    """
    from src.core.config import get_settings

    settings = get_settings()
    return V3RelevanceConfig(
        primary_threshold=settings.v3_relevance_primary_threshold,
        minimum_threshold=settings.v3_relevance_minimum_threshold,
    )


def get_v3_feedback_loop_config() -> V3FeedbackLoopConfig:
    """
    Get V3 feedback loop configuration for FeedbackLoopService.

    Returns:
        V3FeedbackLoopConfig with validated limits from settings.
    """
    from src.core.config import get_settings

    settings = get_settings()
    return V3FeedbackLoopConfig(
        max_records=settings.v3_feedback_loop_max_records,
        min_samples=settings.v3_feedback_loop_min_samples,
        confidence_threshold=settings.v3_feedback_loop_confidence_threshold,
    )


def get_v3_display_config() -> V3DisplayConfig:
    """
    Get V3 display configuration for display components.

    Returns:
        V3DisplayConfig with validated display settings.
    """
    from src.core.config import get_settings

    settings = get_settings()
    return V3DisplayConfig(
        enabled=settings.v3_display_enabled,
        max_items_per_domain=settings.v3_display_max_items_per_domain,
        viewport_mobile_max_width=settings.v3_display_viewport_mobile_max_width,
        use_html_rendering=True,  # Always enabled
        show_action_buttons=settings.v3_display_show_action_buttons,
    )


def get_v3_prompt_config() -> V3PromptConfig:
    """
    Get V3 prompt configuration for version management.

    Returns:
        V3PromptConfig with prompt versions from settings.
    """
    from src.core.config import get_settings

    settings = get_settings()
    return V3PromptConfig(
        router_version=settings.v3_router_prompt_version,
        planner_version=settings.v3_smart_planner_prompt_version,
    )


# Backwards compatibility alias for query_analyzer_service.py
get_routing_thresholds = get_v3_routing_config


def get_debug_thresholds() -> dict[str, dict[str, float | int | bool]]:
    """
    Get all scoring thresholds for debug panel display.

    Returns a flat dictionary organized by category for easy consumption
    by the debug panel frontend.

    Returns:
        Dictionary with all thresholds grouped by category:
        - intent_detection: Intent classifier thresholds
        - domain_selection: Domain selector thresholds (semantic + v3)
        - routing_decision: Router decision thresholds
        - tool_selection: Tool selector thresholds
        - context_resolution: Context reference thresholds
        - semantic_validation: Semantic validator thresholds
        - executor: Executor circuit breaker/recovery thresholds
        - relevance: Relevance engine thresholds
        - feedback_loop: Feedback loop thresholds
    """
    from src.core.config import get_settings

    settings = get_settings()

    return {
        "intent_detection": {
            "high_threshold": settings.semantic_intent_high_threshold,
            "fallback_threshold": settings.semantic_intent_fallback_threshold,
        },
        "domain_selection": {
            # Calibrated thresholds (used for actual selection)
            "softmax_temperature": settings.v3_domain_softmax_temperature,
            "primary_min": settings.v3_domain_calibrated_primary_min,
            "max_domains": settings.semantic_domain_max_domains,
        },
        "routing_decision": {
            "chat_semantic_threshold": settings.v3_routing_chat_semantic_threshold,
            "high_semantic_threshold": settings.v3_routing_high_semantic_threshold,
            "min_confidence": settings.v3_routing_min_confidence,
            "chat_override_threshold": settings.v3_routing_chat_override_threshold,
            "cross_domain_threshold": settings.v3_routing_cross_domain_threshold,
        },
        "tool_selection": {
            # Calibrated thresholds (used for actual selection)
            "softmax_temperature": settings.v3_tool_softmax_temperature,
            "primary_min": settings.v3_tool_calibrated_primary_min,
            "max_tools": settings.semantic_tool_selector_max_tools,
        },
        "context_resolution": {
            "confidence_threshold": settings.context_reference_confidence_threshold,
            "active_window_turns": settings.context_active_window_turns,
            "timeout_ms": settings.context_resolution_timeout_ms,
        },
        "semantic_validation": {
            "enabled": True,  # Always enabled
            "confidence_threshold": settings.semantic_validation_confidence_threshold,
            "timeout_seconds": settings.semantic_validation_timeout_seconds,
        },
        "executor": {
            "max_recovery_per_step": settings.v3_executor_max_recovery_per_step,
            "max_total_recoveries": settings.v3_executor_max_total_recoveries,
            "recovery_timeout_ms": settings.v3_executor_recovery_timeout_ms,
            "circuit_breaker_threshold": settings.v3_executor_circuit_breaker_threshold,
        },
        "relevance": {
            "primary_threshold": settings.v3_relevance_primary_threshold,
            "minimum_threshold": settings.v3_relevance_minimum_threshold,
        },
        "feedback_loop": {
            "max_records": settings.v3_feedback_loop_max_records,
            "min_samples": settings.v3_feedback_loop_min_samples,
            "confidence_threshold": settings.v3_feedback_loop_confidence_threshold,
        },
    }
