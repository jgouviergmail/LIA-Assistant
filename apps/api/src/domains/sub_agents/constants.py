"""
Sub-Agents domain constants and pre-defined templates.

Templates are Python constants (no DB table). Each template provides
default configuration for common sub-agent archetypes.
"""

from typing import Any

from src.core.constants import TOOL_NAME_DELEGATE_SUB_AGENT

# Settings defaults are centralized in src/core/constants.py (SUBAGENT_* prefix).
# This file contains domain-specific constants only.

# ============================================================================
# REDIS KEYS (Phase B — daily token budget)
# ============================================================================

# Redis key pattern for daily token budget
SUBAGENT_DAILY_BUDGET_KEY_PREFIX = "subagent_daily_budget:"
SUBAGENT_DAILY_BUDGET_TTL_SECONDS = 86400  # 24h, reset at midnight UTC

# ============================================================================
# BLOCKED TOOLS (write/destructive operations — V1 read-only sub-agents)
# ============================================================================

SUBAGENT_DEFAULT_BLOCKED_TOOLS: list[str] = [
    # Email write operations
    "send_email_tool",
    "reply_email_tool",
    "forward_email_tool",
    "delete_email_tool",
    # Label mutations
    "create_label_tool",
    "update_label_tool",
    "delete_label_tool",
    "apply_labels_tool",
    "remove_labels_tool",
    # Calendar write operations
    "create_event_tool",
    "update_event_tool",
    "delete_event_tool",
    # Task write operations
    "create_task_tool",
    "complete_task_tool",
]

# ============================================================================
# READ-ONLY SYSTEM PROMPT PREFIX (injected before sub-agent's custom prompt)
# ============================================================================

SUBAGENT_READ_ONLY_PREFIX = (
    "You are a read-only sub-agent. You MUST NOT attempt any write, create, "
    "update, delete, or send operations. Your role is strictly limited to "
    "searching, reading, analyzing, and synthesizing information. "
    "If asked to perform a write operation, explain that you cannot and suggest "
    "the user ask the principal assistant instead.\n\n"
)

SUBAGENT_CONTEXT_SUMMARY_PREFIX = "Previous execution context: "

# ============================================================================
# DIRECT PIPELINE CONSTANTS (simplified executor — bypass full graph)
# ============================================================================

# Tools excluded from sub-agent planner catalogue (prevents sub-sub-agent recursion)
SUBAGENT_EXCLUDED_PLANNER_TOOLS: frozenset[str] = frozenset({TOOL_NAME_DELEGATE_SUB_AGENT})

# Synthesis prompt: versioned file in src/domains/agents/prompts/v1/subagent_synthesis_prompt.txt
# Loaded via load_prompt("subagent_synthesis_prompt") in executor.py
SUBAGENT_SYNTHESIS_PROMPT_NAME = "subagent_synthesis_prompt"

# ============================================================================
# PRE-DEFINED TEMPLATES
# ============================================================================

# i18n keys follow pattern: sub_agents.templates.{template_id}.{field}
# Translations in locales/{lang}/translation.json

SUBAGENT_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "research_assistant",
        "name_i18n_key": "sub_agents.templates.research_assistant.name",
        "description_i18n_key": "sub_agents.templates.research_assistant.description",
        "name_default": "Research Assistant",
        "description_default": (
            "Specialized in deep web research, multi-source synthesis, " "and fact-checking"
        ),
        "icon": "🔍",
        "system_prompt": (
            "You are a research specialist. Your strengths:\n"
            "- Deep web research using multiple search engines\n"
            "- Cross-referencing information from different sources\n"
            "- Identifying contradictions and reliability of sources\n"
            "- Producing structured, well-sourced summaries\n\n"
            "Always cite your sources. When information conflicts, "
            "present both perspectives with source attribution."
        ),
        "suggested_skill_ids": [],
        "suggested_tools": [
            "unified_web_search_tool",
            "brave_search_tool",
            "brave_news_tool",
            "perplexity_search_tool",
            "perplexity_ask_tool",
            "search_wikipedia_tool",
            "get_wikipedia_article_tool",
        ],
        "default_blocked_tools": SUBAGENT_DEFAULT_BLOCKED_TOOLS,
    },
    {
        "id": "writing_assistant",
        "name_i18n_key": "sub_agents.templates.writing_assistant.name",
        "description_i18n_key": "sub_agents.templates.writing_assistant.description",
        "name_default": "Writing Assistant",
        "description_default": "Specialized in drafting, editing, and improving written content",
        "icon": "✍️",
        "system_prompt": (
            "You are a writing specialist. Your strengths:\n"
            "- Drafting clear, well-structured content\n"
            "- Adapting tone and style to the target audience\n"
            "- Proofreading and suggesting improvements\n"
            "- Summarizing long documents\n\n"
            "Focus on clarity, conciseness, and impact. "
            "When editing, explain your changes."
        ),
        "suggested_skill_ids": [],
        "suggested_tools": [],
        "default_blocked_tools": SUBAGENT_DEFAULT_BLOCKED_TOOLS,
    },
    {
        "id": "data_analyst",
        "name_i18n_key": "sub_agents.templates.data_analyst.name",
        "description_i18n_key": "sub_agents.templates.data_analyst.description",
        "name_default": "Data Analyst",
        "description_default": "Specialized in analyzing data from emails, calendar, and files",
        "icon": "📊",
        "system_prompt": (
            "You are a data analysis specialist. Your strengths:\n"
            "- Analyzing patterns in emails, calendar events, and files\n"
            "- Producing structured reports with key metrics\n"
            "- Identifying trends and anomalies\n"
            "- Creating actionable insights from raw data\n\n"
            "Always present data clearly with numbers, dates, and "
            "concrete observations. Separate facts from interpretations."
        ),
        "suggested_skill_ids": [],
        "suggested_tools": [
            "search_emails_tool",
            "get_email_details_tool",
            "search_events_tool",
            "get_event_details_tool",
            "search_files_tool",
            "get_file_details_tool",
            "list_tasks_tool",
        ],
        "default_blocked_tools": SUBAGENT_DEFAULT_BLOCKED_TOOLS,
    },
]


def get_template_by_id(template_id: str) -> dict[str, Any] | None:
    """Look up a template by its ID."""
    for template in SUBAGENT_TEMPLATES:
        if template["id"] == template_id:
            return template
    return None
