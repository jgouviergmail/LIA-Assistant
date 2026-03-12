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
}


# --- Proven Defaults (extracted from production .env) ---
# These values are the optimized baseline for the application.
# The "Reset" button in the admin UI restores these values.


LLM_DEFAULTS: dict[str, LLMAgentConfig] = {
    # --- Pipeline ---
    "semantic_pivot": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=5000,
        reasoning_effort="minimal",
    ),
    "query_analyzer": LLMAgentConfig(
        provider="openai",
        model="gpt-5.1",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=5000,
        reasoning_effort="low",
    ),
    "router": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        reasoning_effort="minimal",
    ),
    "planner": LLMAgentConfig(
        provider="openai",
        model="gpt-5.1",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=20000,
        timeout_seconds=30,
        reasoning_effort="low",
    ),
    "semantic_validator": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        reasoning_effort="minimal",
    ),
    "context_resolver": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        reasoning_effort="minimal",
    ),
    # --- Domain Agents ---
    "contacts_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-5-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
        reasoning_effort="minimal",
    ),
    "emails_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-5-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
        reasoning_effort="minimal",
    ),
    "calendar_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-5-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
        reasoning_effort="minimal",
    ),
    "drive_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-5-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
        reasoning_effort="minimal",
    ),
    "tasks_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-5-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
        reasoning_effort="minimal",
    ),
    "weather_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-5-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        reasoning_effort="minimal",
    ),
    "wikipedia_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-5-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
        reasoning_effort="minimal",
    ),
    "perplexity_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-5-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=3000,
        reasoning_effort="minimal",
    ),
    "brave_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-5-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
        reasoning_effort="minimal",
    ),
    "web_search_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-5-nano",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=4000,
        reasoning_effort="minimal",
    ),
    "web_fetch_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-5-nano",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=3000,
        reasoning_effort="minimal",
    ),
    "places_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-5-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
        reasoning_effort="minimal",
    ),
    "routes_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-5-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
        reasoning_effort="minimal",
    ),
    # --- Query & Response ---
    "query_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=5000,
        reasoning_effort="minimal",
    ),
    "response": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=0.5,
        top_p=1.0,
        frequency_penalty=0.1,
        presence_penalty=0.0,
        max_tokens=5000,
    ),
    # --- HITL ---
    "hitl_classifier": LLMAgentConfig(
        provider="openai",
        model="gpt-5-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=300,
        reasoning_effort="minimal",
    ),
    "hitl_question_generator": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.5,
        top_p=1.0,
        frequency_penalty=0.7,
        presence_penalty=0.3,
        max_tokens=500,
        reasoning_effort="minimal",
    ),
    "hitl_plan_approval_question_generator": LLMAgentConfig(
        provider="openai",
        model="gpt-5-nano",
        temperature=0.5,
        top_p=1.0,
        frequency_penalty=0.7,
        presence_penalty=0.3,
        max_tokens=500,
        reasoning_effort="minimal",
    ),
    # --- Memory ---
    "memory_extraction": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        reasoning_effort="minimal",
    ),
    "memory_reference_resolution": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=500,
        reasoning_effort="minimal",
    ),
    # --- Background ---
    "interest_extraction": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=500,
        reasoning_effort="minimal",
    ),
    "interest_content": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.7,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        reasoning_effort="minimal",
    ),
    "heartbeat_decision": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
    ),
    "heartbeat_message": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=0.7,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=500,
    ),
    "broadcast_translator": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=500,
    ),
    # --- Specialized ---
    "voice_comment": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.7,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=500,
        reasoning_effort="minimal",
    ),
    "mcp_description": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=300,
        reasoning_effort="minimal",
    ),
    "mcp_excalidraw": LLMAgentConfig(
        provider="anthropic",
        model="claude-opus-4-6",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=20000,
        timeout_seconds=60,
    ),
    "vision_analysis": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1",
        temperature=0.5,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=4096,
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
    "evaluator": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
    ),
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
}
