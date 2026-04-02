"""
LLM Configuration Constants — Single source of truth for LLM types and defaults.

LLM_TYPES_REGISTRY: Metadata for each LLM type (display name, category, capabilities).
LLM_DEFAULTS: Proven default values extracted from production .env (code = source of truth).

Resolution flow: LLM_DEFAULTS (code) → DB override (if exists) → Effective config.
Reset button restores these proven defaults.

Created: 2026-03-08
"""

from dataclasses import dataclass

from src.core.llm_agent_config import LLMAgentConfig

# --- LLM Type Metadata ---


@dataclass(frozen=True)
class LLMTypeMetadata:
    """Metadata for a single LLM type."""

    llm_type: str
    display_name: str
    category: str
    description_key: str
    required_capabilities: list[str]


# Categories for grouping in the admin UI
CATEGORY_PIPELINE = "pipeline"
CATEGORY_DOMAIN_AGENTS = "domain_agents"
CATEGORY_QUERY_RESPONSE = "query_response"
CATEGORY_HITL = "hitl"
CATEGORY_MEMORY = "memory"
CATEGORY_BACKGROUND = "background"
CATEGORY_SPECIALIZED = "specialized"

# Ordered category list for UI display
LLM_CATEGORIES_ORDER = [
    CATEGORY_PIPELINE,
    CATEGORY_DOMAIN_AGENTS,
    CATEGORY_QUERY_RESPONSE,
    CATEGORY_HITL,
    CATEGORY_MEMORY,
    CATEGORY_BACKGROUND,
    CATEGORY_SPECIALIZED,
]


LLM_TYPES_REGISTRY: dict[str, LLMTypeMetadata] = {
    # --- Pipeline (execution order) ---
    "semantic_pivot": LLMTypeMetadata(
        llm_type="semantic_pivot",
        display_name="Semantic Pivot",
        category=CATEGORY_PIPELINE,
        description_key="settings.admin.llmConfig.types.semantic_pivot",
        required_capabilities=[],
    ),
    "query_analyzer": LLMTypeMetadata(
        llm_type="query_analyzer",
        display_name="Query Analyzer",
        category=CATEGORY_PIPELINE,
        description_key="settings.admin.llmConfig.types.query_analyzer",
        required_capabilities=[],
    ),
    "router": LLMTypeMetadata(
        llm_type="router",
        display_name="Router",
        category=CATEGORY_PIPELINE,
        description_key="settings.admin.llmConfig.types.router",
        required_capabilities=["structured_output"],
    ),
    "planner": LLMTypeMetadata(
        llm_type="planner",
        display_name="Planner",
        category=CATEGORY_PIPELINE,
        description_key="settings.admin.llmConfig.types.planner",
        required_capabilities=["structured_output"],
    ),
    "semantic_validator": LLMTypeMetadata(
        llm_type="semantic_validator",
        display_name="Semantic Validator",
        category=CATEGORY_PIPELINE,
        description_key="settings.admin.llmConfig.types.semantic_validator",
        required_capabilities=[],
    ),
    "context_resolver": LLMTypeMetadata(
        llm_type="context_resolver",
        display_name="Context Resolver",
        category=CATEGORY_PIPELINE,
        description_key="settings.admin.llmConfig.types.context_resolver",
        required_capabilities=[],
    ),
    # --- Domain Agents ---
    "contacts_agent": LLMTypeMetadata(
        llm_type="contacts_agent",
        display_name="Contacts Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.contacts_agent",
        required_capabilities=["tools"],
    ),
    "emails_agent": LLMTypeMetadata(
        llm_type="emails_agent",
        display_name="Emails Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.emails_agent",
        required_capabilities=["tools"],
    ),
    "calendar_agent": LLMTypeMetadata(
        llm_type="calendar_agent",
        display_name="Calendar Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.calendar_agent",
        required_capabilities=["tools"],
    ),
    "drive_agent": LLMTypeMetadata(
        llm_type="drive_agent",
        display_name="Drive Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.drive_agent",
        required_capabilities=["tools"],
    ),
    "tasks_agent": LLMTypeMetadata(
        llm_type="tasks_agent",
        display_name="Tasks Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.tasks_agent",
        required_capabilities=["tools"],
    ),
    "weather_agent": LLMTypeMetadata(
        llm_type="weather_agent",
        display_name="Weather Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.weather_agent",
        required_capabilities=["tools"],
    ),
    "wikipedia_agent": LLMTypeMetadata(
        llm_type="wikipedia_agent",
        display_name="Wikipedia Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.wikipedia_agent",
        required_capabilities=["tools"],
    ),
    "perplexity_agent": LLMTypeMetadata(
        llm_type="perplexity_agent",
        display_name="Perplexity Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.perplexity_agent",
        required_capabilities=["tools"],
    ),
    "brave_agent": LLMTypeMetadata(
        llm_type="brave_agent",
        display_name="Brave Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.brave_agent",
        required_capabilities=["tools"],
    ),
    "web_search_agent": LLMTypeMetadata(
        llm_type="web_search_agent",
        display_name="Web Search Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.web_search_agent",
        required_capabilities=["tools"],
    ),
    "web_fetch_agent": LLMTypeMetadata(
        llm_type="web_fetch_agent",
        display_name="Web Fetch Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.web_fetch_agent",
        required_capabilities=["tools"],
    ),
    "browser_agent": LLMTypeMetadata(
        llm_type="browser_agent",
        display_name="Browser Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.browser_agent",
        required_capabilities=["tools"],
    ),
    "hue_agent": LLMTypeMetadata(
        llm_type="hue_agent",
        display_name="Hue Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.hue_agent",
        required_capabilities=["tools"],
    ),
    "places_agent": LLMTypeMetadata(
        llm_type="places_agent",
        display_name="Places Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.places_agent",
        required_capabilities=["tools"],
    ),
    "routes_agent": LLMTypeMetadata(
        llm_type="routes_agent",
        display_name="Routes Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.routes_agent",
        required_capabilities=["tools"],
    ),
    # --- Query & Response ---
    "query_agent": LLMTypeMetadata(
        llm_type="query_agent",
        display_name="Query Agent",
        category=CATEGORY_QUERY_RESPONSE,
        description_key="settings.admin.llmConfig.types.query_agent",
        required_capabilities=["tools"],
    ),
    "response": LLMTypeMetadata(
        llm_type="response",
        display_name="Response",
        category=CATEGORY_QUERY_RESPONSE,
        description_key="settings.admin.llmConfig.types.response",
        required_capabilities=[],
    ),
    # --- HITL ---
    "hitl_classifier": LLMTypeMetadata(
        llm_type="hitl_classifier",
        display_name="HITL Classifier",
        category=CATEGORY_HITL,
        description_key="settings.admin.llmConfig.types.hitl_classifier",
        required_capabilities=["structured_output"],
    ),
    "hitl_question_generator": LLMTypeMetadata(
        llm_type="hitl_question_generator",
        display_name="HITL Question Generator",
        category=CATEGORY_HITL,
        description_key="settings.admin.llmConfig.types.hitl_question_generator",
        required_capabilities=[],
    ),
    "hitl_plan_approval_question_generator": LLMTypeMetadata(
        llm_type="hitl_plan_approval_question_generator",
        display_name="HITL Plan Approval",
        category=CATEGORY_HITL,
        description_key="settings.admin.llmConfig.types.hitl_plan_approval_question_generator",
        required_capabilities=[],
    ),
    # --- Memory ---
    "memory_extraction": LLMTypeMetadata(
        llm_type="memory_extraction",
        display_name="Memory Extraction",
        category=CATEGORY_MEMORY,
        description_key="settings.admin.llmConfig.types.memory_extraction",
        required_capabilities=[],
    ),
    "memory_reference_resolution": LLMTypeMetadata(
        llm_type="memory_reference_resolution",
        display_name="Memory Reference Resolution",
        category=CATEGORY_MEMORY,
        description_key="settings.admin.llmConfig.types.memory_reference_resolution",
        required_capabilities=[],
    ),
    # --- Background ---
    "interest_extraction": LLMTypeMetadata(
        llm_type="interest_extraction",
        display_name="Interest Extraction",
        category=CATEGORY_BACKGROUND,
        description_key="settings.admin.llmConfig.types.interest_extraction",
        required_capabilities=[],
    ),
    "interest_content": LLMTypeMetadata(
        llm_type="interest_content",
        display_name="Interest Content",
        category=CATEGORY_BACKGROUND,
        description_key="settings.admin.llmConfig.types.interest_content",
        required_capabilities=[],
    ),
    "heartbeat_decision": LLMTypeMetadata(
        llm_type="heartbeat_decision",
        display_name="Heartbeat Decision",
        category=CATEGORY_BACKGROUND,
        description_key="settings.admin.llmConfig.types.heartbeat_decision",
        required_capabilities=["structured_output"],
    ),
    "heartbeat_message": LLMTypeMetadata(
        llm_type="heartbeat_message",
        display_name="Heartbeat Message",
        category=CATEGORY_BACKGROUND,
        description_key="settings.admin.llmConfig.types.heartbeat_message",
        required_capabilities=[],
    ),
    "broadcast_translator": LLMTypeMetadata(
        llm_type="broadcast_translator",
        display_name="Broadcast Translator",
        category=CATEGORY_BACKGROUND,
        description_key="settings.admin.llmConfig.types.broadcast_translator",
        required_capabilities=[],
    ),
    # --- Specialized ---
    "voice_comment": LLMTypeMetadata(
        llm_type="voice_comment",
        display_name="Voice Comment",
        category=CATEGORY_SPECIALIZED,
        description_key="settings.admin.llmConfig.types.voice_comment",
        required_capabilities=[],
    ),
    "mcp_description": LLMTypeMetadata(
        llm_type="mcp_description",
        display_name="MCP Description",
        category=CATEGORY_SPECIALIZED,
        description_key="settings.admin.llmConfig.types.mcp_description",
        required_capabilities=[],
    ),
    "mcp_excalidraw": LLMTypeMetadata(
        llm_type="mcp_excalidraw",
        display_name="MCP Excalidraw",
        category=CATEGORY_SPECIALIZED,
        description_key="settings.admin.llmConfig.types.mcp_excalidraw",
        required_capabilities=[],
    ),
    "vision_analysis": LLMTypeMetadata(
        llm_type="vision_analysis",
        display_name="Vision Analysis",
        category=CATEGORY_SPECIALIZED,
        description_key="settings.admin.llmConfig.types.vision_analysis",
        required_capabilities=["vision"],
    ),
    "skill_description_translator": LLMTypeMetadata(
        llm_type="skill_description_translator",
        display_name="Skill Description Translator",
        category=CATEGORY_SPECIALIZED,
        description_key="settings.admin.llmConfig.types.skill_description_translator",
        required_capabilities=[],
    ),
    "evaluator": LLMTypeMetadata(
        llm_type="evaluator",
        display_name="Evaluator (LLM-as-Judge)",
        category=CATEGORY_SPECIALIZED,
        description_key="settings.admin.llmConfig.types.evaluator",
        required_capabilities=["structured_output"],
    ),
    "compaction": LLMTypeMetadata(
        llm_type="compaction",
        display_name="Context Compaction",
        category=CATEGORY_PIPELINE,
        description_key="settings.admin.llmConfig.types.compaction",
        required_capabilities=[],
    ),
    "subagent": LLMTypeMetadata(
        llm_type="subagent",
        display_name="Sub-Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.subagent",
        required_capabilities=["tools"],
    ),
    "journal_extraction": LLMTypeMetadata(
        llm_type="journal_extraction",
        display_name="Journal Extraction",
        category=CATEGORY_BACKGROUND,
        description_key="settings.admin.llmConfig.types.journal_extraction",
        required_capabilities=[],
    ),
    "journal_consolidation": LLMTypeMetadata(
        llm_type="journal_consolidation",
        display_name="Journal Consolidation",
        category=CATEGORY_BACKGROUND,
        description_key="settings.admin.llmConfig.types.journal_consolidation",
        required_capabilities=[],
    ),
    # ADR-062: Initiative Phase + MCP ReAct
    "initiative": LLMTypeMetadata(
        llm_type="initiative",
        display_name="Initiative Node",
        category=CATEGORY_PIPELINE,
        description_key="settings.admin.llmConfig.types.initiative",
        required_capabilities=["structured_output"],
    ),
    "mcp_react_agent": LLMTypeMetadata(
        llm_type="mcp_react_agent",
        display_name="MCP Iterative (ReAct)",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.mcp_react_agent",
        required_capabilities=["tool_calling"],
    ),
    # Psyche Engine (evolution)
    "psyche_summary": LLMTypeMetadata(
        llm_type="psyche_summary",
        display_name="Psyche Summary",
        category=CATEGORY_BACKGROUND,
        description_key="settings.admin.llmConfig.types.psyche_summary",
        required_capabilities=[],
    ),
    # AI Image Generation (evolution)
    "image_generation": LLMTypeMetadata(
        llm_type="image_generation",
        display_name="Image Generation",
        category=CATEGORY_SPECIALIZED,
        description_key="settings.admin.llmConfig.types.image_generation",
        required_capabilities=[],  # Images API, not chat completions
    ),
}


# --- Proven Defaults (extracted from production .env) ---
# These values are the optimized baseline for the application.
# The "Reset" button in the admin UI restores these values.
# Updated: 2026-03-29 — Merged from production DB overrides into code defaults.
# Strategy: nano (domain agents), mini (routing), sonnet (extraction), qwen (planning), gpt-5.4 (advanced)


LLM_DEFAULTS: dict[str, LLMAgentConfig] = {
    # --- Pipeline ---
    "compaction": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=4000,
    ),
    "context_resolver": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
    ),
    "initiative": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=5000,
    ),
    "planner": LLMAgentConfig(
        provider="qwen",
        model="qwen3.5-plus",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=10000,
        timeout_seconds=30.0,
        reasoning_effort="low",
    ),
    "query_analyzer": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=5000,
    ),
    "router": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
    ),
    "semantic_pivot": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=5000,
    ),
    "semantic_validator": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
    ),
    # --- Domain Agents ---
    "brave_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
    ),
    "browser_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-5.4",
        temperature=0.2,
        top_p=0.9,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=8000,
        reasoning_effort="low",
    ),
    "calendar_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
    ),
    "contacts_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
    ),
    "drive_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
    ),
    "emails_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
    ),
    "hue_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
    ),
    "mcp_react_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-5.4",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=16000,
        reasoning_effort="low",
    ),
    "perplexity_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=3000,
    ),
    "places_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
    ),
    "routes_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
    ),
    "subagent": LLMAgentConfig(
        provider="openai",
        model="gpt-5.4",
        temperature=0.5,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=8000,
        reasoning_effort="low",
    ),
    "tasks_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
    ),
    "weather_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
    ),
    "web_fetch_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=3000,
    ),
    "web_search_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=4000,
    ),
    "wikipedia_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
    ),
    # --- Query & Response ---
    "query_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=5000,
    ),
    "response": LLMAgentConfig(
        provider="anthropic",
        model="claude-sonnet-4-6",
        temperature=0.7,
        top_p=1.0,
        frequency_penalty=0.1,
        presence_penalty=0.0,
        max_tokens=5000,
        reasoning_effort="low",
    ),
    # --- HITL ---
    "hitl_classifier": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=300,
    ),
    "hitl_plan_approval_question_generator": LLMAgentConfig(
        provider="anthropic",
        model="claude-sonnet-4-6",
        temperature=0.5,
        top_p=1.0,
        frequency_penalty=0.7,
        presence_penalty=0.3,
        max_tokens=500,
        reasoning_effort="low",
    ),
    "hitl_question_generator": LLMAgentConfig(
        provider="anthropic",
        model="claude-sonnet-4-6",
        temperature=0.5,
        top_p=1.0,
        frequency_penalty=0.7,
        presence_penalty=0.3,
        max_tokens=500,
        reasoning_effort="low",
    ),
    # --- Memory ---
    "memory_extraction": LLMAgentConfig(
        provider="anthropic",
        model="claude-sonnet-4-6",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        reasoning_effort="low",
    ),
    "memory_reference_resolution": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=500,
    ),
    # --- Background ---
    "broadcast_translator": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=500,
    ),
    "heartbeat_decision": LLMAgentConfig(
        provider="qwen",
        model="qwen3.5-plus",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
        reasoning_effort="none",
    ),
    "heartbeat_message": LLMAgentConfig(
        provider="anthropic",
        model="claude-sonnet-4-6",
        temperature=0.7,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=500,
        reasoning_effort="low",
    ),
    "interest_content": LLMAgentConfig(
        provider="anthropic",
        model="claude-sonnet-4-6",
        temperature=0.7,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        reasoning_effort="low",
    ),
    "interest_extraction": LLMAgentConfig(
        provider="anthropic",
        model="claude-sonnet-4-6",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=500,
        reasoning_effort="low",
    ),
    "journal_consolidation": LLMAgentConfig(
        provider="qwen",
        model="qwen3.5-plus",
        temperature=0.5,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=10000,
        reasoning_effort="none",
    ),
    "journal_extraction": LLMAgentConfig(
        provider="anthropic",
        model="claude-sonnet-4-6",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=5000,
        reasoning_effort="low",
    ),
    "psyche_summary": LLMAgentConfig(
        provider="anthropic",
        model="claude-sonnet-4-6",
        temperature=0.7,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=200,
        reasoning_effort="low",
    ),
    # --- Specialized ---
    "evaluator": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
    ),
    "image_generation": LLMAgentConfig(
        provider="openai",
        model="gpt-image-1",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1,
    ),
    "mcp_description": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=300,
    ),
    "mcp_excalidraw": LLMAgentConfig(
        provider="anthropic",
        model="claude-opus-4-6",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=20000,
        timeout_seconds=60.0,
        reasoning_effort="medium",
    ),
    "skill_description_translator": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
    ),
    "vision_analysis": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=0.5,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=4096,
    ),
    "voice_comment": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=0.7,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=500,
    ),
}

# --- Image Generation Models ---
# These are NOT chat models — they use the provider's Images API.
# Listed separately from FALLBACK_PROFILES (which only contains chat models).
# Used by the admin LLM Config UI to populate the model dropdown for image_generation.
IMAGE_GENERATION_MODELS: dict[str, list[str]] = {
    "openai": [
        "gpt-image-1.5",
        "gpt-image-1",
        "gpt-image-1-mini",
    ],
}


# Validate that REGISTRY and DEFAULTS are synchronized
assert set(LLM_TYPES_REGISTRY.keys()) == set(LLM_DEFAULTS.keys()), (
    f"LLM_TYPES_REGISTRY and LLM_DEFAULTS keys mismatch: "
    f"registry_only={set(LLM_TYPES_REGISTRY.keys()) - set(LLM_DEFAULTS.keys())}, "
    f"defaults_only={set(LLM_DEFAULTS.keys()) - set(LLM_TYPES_REGISTRY.keys())}"
)


# Known LLM providers with display names
LLM_PROVIDERS: dict[str, str] = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "deepseek": "DeepSeek",
    "perplexity": "Perplexity",
    "ollama": "Ollama",
    "gemini": "Google Gemini",
    "qwen": "Qwen",
}
