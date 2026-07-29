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
from src.core.reasoning_types import (
    ReasoningEffortEnum,
    ReasoningEffortToggleBudget,
)
from src.domains.llm.models import LLMModelKindEnum

# --- LLM Type Metadata ---


# Power tier constants — visual indicator of the computational weight of an LLM slot.
# Assigned per LLM type (not per model) so admins can see at a glance which slots
# require expensive models vs. lightweight ones.
POWER_TIER_CRITICAL = "critical"  # Red pastel — needs the most powerful model available
POWER_TIER_HIGH = "high"  # Orange pastel — needs a strong reasoning model
POWER_TIER_MEDIUM = "medium"  # Blue pastel — moderate capability sufficient
POWER_TIER_LOW = "low"  # Green pastel — lightweight model sufficient
# None → no visual indicator (special-purpose slots like image_generation)


@dataclass(frozen=True)
class LLMTypeMetadata:
    """Metadata for a single LLM type."""

    llm_type: str
    display_name: str
    category: str
    description_key: str
    required_capabilities: list[str]
    power_tier: str | None = None
    # The kind of model this LLM type expects. Drives the
    # ``GET /llm-config/metadata?kinds=`` query param sent by the frontend
    # when populating the model dropdown for this type. Defaults to ``chat``
    # (overwhelming majority); ``image_generation`` overrides to ``image``.
    required_kind: LLMModelKindEnum = LLMModelKindEnum.chat


# Categories for grouping in the admin UI
CATEGORY_PIPELINE = "pipeline"
CATEGORY_DOMAIN_AGENTS = "domain_agents"
CATEGORY_QUERY_RESPONSE = "query_response"
CATEGORY_HITL = "hitl"
CATEGORY_MEMORY = "memory"
CATEGORY_BACKGROUND = "background"
CATEGORY_BRIEFING = "briefing"
CATEGORY_SPECIALIZED = "specialized"

# Ordered category list for UI display
LLM_CATEGORIES_ORDER = [
    CATEGORY_PIPELINE,
    CATEGORY_DOMAIN_AGENTS,
    CATEGORY_QUERY_RESPONSE,
    CATEGORY_HITL,
    CATEGORY_MEMORY,
    CATEGORY_BACKGROUND,
    CATEGORY_BRIEFING,
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
        power_tier=POWER_TIER_MEDIUM,
    ),
    "query_analyzer": LLMTypeMetadata(
        llm_type="query_analyzer",
        display_name="Query Analyzer",
        category=CATEGORY_PIPELINE,
        description_key="settings.admin.llmConfig.types.query_analyzer",
        required_capabilities=[],
        power_tier=POWER_TIER_HIGH,
    ),
    "router": LLMTypeMetadata(
        llm_type="router",
        display_name="Router",
        category=CATEGORY_PIPELINE,
        description_key="settings.admin.llmConfig.types.router",
        required_capabilities=["structured_output"],
        power_tier=POWER_TIER_MEDIUM,
    ),
    "planner": LLMTypeMetadata(
        llm_type="planner",
        display_name="Planner",
        category=CATEGORY_PIPELINE,
        description_key="settings.admin.llmConfig.types.planner",
        required_capabilities=["structured_output"],
        power_tier=POWER_TIER_HIGH,
    ),
    "semantic_validator": LLMTypeMetadata(
        llm_type="semantic_validator",
        display_name="Semantic Validator",
        category=CATEGORY_PIPELINE,
        description_key="settings.admin.llmConfig.types.semantic_validator",
        required_capabilities=[],
        power_tier=POWER_TIER_MEDIUM,
    ),
    "context_resolver": LLMTypeMetadata(
        llm_type="context_resolver",
        display_name="Context Resolver",
        category=CATEGORY_PIPELINE,
        description_key="settings.admin.llmConfig.types.context_resolver",
        required_capabilities=[],
        power_tier=POWER_TIER_MEDIUM,
    ),
    # --- Domain Agents ---
    "contacts_agent": LLMTypeMetadata(
        llm_type="contacts_agent",
        display_name="Contacts Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.contacts_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_LOW,
    ),
    "emails_agent": LLMTypeMetadata(
        llm_type="emails_agent",
        display_name="Emails Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.emails_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_LOW,
    ),
    "calendar_agent": LLMTypeMetadata(
        llm_type="calendar_agent",
        display_name="Calendar Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.calendar_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_LOW,
    ),
    "drive_agent": LLMTypeMetadata(
        llm_type="drive_agent",
        display_name="Drive Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.drive_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_LOW,
    ),
    "tasks_agent": LLMTypeMetadata(
        llm_type="tasks_agent",
        display_name="Tasks Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.tasks_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_LOW,
    ),
    "weather_agent": LLMTypeMetadata(
        llm_type="weather_agent",
        display_name="Weather Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.weather_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_LOW,
    ),
    "wikipedia_agent": LLMTypeMetadata(
        llm_type="wikipedia_agent",
        display_name="Wikipedia Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.wikipedia_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_LOW,
    ),
    "perplexity_agent": LLMTypeMetadata(
        llm_type="perplexity_agent",
        display_name="Perplexity Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.perplexity_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_LOW,
    ),
    "brave_agent": LLMTypeMetadata(
        llm_type="brave_agent",
        display_name="Brave Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.brave_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_LOW,
    ),
    "web_search_agent": LLMTypeMetadata(
        llm_type="web_search_agent",
        display_name="Web Search Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.web_search_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_LOW,
    ),
    "web_fetch_agent": LLMTypeMetadata(
        llm_type="web_fetch_agent",
        display_name="Web Fetch Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.web_fetch_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_LOW,
    ),
    "browser_agent": LLMTypeMetadata(
        llm_type="browser_agent",
        display_name="Browser Agent (ReAct)",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.browser_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_HIGH,
    ),
    "hue_agent": LLMTypeMetadata(
        llm_type="hue_agent",
        display_name="Hue Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.hue_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_LOW,
    ),
    "places_agent": LLMTypeMetadata(
        llm_type="places_agent",
        display_name="Places Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.places_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_LOW,
    ),
    "routes_agent": LLMTypeMetadata(
        llm_type="routes_agent",
        display_name="Routes Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.routes_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_LOW,
    ),
    "health_agent": LLMTypeMetadata(
        llm_type="health_agent",
        display_name="Health Metrics Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.health_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_LOW,
    ),
    "telephony_agent": LLMTypeMetadata(
        llm_type="telephony_agent",
        display_name="Telephony Agent",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.telephony_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_LOW,
    ),
    # --- Query & Response ---
    "query_agent": LLMTypeMetadata(
        llm_type="query_agent",
        display_name="Query Agent",
        category=CATEGORY_QUERY_RESPONSE,
        description_key="settings.admin.llmConfig.types.query_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_HIGH,
    ),
    "response": LLMTypeMetadata(
        llm_type="response",
        display_name="Response",
        category=CATEGORY_QUERY_RESPONSE,
        description_key="settings.admin.llmConfig.types.response",
        required_capabilities=[],
        power_tier=POWER_TIER_HIGH,
    ),
    # --- HITL ---
    "hitl_classifier": LLMTypeMetadata(
        llm_type="hitl_classifier",
        display_name="HITL Classifier",
        category=CATEGORY_HITL,
        description_key="settings.admin.llmConfig.types.hitl_classifier",
        required_capabilities=["structured_output"],
        power_tier=POWER_TIER_LOW,
    ),
    "hitl_question_generator": LLMTypeMetadata(
        llm_type="hitl_question_generator",
        display_name="HITL Question Generator",
        category=CATEGORY_HITL,
        description_key="settings.admin.llmConfig.types.hitl_question_generator",
        required_capabilities=[],
        power_tier=POWER_TIER_HIGH,
    ),
    "hitl_plan_approval_question_generator": LLMTypeMetadata(
        llm_type="hitl_plan_approval_question_generator",
        display_name="HITL Plan Approval",
        category=CATEGORY_HITL,
        description_key="settings.admin.llmConfig.types.hitl_plan_approval_question_generator",
        required_capabilities=[],
        power_tier=POWER_TIER_HIGH,
    ),
    # --- Memory ---
    "memory_extraction": LLMTypeMetadata(
        llm_type="memory_extraction",
        display_name="Memory Extraction",
        category=CATEGORY_MEMORY,
        description_key="settings.admin.llmConfig.types.memory_extraction",
        required_capabilities=[],
        power_tier=POWER_TIER_MEDIUM,
    ),
    "memory_reference_extraction": LLMTypeMetadata(
        llm_type="memory_reference_extraction",
        display_name="Memory Reference Extraction",
        category=CATEGORY_MEMORY,
        description_key="settings.admin.llmConfig.types.memory_reference_extraction",
        required_capabilities=[],
        power_tier=POWER_TIER_LOW,
    ),
    "open_loop_extraction": LLMTypeMetadata(
        llm_type="open_loop_extraction",
        display_name="Open Loop Extraction",
        category=CATEGORY_MEMORY,
        description_key="settings.admin.llmConfig.types.open_loop_extraction",
        required_capabilities=[],
        power_tier=POWER_TIER_LOW,
    ),
    "memory_reference_resolution": LLMTypeMetadata(
        llm_type="memory_reference_resolution",
        display_name="Memory Reference Resolution",
        category=CATEGORY_MEMORY,
        description_key="settings.admin.llmConfig.types.memory_reference_resolution",
        required_capabilities=[],
        power_tier=POWER_TIER_MEDIUM,
    ),
    # --- Background ---
    "interest_extraction": LLMTypeMetadata(
        llm_type="interest_extraction",
        display_name="Interest Extraction",
        category=CATEGORY_BACKGROUND,
        description_key="settings.admin.llmConfig.types.interest_extraction",
        required_capabilities=[],
        power_tier=POWER_TIER_MEDIUM,
    ),
    "interest_content": LLMTypeMetadata(
        llm_type="interest_content",
        display_name="Interest Content",
        category=CATEGORY_BACKGROUND,
        description_key="settings.admin.llmConfig.types.interest_content",
        required_capabilities=[],
        power_tier=POWER_TIER_HIGH,
    ),
    "heartbeat_decision": LLMTypeMetadata(
        llm_type="heartbeat_decision",
        display_name="Heartbeat Decision",
        category=CATEGORY_BACKGROUND,
        description_key="settings.admin.llmConfig.types.heartbeat_decision",
        required_capabilities=["structured_output"],
        power_tier=POWER_TIER_HIGH,
    ),
    "heartbeat_message": LLMTypeMetadata(
        llm_type="heartbeat_message",
        display_name="Heartbeat Message",
        category=CATEGORY_BACKGROUND,
        description_key="settings.admin.llmConfig.types.heartbeat_message",
        required_capabilities=[],
        power_tier=POWER_TIER_HIGH,
    ),
    "broadcast_translator": LLMTypeMetadata(
        llm_type="broadcast_translator",
        display_name="Broadcast Translator",
        category=CATEGORY_BACKGROUND,
        description_key="settings.admin.llmConfig.types.broadcast_translator",
        required_capabilities=[],
        power_tier=POWER_TIER_MEDIUM,
    ),
    "personality_translation": LLMTypeMetadata(
        llm_type="personality_translation",
        display_name="Personality Translator",
        category=CATEGORY_BACKGROUND,
        description_key="settings.admin.llmConfig.types.personality_translation",
        required_capabilities=[],
        power_tier=POWER_TIER_LOW,
    ),
    # --- Briefing (Today dashboard) ---
    "briefing": LLMTypeMetadata(
        llm_type="briefing",
        display_name="Briefing (Greeting + Synthesis)",
        category=CATEGORY_BRIEFING,
        description_key="settings.admin.llmConfig.types.briefing",
        required_capabilities=[],
        power_tier=POWER_TIER_LOW,
    ),
    "telephony_synthesis": LLMTypeMetadata(
        llm_type="telephony_synthesis",
        display_name="Telephony Return Synthesis",
        category=CATEGORY_SPECIALIZED,
        description_key="settings.admin.llmConfig.types.telephony_synthesis",
        required_capabilities=[],
        power_tier=POWER_TIER_LOW,
    ),
    # --- Specialized ---
    "voice_comment": LLMTypeMetadata(
        llm_type="voice_comment",
        display_name="Voice Comment",
        category=CATEGORY_SPECIALIZED,
        description_key="settings.admin.llmConfig.types.voice_comment",
        required_capabilities=[],
        power_tier=POWER_TIER_MEDIUM,
    ),
    "mcp_description": LLMTypeMetadata(
        llm_type="mcp_description",
        display_name="MCP Description",
        category=CATEGORY_SPECIALIZED,
        description_key="settings.admin.llmConfig.types.mcp_description",
        required_capabilities=[],
        power_tier=POWER_TIER_MEDIUM,
    ),
    "mcp_app_react_agent": LLMTypeMetadata(
        llm_type="mcp_app_react_agent",
        display_name="MCP App (ReAct)",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.mcp_app_react_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_CRITICAL,
    ),
    "vision_analysis": LLMTypeMetadata(
        llm_type="vision_analysis",
        display_name="Vision Analysis",
        category=CATEGORY_SPECIALIZED,
        description_key="settings.admin.llmConfig.types.vision_analysis",
        required_capabilities=["vision"],
        power_tier=POWER_TIER_MEDIUM,
    ),
    "skill_description_translator": LLMTypeMetadata(
        llm_type="skill_description_translator",
        display_name="Skill Description Translator",
        category=CATEGORY_SPECIALIZED,
        description_key="settings.admin.llmConfig.types.skill_description_translator",
        required_capabilities=[],
        power_tier=POWER_TIER_MEDIUM,
    ),
    "evaluator": LLMTypeMetadata(
        llm_type="evaluator",
        display_name="Evaluator (LLM-as-Judge)",
        category=CATEGORY_SPECIALIZED,
        description_key="settings.admin.llmConfig.types.evaluator",
        required_capabilities=["structured_output"],
        power_tier=POWER_TIER_MEDIUM,
    ),
    "compaction": LLMTypeMetadata(
        llm_type="compaction",
        display_name="Context Compaction",
        category=CATEGORY_PIPELINE,
        description_key="settings.admin.llmConfig.types.compaction",
        required_capabilities=[],
        power_tier=POWER_TIER_HIGH,
    ),
    "subagent": LLMTypeMetadata(
        llm_type="subagent",
        # ADR-083: drives a scoped ReAct loop (read-only tools, tight iteration
        # budget) — mirrors the "MCP Iterative (ReAct)" naming of mcp_react_agent.
        # llm_type id stays "subagent" — DB rows, config overrides, code refs
        # (get_llm("subagent")) are unaffected by this display change.
        display_name="Sub-Agent (ReAct)",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.subagent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_HIGH,
    ),
    "journal_extraction": LLMTypeMetadata(
        llm_type="journal_extraction",
        display_name="Journal Extraction",
        category=CATEGORY_BACKGROUND,
        description_key="settings.admin.llmConfig.types.journal_extraction",
        required_capabilities=[],
        power_tier=POWER_TIER_MEDIUM,
    ),
    "journal_consolidation": LLMTypeMetadata(
        llm_type="journal_consolidation",
        display_name="Journal Consolidation",
        category=CATEGORY_BACKGROUND,
        description_key="settings.admin.llmConfig.types.journal_consolidation",
        required_capabilities=[],
        power_tier=POWER_TIER_HIGH,
    ),
    # ADR-062: Initiative Phase + MCP ReAct
    "initiative": LLMTypeMetadata(
        llm_type="initiative",
        display_name="Initiative Node",
        category=CATEGORY_PIPELINE,
        description_key="settings.admin.llmConfig.types.initiative",
        required_capabilities=["structured_output"],
        power_tier=POWER_TIER_HIGH,
    ),
    "mcp_react_agent": LLMTypeMetadata(
        llm_type="mcp_react_agent",
        display_name="MCP Iterative (ReAct)",
        category=CATEGORY_DOMAIN_AGENTS,
        description_key="settings.admin.llmConfig.types.mcp_react_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_HIGH,
    ),
    # ADR-070: ReAct Execution Mode
    "react_agent": LLMTypeMetadata(
        llm_type="react_agent",
        display_name="ReAct Agent",
        category=CATEGORY_PIPELINE,
        description_key="settings.admin.llmConfig.types.react_agent",
        required_capabilities=["tools"],
        power_tier=POWER_TIER_HIGH,
    ),
    # Psyche Engine (evolution)
    "psyche_summary": LLMTypeMetadata(
        llm_type="psyche_summary",
        display_name="Psyche Summary",
        category=CATEGORY_BACKGROUND,
        description_key="settings.admin.llmConfig.types.psyche_summary",
        required_capabilities=[],
        power_tier=POWER_TIER_MEDIUM,
    ),
    # AI Image Generation (evolution)
    "image_generation": LLMTypeMetadata(
        llm_type="image_generation",
        display_name="Image Generation",
        category=CATEGORY_SPECIALIZED,
        description_key="settings.admin.llmConfig.types.image_generation",
        required_capabilities=[],  # Images API, not chat completions
        required_kind=LLMModelKindEnum.image,
    ),
    # Voice STT (when user opts into the remote provider for the voice mode).
    # Token-based sampling caps don't apply (STT is audio-billed); the
    # admin form should hide them for kind=audio rows.
    "voice_transcription": LLMTypeMetadata(
        llm_type="voice_transcription",
        display_name="Voice Transcription (STT)",
        category=CATEGORY_SPECIALIZED,
        description_key="settings.admin.llmConfig.types.voice_transcription",
        required_capabilities=[],  # Audio API, not chat completions
        required_kind=LLMModelKindEnum.audio,
    ),
    # Voice TTS — provider/model selection for the voice comments synthesis.
    # The voice (male + female) and the provider-specific tuning (speed,
    # response_format, rate, pitch, volume, voice_settings, …) live inside
    # ``provider_config`` JSONB so the admin form can render the right
    # inputs per provider (cf. ADR-081).
    "voice_tts": LLMTypeMetadata(
        llm_type="voice_tts",
        display_name="Voice Synthesis (TTS)",
        category=CATEGORY_SPECIALIZED,
        description_key="settings.admin.llmConfig.types.voice_tts",
        required_capabilities=[],  # TTS API, not chat completions
        required_kind=LLMModelKindEnum.tts,
    ),
}


# --- Proven Defaults (extracted from production configuration) ---
# These values are the optimized baseline for the application.
# The "Reset" button in the admin UI restores these values.
# Updated: 2026-04-08 — Merged from DEV admin UI overrides into code defaults.
# Strategy:
#   - Pipeline fast (routing, validation, resolution): openai/gpt-5-mini (reasoning_effort=minimal)
#   - Pipeline heavy (planning, analysis, initiative): qwen/qwen3.5-plus (reasoning_effort=none)
#   - Domain agents (simple): openai/gpt-4.1-nano (no reasoning)
#   - Domain agents (advanced): qwen/qwen3.5-plus (reasoning_effort=none)
#   - Query & Response: qwen/qwen3.5-plus (reasoning_effort=none)
#   - HITL & Memory: qwen/qwen3.5-plus (reasoning_effort=none)
#   - Background: qwen/qwen3.5-plus (reasoning_effort=none)
#   - Specialized: openai/gpt-5-mini (reasoning_effort=minimal) or provider-specific


LLM_DEFAULTS: dict[str, LLMAgentConfig] = {
    # --- Pipeline ---
    "compaction": LLMAgentConfig(
        provider="qwen",
        model="qwen3.5-plus",
        temperature=0.5,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=10000,
        timeout_seconds=180.0,
        reasoning_effort=ReasoningEffortToggleBudget(enabled=True, budget=4096),
    ),
    "context_resolver": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        timeout_seconds=30.0,
        reasoning_effort=ReasoningEffortEnum(effort="minimal"),
    ),
    "initiative": LLMAgentConfig(
        provider="qwen",
        model="qwen3.5-plus",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=10000,
        timeout_seconds=60.0,
        reasoning_effort=ReasoningEffortToggleBudget(enabled=False),
    ),
    "planner": LLMAgentConfig(
        provider="qwen",
        model="qwen3.5-plus",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=10000,
        timeout_seconds=60.0,
        reasoning_effort=ReasoningEffortToggleBudget(enabled=False),
    ),
    "query_analyzer": LLMAgentConfig(
        provider="qwen",
        model="qwen3.5-plus",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=10000,
        timeout_seconds=60.0,
        reasoning_effort=ReasoningEffortToggleBudget(enabled=False),
    ),
    "router": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=5000,
        timeout_seconds=60.0,
        reasoning_effort=ReasoningEffortEnum(effort="minimal"),
    ),
    "semantic_pivot": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        timeout_seconds=30.0,
        reasoning_effort=ReasoningEffortEnum(effort="minimal"),
    ),
    "semantic_validator": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        timeout_seconds=30.0,
        reasoning_effort=ReasoningEffortEnum(effort="minimal"),
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
        timeout_seconds=30.0,
    ),
    "browser_agent": LLMAgentConfig(
        provider="qwen",
        model="qwen3.5-plus",
        temperature=0.2,
        top_p=0.9,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=50000,
        timeout_seconds=120.0,
        reasoning_effort=ReasoningEffortToggleBudget(enabled=False),
    ),
    "calendar_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
        timeout_seconds=30.0,
    ),
    "contacts_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
        timeout_seconds=30.0,
    ),
    "drive_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
        timeout_seconds=30.0,
    ),
    "emails_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
        timeout_seconds=30.0,
    ),
    "hue_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        timeout_seconds=30.0,
    ),
    "mcp_react_agent": LLMAgentConfig(
        provider="qwen",
        model="qwen3.5-plus",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=50000,
        timeout_seconds=120.0,
        reasoning_effort=ReasoningEffortToggleBudget(enabled=True, budget=16384),
    ),
    # ADR-070: ReAct Execution Mode — autonomous reasoning loop (pipeline alternative)
    "react_agent": LLMAgentConfig(
        provider="qwen",
        model="qwen3.5-plus",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=50000,
        timeout_seconds=120.0,
        reasoning_effort=ReasoningEffortToggleBudget(enabled=True, budget=16384),
    ),
    "perplexity_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=3000,
        timeout_seconds=30.0,
    ),
    "places_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
        timeout_seconds=30.0,
    ),
    "routes_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
        timeout_seconds=30.0,
    ),
    "subagent": LLMAgentConfig(
        provider="qwen",
        model="qwen3.5-plus",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=10000,
        timeout_seconds=60.0,
        reasoning_effort=ReasoningEffortToggleBudget(enabled=False),
    ),
    "tasks_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
        timeout_seconds=30.0,
    ),
    "weather_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        timeout_seconds=30.0,
    ),
    "health_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1500,
        timeout_seconds=30.0,
    ),
    # Telephony agent: a single draft-producing tool call (place_phone_call) —
    # small deterministic model, same profile as the other domain agents.
    "telephony_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        timeout_seconds=30.0,
    ),
    "web_fetch_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=3000,
        timeout_seconds=30.0,
    ),
    "web_search_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=4000,
        timeout_seconds=30.0,
    ),
    "wikipedia_agent": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2000,
        timeout_seconds=30.0,
    ),
    # --- Query & Response ---
    "query_agent": LLMAgentConfig(
        provider="qwen",
        model="qwen3.5-plus",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=5000,
        timeout_seconds=60.0,
        reasoning_effort=ReasoningEffortToggleBudget(enabled=False),
    ),
    "response": LLMAgentConfig(
        provider="qwen",
        model="qwen3.5-plus",
        temperature=1.0,
        top_p=1.0,
        frequency_penalty=0.1,
        presence_penalty=0.0,
        max_tokens=10000,
        timeout_seconds=60.0,
        reasoning_effort=ReasoningEffortToggleBudget(enabled=False),
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
        timeout_seconds=30.0,
    ),
    "hitl_plan_approval_question_generator": LLMAgentConfig(
        provider="qwen",
        model="qwen3.5-plus",
        temperature=1.0,
        top_p=1.0,
        frequency_penalty=0.7,
        presence_penalty=0.3,
        max_tokens=1000,
        timeout_seconds=30.0,
        reasoning_effort=ReasoningEffortToggleBudget(enabled=False),
    ),
    "hitl_question_generator": LLMAgentConfig(
        provider="qwen",
        model="qwen3.5-plus",
        temperature=1.0,
        top_p=1.0,
        frequency_penalty=0.7,
        presence_penalty=0.3,
        max_tokens=1000,
        timeout_seconds=30.0,
        reasoning_effort=ReasoningEffortToggleBudget(enabled=False),
    ),
    # --- Memory ---
    "memory_extraction": LLMAgentConfig(
        provider="openai",
        model="gpt-5.4-mini",
        temperature=0.5,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        timeout_seconds=60.0,
        reasoning_effort=ReasoningEffortEnum(effort="low"),
    ),
    "open_loop_extraction": LLMAgentConfig(
        provider="openai",
        model="gpt-5.4-mini",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=800,
        timeout_seconds=45.0,
        reasoning_effort=ReasoningEffortEnum(effort="low"),
    ),
    "memory_reference_extraction": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=500,
        timeout_seconds=30.0,
        # was "minimal" — invalid for non-reasoning gpt-4.1-nano (option-(a) drop).
        reasoning_effort=None,
    ),
    "memory_reference_resolution": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        timeout_seconds=30.0,
        reasoning_effort=ReasoningEffortEnum(effort="minimal"),
    ),
    # --- Background ---
    "briefing": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.7,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=500,
        timeout_seconds=20.0,
    ),
    # Telephony return synthesis: a single tool-less call summarizing a finished
    # call + proposing a follow-up. Low temperature (factual). The budget must
    # fit the FULL debrief-era output (ADR-174: summary + proposal_text + 6
    # debrief fields) PLUS reasoning tokens when the admin routes the type to a
    # thinking model — measured 2026-07-29 on deepseek-v4-flash effort=high: a
    # 600-token cap was consumed entirely by reasoning (empty/truncated JSON on
    # every call). Calibrated like heartbeat_decision (same shape of task).
    "telephony_synthesis": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.4,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=5000,
        timeout_seconds=60.0,
    ),
    "broadcast_translator": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=5000,
        timeout_seconds=30.0,
        reasoning_effort=ReasoningEffortEnum(effort="minimal"),
    ),
    # Personality title/description translation — preserves the previous
    # hardcoded behavior (gpt-4.1-nano, temp 0.3, 500 tokens) as code default;
    # now overridable from the admin LLM Configuration UI (N-219.1).
    "personality_translation": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-nano",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=500,
        timeout_seconds=20.0,
    ),
    "heartbeat_decision": LLMAgentConfig(
        provider="qwen",
        model="qwen3.5-plus",
        temperature=0.5,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=5000,
        timeout_seconds=60.0,
        reasoning_effort=ReasoningEffortToggleBudget(enabled=True, budget=4096),
    ),
    "heartbeat_message": LLMAgentConfig(
        provider="qwen",
        model="qwen3.5-plus",
        temperature=1.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=5000,
        timeout_seconds=60.0,
        reasoning_effort=ReasoningEffortToggleBudget(enabled=False),
    ),
    "interest_content": LLMAgentConfig(
        provider="qwen",
        model="qwen3.5-plus",
        temperature=1.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=10000,
        timeout_seconds=60.0,
        reasoning_effort=ReasoningEffortToggleBudget(enabled=False),
    ),
    "interest_extraction": LLMAgentConfig(
        provider="openai",
        model="gpt-5.4-mini",
        temperature=0.5,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=500,
        timeout_seconds=60.0,
        reasoning_effort=ReasoningEffortEnum(effort="low"),
    ),
    "journal_consolidation": LLMAgentConfig(
        provider="qwen",
        model="qwen3.5-plus",
        temperature=0.5,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=10000,
        timeout_seconds=180.0,
        reasoning_effort=ReasoningEffortToggleBudget(enabled=True, budget=4096),
    ),
    "journal_extraction": LLMAgentConfig(
        provider="openai",
        model="gpt-5.4-mini",
        temperature=0.5,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=5000,
        timeout_seconds=60.0,
        reasoning_effort=ReasoningEffortEnum(effort="low"),
    ),
    "psyche_summary": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.7,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        timeout_seconds=30.0,
        reasoning_effort=ReasoningEffortEnum(effort="minimal"),
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
        timeout_seconds=30.0,
    ),
    "image_generation": LLMAgentConfig(
        provider="openai",
        model="gpt-image-1",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=50000,
        timeout_seconds=120.0,
    ),
    # Voice STT — ElevenLabs Scribe v2 by default ($0.22/hour). The sampling
    # parameters are not consumed by the STT API (no token sampling); they
    # carry safe placeholders so the LLMAgentConfig validation passes.
    "voice_transcription": LLMAgentConfig(
        provider="elevenlabs",
        model="scribe_v2",
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,  # placeholder; STT does not produce token output
        timeout_seconds=60.0,
    ),
    # Voice TTS — Edge (Microsoft) by default, free. Voice + provider-
    # specific tuning live in ``provider_config`` (JSONB string) so the
    # admin can switch providers without losing the per-model defaults.
    # The default carries Edge's standard French voices and rate.
    "voice_tts": LLMAgentConfig(
        provider="edge",
        model="edge-tts",
        provider_config=(
            "{"
            '"voice_male": "fr-FR-RemyMultilingualNeural",'
            '"voice_female": "fr-FR-VivienneMultilingualNeural",'
            '"rate": "+10%",'
            '"pitch": "+0Hz",'
            '"volume": "+0%"'
            "}"
        ),
        temperature=0.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,  # placeholder; TTS does not produce token output
        timeout_seconds=60.0,
    ),
    "mcp_description": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        timeout_seconds=30.0,
        reasoning_effort=ReasoningEffortEnum(effort="minimal"),
    ),
    "mcp_app_react_agent": LLMAgentConfig(
        provider="anthropic",
        model="claude-opus-4-6",
        # Reasoning (adaptive thinking) is enabled → Anthropic forbids a custom
        # temperature; the factory omits it at call time. We keep 1.0 here (the
        # only value Anthropic accepts with thinking) for a coherent default.
        temperature=1.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=50000,
        timeout_seconds=120.0,
        reasoning_effort=ReasoningEffortEnum(effort="medium"),
    ),
    "skill_description_translator": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        timeout_seconds=30.0,
        reasoning_effort=ReasoningEffortEnum(effort="minimal"),
    ),
    "vision_analysis": LLMAgentConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=1.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=5000,
        timeout_seconds=60.0,
        reasoning_effort=ReasoningEffortEnum(effort="minimal"),
    ),
    "voice_comment": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1-mini",
        temperature=1.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=1000,
        timeout_seconds=30.0,
    ),
}

# NOTE: The legacy ``IMAGE_GENERATION_MODELS`` constant was removed in the
# v1.x DB-source-of-truth release. The list of image-generation models now
# comes from ``ImageOptionsCache.get_models_grouped_by_provider()`` (DISTINCT
# on ``image_generation_pricing``). To declare a new image model an admin
# adds its 9 (model, quality, size) pricing rows in Tarification LLM Image —
# the model becomes immediately selectable in Configuration LLM and in the
# user-facing Préférences via ``GET /image-generation/options``.


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
    "elevenlabs": "ElevenLabs",
    "edge": "Edge TTS (Microsoft)",
}
