"""
Agent system prompts with versioned loading.

This module provides backward-compatible access to versioned prompts stored in files.
All prompts are now version-controlled for A/B testing, rollbacks, and governance.

Migration status:
- Router prompt: Migrated to {version}/router_system_prompt.txt (ROUTER_PROMPT_VERSION)
- Response prompt: Migrated to {version}/response_system_prompt_base.txt (RESPONSE_PROMPT_VERSION)
- Contacts agent prompt: Migrated to {version}/contacts_agent_prompt.txt (CONTACTS_AGENT_PROMPT_VERSION)
- HITL classifier prompt: Migrated to {version}/hitl_classifier_prompt.txt (HITL_CLASSIFIER_PROMPT_VERSION)
- Planner prompt: Migrated to {version}/planner_system_prompt.txt (PLANNER_PROMPT_VERSION)

All versions are configurable via environment variables in .env or .env.example.
Default version: v1 for all prompts.

Compliance: LangGraph v1.0 + LangChain v1.0 best practices
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import structlog

from src.core.constants import DEFAULT_LANGUAGE
from src.core.i18n_types import LANGUAGE_NAMES
from src.domains.agents.prompts.prompt_loader import (
    PromptIntegrityError,
    PromptLoadError,
    PromptName,
    PromptVersion,
    calculate_prompt_hash,
    get_available_versions,
    get_prompt_metadata,
    list_available_prompts,
    load_prompt,
    load_prompt_with_fallback,
    validate_all_prompts,
)

logger = structlog.get_logger(__name__)

# ============================
# TIMEZONE AND TEMPORAL CONTEXT
# ============================

# Default timezone for fallback
DEFAULT_TIMEZONE = "Europe/Paris"

# ============================
# PROMPT HELPERS
# ============================


def escape_braces(s: str) -> str:
    """Escape curly braces in dynamic content injected into ChatPromptTemplate.

    Must be applied to values that end up inside a ChatPromptTemplate format string
    (e.g., formatted_system_prompt in get_response_prompt(), or values passed to
    chain.ainvoke() for {placeholder} variables). ChatPromptTemplate re-processes
    the string, so {text} in values is interpreted as a template variable.

    Do NOT use for plain str.format() values — str.format() does not re-process
    substituted values, so {{text}} would appear literally in the output.

    Introduced for langchain-core 1.2.17 stricter template variable validation.
    """
    return s.replace("{", "{{").replace("}", "}}")


def format_with_current_datetime(
    prompt: str, user_timezone: str = DEFAULT_TIMEZONE, user_language: str = DEFAULT_LANGUAGE
) -> str:
    """
    Inject current_datetime placeholder into a prompt if present.

    Uses str.replace() for partial substitution to avoid KeyError when
    prompts contain other placeholders like {user_query}, {detected_domains}.
    """
    if "{current_datetime}" not in prompt:
        return prompt
    try:
        datetime_context = get_current_datetime_context(user_timezone, user_language)
        return prompt.replace("{current_datetime}", datetime_context)
    except Exception as e:
        # Log warning for debugging - should not happen in production
        logger.warning(
            "format_with_current_datetime_failed",
            error=str(e),
            error_type=type(e).__name__,
            user_timezone=user_timezone,
            user_language=user_language,
            prompt_preview=prompt[:100] if len(prompt) > 100 else prompt,
        )
        # Fail-safe: return original prompt if formatting fails
        return prompt


# Period of day translations (i18n - 6 languages)
_PERIOD_OF_DAY = {
    "fr": ["Nuit", "Matin", "Midi", "Après-midi", "Soirée"],
    "en": ["Night", "Morning", "Midday", "Afternoon", "Evening"],
    "es": ["Noche", "Mañana", "Mediodía", "Tarde", "Noche"],
    "de": ["Nacht", "Morgen", "Mittag", "Nachmittag", "Abend"],
    "it": ["Notte", "Mattina", "Mezzogiorno", "Pomeriggio", "Sera"],
    "zh-CN": ["夜间", "上午", "中午", "下午", "晚上"],
}


def get_period_of_day(hour: int, language: str = "fr") -> str:
    """
    Get period of day name based on hour (24h format).

    Args:
        hour: Hour in 24h format (0-23).
        language: Language code (fr, en, es, de, it, zh-CN).

    Returns:
        Period name in the specified language.
    """
    lang = language[:2] if len(language) > 2 and language != "zh-CN" else language
    periods = _PERIOD_OF_DAY.get(lang, _PERIOD_OF_DAY["fr"])

    if 5 <= hour < 12:
        return periods[1]  # Morning
    elif 12 <= hour < 14:
        return periods[2]  # Midday
    elif 14 <= hour < 18:
        return periods[3]  # Afternoon
    elif 18 <= hour < 22:
        return periods[4]  # Evening
    else:
        return periods[0]  # Night


# Season translations (i18n - 6 languages)
_SEASONS = {
    "fr": ["Hiver", "Printemps", "Été", "Automne"],
    "en": ["Winter", "Spring", "Summer", "Autumn"],
    "es": ["Invierno", "Primavera", "Verano", "Otoño"],
    "de": ["Winter", "Frühling", "Sommer", "Herbst"],
    "it": ["Inverno", "Primavera", "Estate", "Autunno"],
    "zh-CN": ["冬季", "春季", "夏季", "秋季"],
}


def get_season(month: int, language: str = "fr") -> str:
    """Get season name based on month (Northern Hemisphere)."""
    lang = language[:2] if len(language) > 2 and language != "zh-CN" else language
    seasons = _SEASONS.get(lang, _SEASONS["fr"])

    if month in [12, 1, 2]:
        return seasons[0]  # Winter
    elif month in [3, 4, 5]:
        return seasons[1]  # Spring
    elif month in [6, 7, 8]:
        return seasons[2]  # Summer
    else:
        return seasons[3]  # Autumn


def is_weekend(weekday: int) -> bool:
    """Check if day is weekend (Saturday or Sunday)."""
    return weekday >= 5


# Day names translations (i18n - 6 languages)
_DAY_NAMES = {
    "fr": ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "es": ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"],
    "de": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
    "it": ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"],
    "zh-CN": ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"],
}

# Month names translations (i18n - 6 languages)
_MONTH_NAMES = {
    "fr": [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ],
    "en": [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ],
    "es": [
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ],
    "de": [
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ],
    "it": [
        "gennaio",
        "febbraio",
        "marzo",
        "aprile",
        "maggio",
        "giugno",
        "luglio",
        "agosto",
        "settembre",
        "ottobre",
        "novembre",
        "dicembre",
    ],
    "zh-CN": [
        "一月",
        "二月",
        "三月",
        "四月",
        "五月",
        "六月",
        "七月",
        "八月",
        "九月",
        "十月",
        "十一月",
        "十二月",
    ],
}

# Weekend status translations
_WEEK_STATUS = {
    "fr": ["Semaine", "Week-end"],
    "en": ["Weekday", "Weekend"],
    "es": ["Día laborable", "Fin de semana"],
    "de": ["Wochentag", "Wochenende"],
    "it": ["Giorno feriale", "Fine settimana"],
    "zh-CN": ["工作日", "周末"],
}


def get_current_datetime_context(
    user_timezone: str = DEFAULT_TIMEZONE, language: str = "fr"
) -> str:
    """
    Get rich temporal context for LLM prompts with user's timezone.

    Generates a comprehensive datetime context string with:
    - Full date in user's timezone
    - Time with period indicator
    - Day of week
    - Season
    - Weekend indicator
    """
    try:
        lang = language[:2] if len(language) > 2 and language != "zh-CN" else language
        if lang not in _DAY_NAMES:
            lang = "fr"

        utc_now = datetime.now(UTC)
        user_tz = ZoneInfo(user_timezone)
        user_now = utc_now.astimezone(user_tz)

        hour = user_now.hour
        weekday = user_now.weekday()
        month = user_now.month

        period = get_period_of_day(hour, language)
        season = get_season(month, language)
        is_weekend_day = is_weekend(weekday)

        day_name = _DAY_NAMES[lang][weekday]
        month_name = _MONTH_NAMES[lang][month - 1]
        week_status = _WEEK_STATUS[lang][1] if is_weekend_day else _WEEK_STATUS[lang][0]

        if lang == "en":
            date_format = f"{day_name} {month_name} {user_now.day}, {user_now.year}"
            time_format = user_now.strftime("%I:%M %p")
        elif lang == "zh-CN":
            date_format = f"{user_now.year}年{month_name}{user_now.day}日 {day_name}"
            time_format = user_now.strftime("%H:%M")
        else:
            date_format = f"{day_name} {user_now.day} {month_name} {user_now.year}"
            time_format = user_now.strftime("%H:%M")

        # Add ISO format WITH timezone offset for time-sensitive operations
        # CRITICAL: The offset is required so the planner generates correct times
        # When user says "21h", planner should generate "2026-01-18T21:00:00+01:00" not "...Z"
        iso_format = user_now.isoformat()

        return f"📅 {date_format}, {time_format} ({period}) - {week_status} - {season} | ISO: {iso_format} | Timezone: {user_timezone}"

    except Exception as e:
        utc_now = datetime.now(UTC)
        return f"📅 {utc_now.strftime('%Y-%m-%d %H:%M:%S')} UTC (timezone conversion failed: {e})"


# ============================
# RESPONSE NODE PROMPT
# ============================


def get_response_prompt(
    user_timezone: str = DEFAULT_TIMEZONE,
    user_language: str = DEFAULT_LANGUAGE,
    personality_instruction: str | None = None,
    conversation_history: str = "(aucun historique)",
    window_size: int = 20,
    psychological_profile: str | None = None,
    knowledge_context: str = "",
    user_query: str = "",
    enriched_query: str | None = None,
    data_for_filtering: str = "",
    resolved_references: dict[str, str] | None = None,
    anticipated_needs: list[str] | None = None,
    skills_context: str = "",
    rag_context: str = "",
) -> str:
    """Get the formatted system prompt for the response node.

    Returns the formatted system prompt string (not a ChatPromptTemplate).
    The caller (response_node) is responsible for building the ChatPromptTemplate
    dynamically, conditionally including system blocks (rejection_override,
    agent_results) only when non-empty. This prevents sending empty system
    content blocks which are rejected by some LLM providers (e.g., Anthropic).

    V3 Architecture: LLM generates conversational response only.
    Data formatting is handled by HTML components (ContactCard, EmailCard, etc.)
    and injected post-LLM via HtmlRenderer.

    Intelligent Filtering (2025-01): When data_for_filtering is provided,
    the LLM analyzes user_query criteria and returns relevant item IDs
    in <relevant_ids> tags for post-filtering before HTML rendering.

    Args:
        user_timezone: User's IANA timezone for temporal context.
        user_language: User's language code (fr, en, etc.).
        personality_instruction: LLM personality prompt instruction.
        conversation_history: Formatted conversation history string.
        window_size: Number of turns in conversation window.
        psychological_profile: User's psychological profile for memory injection.
        knowledge_context: Brave Search enrichment context for encyclopedic knowledge.
            Injected from KnowledgeEnrichmentService (Web or News search results).
        user_query: Current user query (original, in user's language).
        enriched_query: Enriched query with context resolved (in English).
            Example: "je veux les détails" + history "où habitent les dupond"
            → enriched_query: "get contact details for the dupond family"
        data_for_filtering: Enriched data with IDs for LLM filtering analysis.
        resolved_references: Resolved personal references from memory (e.g., {"ma femme": "jean dupond"}).
        anticipated_needs: List of anticipated user needs for proactive suggestions.
            Example: ["may want reminder", "may want to reschedule"]
            Used by LIA to provide proactive suggestions in response.
        skills_context: Skills content per activation route.
            Routes 1+2 (planner/bypass): L2 <skill_content> structured wrapping.
            Route 3 (conversation): L1 catalogue with activate_skill_tool instruction.
        rag_context: RAG Spaces context from user's knowledge documents.
            Injected from RAG retrieval service (hybrid semantic + BM25 search).

    Returns:
        Formatted system prompt string ready for ChatPromptTemplate construction.
    """
    from src.core.config import get_settings

    settings = get_settings()

    response_system_prompt_template = load_prompt(
        "response_system_prompt_base", version=settings.response_prompt_version
    )

    # V3 Architecture: No fewshots - HTML components handle data formatting
    fewshot_examples = ""

    default_personality = load_prompt("default_personality_prompt")

    # Escape curly braces in user-provided content to prevent format() interpretation
    # User query and data_for_filtering may contain {} which would be interpreted as placeholders
    safe_user_query = escape_braces(user_query) if user_query else "(pas de requête)"
    safe_enriched_query = escape_braces(enriched_query) if enriched_query else ""
    safe_data_for_filtering = (
        escape_braces(data_for_filtering) if data_for_filtering else "(pas de données)"
    )
    safe_knowledge_context = escape_braces(knowledge_context) if knowledge_context else ""

    # Format resolved references for natural response phrasing
    # Example: {"ma femme": "jean dupond"} → "ma femme = jean dupond"
    resolved_refs_str = ""
    if resolved_references:
        resolved_refs_str = ", ".join(
            f'"{ref}" = {name}' for ref, name in resolved_references.items()
        )

    # Format anticipated needs for proactive suggestions
    # Example: ["may want reminder", "may want to reschedule"] → "- may want reminder\n- may want to reschedule"
    anticipated_needs_str = ""
    if anticipated_needs and len(anticipated_needs) > 0:
        anticipated_needs_str = "\n".join(f"- {need}" for need in anticipated_needs[:4])  # Max 4
    else:
        anticipated_needs_str = "(aucun besoin anticipé)"

    # Convert language code to human-readable name for LLM comprehension
    # e.g., "zh-CN" → "Simplified Chinese", "fr" → "French"
    user_language_name = LANGUAGE_NAMES.get(user_language, user_language)

    logger.info(
        "response_prompt_language_conversion",
        user_language_code=user_language,
        user_language_name=user_language_name,
    )

    # Skills context: escape braces for ChatPromptTemplate safety
    safe_skills_context = escape_braces(skills_context) if skills_context else ""
    safe_rag_context = escape_braces(rag_context) if rag_context else ""

    formatted_system_prompt = response_system_prompt_template.format(
        fewshot_examples=fewshot_examples,
        user_language=user_language_name,
        current_datetime=get_current_datetime_context(user_timezone, user_language),
        personnalite=personality_instruction or default_personality,
        conversation_history=conversation_history,
        window_size=window_size,
        psychological_profile=psychological_profile or "",
        knowledge_context=safe_knowledge_context,
        rag_context=safe_rag_context,
        user_query=safe_user_query,
        enriched_query=safe_enriched_query,
        data_for_filtering=safe_data_for_filtering,
        resolved_references=resolved_refs_str,
        anticipated_needs=anticipated_needs_str,
        skills_context=safe_skills_context,
    )

    return formatted_system_prompt


# ============================
# PLANNER NODE PROMPT
# ============================


def build_schema_reference_guide(tool_names: list[str]) -> str:
    """Build tool response schemas reference guide for planner prompt injection."""
    try:
        import json

        from src.domains.agents.tools.schema_registry import ToolSchemaRegistry

        registry = ToolSchemaRegistry.get_instance()
        guide_sections = []

        for tool_name in tool_names:
            schema_data = registry.get_schema(tool_name)
            if not schema_data:
                continue

            response_schema = schema_data["response_schema"]
            examples = schema_data.get("examples", [])

            section = f"### {tool_name}\n\nResponse Structure:\n```json\n"
            section += json.dumps(response_schema, indent=2, ensure_ascii=False)
            section += "\n```\n\n"

            if examples:
                section += "Valid References:\n"
                for example in examples:
                    section += f"- {example['reference']} => {example['expected_type']}\n"

            guide_sections.append(section)

        return "\n".join(guide_sections) if guide_sections else ""

    except Exception as e:
        logger.warning("schema_guide_build_failed", error=str(e), error_type=type(e).__name__)
        return ""


def _get_semantic_deps_fallback() -> str:
    """Get fallback message for semantic dependencies from centralized constants."""
    from src.core.constants import SEMANTIC_DEPS_NO_DEPENDENCIES

    return SEMANTIC_DEPS_NO_DEPENDENCIES


def _build_for_each_directive(
    for_each_detected: bool,
    for_each_collection_key: str | None,
    cardinality_magnitude: int | None,
) -> str:
    """
    Build FOR_EACH directive for planner prompt injection.

    When for_each_detected=True, generates a CRITICAL directive that instructs
    the LLM to use the for_each pattern in its plan.

    Args:
        for_each_detected: True if user wants action for EACH item
        for_each_collection_key: Collection key to iterate over (contacts, events, etc.)
        cardinality_magnitude: Expected number of items (None=unknown, 999=all, N=specific)

    Returns:
        Formatted directive string, empty if for_each not detected
    """
    from src.core.config import get_settings
    from src.core.constants import (
        CARDINALITY_ALL,
        FOR_EACH_COLLECTION_DEFAULT,
        FOR_EACH_MAX_HARD_LIMIT,
    )

    logger = structlog.get_logger(__name__)

    if not for_each_detected:
        return ""

    settings = get_settings()
    collection = for_each_collection_key or FOR_EACH_COLLECTION_DEFAULT

    # Build cardinality hint for LLM understanding
    if cardinality_magnitude is None:
        cardinality_hint = "unknown number of"
        for_each_max_value = settings.for_each_max_default
    elif cardinality_magnitude == CARDINALITY_ALL:
        cardinality_hint = "ALL"
        for_each_max_value = (
            settings.for_each_max_default
        )  # Safety: use config default even for "all"
    else:
        cardinality_hint = f"~{cardinality_magnitude}"
        # Cap at hard limit to ensure LLM generates valid schema
        for_each_max_value = min(cardinality_magnitude, FOR_EACH_MAX_HARD_LIMIT)

    logger.debug(
        "for_each_directive_generated",
        collection=collection,
        cardinality_magnitude=cardinality_magnitude,
        cardinality_hint=cardinality_hint,
        for_each_max_value=for_each_max_value,
    )

    # Load directive from versioned prompt file
    directive_template = load_prompt(
        "for_each_directive_prompt",
        version=settings.planner_prompt_version,
    )

    return directive_template.format(
        collection=collection,
        cardinality_hint=cardinality_hint,
        for_each_max_value=for_each_max_value,
    )


def get_smart_planner_prompt(
    user_goal: str,
    intent: str,
    domains: str,
    anticipated_needs: str,
    catalogue: str,
    original_query: str,
    context: str = "",
    references: str = "",
    user_timezone: str = DEFAULT_TIMEZONE,
    user_language: str = DEFAULT_LANGUAGE,
    validation_feedback: str | None = None,
    semantic_dependencies: str = "",
    learned_patterns: str = "",
    mcp_reference: str = "",
    # FOR_EACH detection from QueryIntelligence
    for_each_detected: bool = False,
    for_each_collection_key: str | None = None,
    cardinality_magnitude: int | None = None,
    # Skills catalogue (agentskills.io standard)
    skills_catalog: str = "",
) -> str:
    """
    Get formatted smart planner prompt for single-domain or simple queries.

    Architecture v3 - Uses filtered catalogue for token efficiency.

    Args:
        user_goal: The user's original query/goal
        intent: Detected intent from query intelligence
        domains: Comma-separated list of detected domains
        anticipated_needs: Anticipated user needs from intelligence
        catalogue: Filtered tool catalogue JSON
        original_query: Original user query in user's language (for search terms)
        context: Optional context from previous interactions
        references: Optional resolved references from context
        user_timezone: User's IANA timezone for temporal context
        user_language: User's language code (fr, en, etc.)
        semantic_dependencies: Dynamic semantic type dependencies for cross-domain planning
        for_each_detected: True if user wants action for EACH item (iteration pattern)
        for_each_collection_key: Collection key to iterate over (contacts, events, etc.)
        cardinality_magnitude: Expected number of items (None=unknown, 999=all, N=specific)
        skills_catalog: XML skills catalogue (agentskills.io L1 progressive disclosure)

    Returns:
        Formatted prompt string ready for LLM
    """
    from src.core.config import get_settings

    settings = get_settings()

    template = load_prompt(
        "smart_planner_prompt",
        version=settings.planner_prompt_version,
    )

    # Build FOR_EACH directive if detected
    for_each_directive = _build_for_each_directive(
        for_each_detected, for_each_collection_key, cardinality_magnitude
    )

    # Build result_keys_list from centralized source of truth
    from src.domains.agents.utils.type_domain_mapping import ALL_RESULT_KEYS

    result_keys_list = ", ".join(sorted(ALL_RESULT_KEYS))

    return template.format(
        user_goal=user_goal,
        intent=intent,
        domains=domains,
        anticipated_needs=anticipated_needs,
        catalogue=catalogue,
        original_query=original_query,
        context=context or "(no context)",
        references=references or "(no resolved references)",
        current_datetime=get_current_datetime_context(user_timezone, user_language),
        user_language=user_language,
        validation_feedback=validation_feedback or "",
        semantic_dependencies=semantic_dependencies or _get_semantic_deps_fallback(),
        learned_patterns=learned_patterns,
        mcp_reference=mcp_reference,
        for_each_directive=for_each_directive,
        skills_catalog=skills_catalog,
        result_keys_list=result_keys_list,
    )


def get_smart_planner_multi_domain_prompt(
    domains: str,
    primary_domain: str,
    intent: str,
    user_goal: str,
    anticipated_needs: str,
    catalogue: str,
    original_query: str,
    context: str = "",
    references: str = "",
    user_timezone: str = DEFAULT_TIMEZONE,
    user_language: str = DEFAULT_LANGUAGE,
    validation_feedback: str | None = None,
    semantic_dependencies: str = "",
    learned_patterns: str = "",
    mcp_reference: str = "",
    # FOR_EACH detection from QueryIntelligence
    for_each_detected: bool = False,
    for_each_collection_key: str | None = None,
    cardinality_magnitude: int | None = None,
    # Skills catalogue (agentskills.io standard)
    skills_catalog: str = "",
) -> str:
    """
    Get formatted smart planner prompt for multi-domain queries.

    Used when the query involves multiple domains that need to work together
    (e.g., "envoie un email à Jean" requires contacts + emails).

    Args:
        domains: Comma-separated list of all detected domains
        primary_domain: The primary domain for the query
        intent: Detected intent from query intelligence
        user_goal: User's high-level goal (plan_organize, communicate, etc.)
        anticipated_needs: Anticipated follow-up needs
        catalogue: Filtered tool catalogue JSON (includes tools from all domains)
        original_query: Original user query in user's language (for search terms)
        context: Resolved context from previous results (e.g., resolved RDV)
        references: Resolved memory references (e.g., "my wife" → "jean")
        user_timezone: User's IANA timezone for temporal context
        user_language: User's language code (fr, en, etc.)
        semantic_dependencies: Dynamic semantic type dependencies for cross-domain planning
        for_each_detected: True if user wants action for EACH item (iteration pattern)
        for_each_collection_key: Collection key to iterate over (contacts, events, etc.)
        cardinality_magnitude: Expected number of items (None=unknown, 999=all, N=specific)
        skills_catalog: XML skills catalogue (agentskills.io L1 progressive disclosure)

    Returns:
        Formatted prompt string ready for LLM
    """
    from src.core.config import get_settings

    settings = get_settings()

    template = load_prompt(
        "smart_planner_multi_domain_prompt",
        version=settings.planner_prompt_version,
    )

    # Build FOR_EACH directive if detected
    for_each_directive = _build_for_each_directive(
        for_each_detected, for_each_collection_key, cardinality_magnitude
    )

    # Build result_keys_list from centralized source of truth
    from src.domains.agents.utils.type_domain_mapping import ALL_RESULT_KEYS

    result_keys_list = ", ".join(sorted(ALL_RESULT_KEYS))

    return template.format(
        domains=domains,
        primary_domain=primary_domain,
        intent=intent,
        user_goal=user_goal,
        anticipated_needs=anticipated_needs,
        catalogue=catalogue,
        original_query=original_query,
        context=context,
        references=references,
        current_datetime=get_current_datetime_context(user_timezone, user_language),
        user_language=user_language,
        validation_feedback=validation_feedback or "",
        semantic_dependencies=semantic_dependencies or _get_semantic_deps_fallback(),
        learned_patterns=learned_patterns,
        mcp_reference=mcp_reference,
        for_each_directive=for_each_directive,
        skills_catalog=skills_catalog,
        result_keys_list=result_keys_list,
    )


def get_planner_prompt(
    context_section: str,
    catalogue_json: str,
    user_message: str,
    response_schemas: str | None = None,
    user_timezone: str = DEFAULT_TIMEZONE,
    user_language: str = DEFAULT_LANGUAGE,
    personality_instruction: str | None = None,
    conversation_history: str = "(aucun historique)",
    window_size: int = 10,
) -> list:
    """Get the planner node prompt messages with pre-formatted dynamic data."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from src.core.config import get_settings

    settings = get_settings()

    planner_prompt_template = load_prompt(
        "planner_system_prompt", version=settings.planner_prompt_version
    )

    if response_schemas is None:
        response_schemas = ""

    default_personality = load_prompt("default_personality_prompt")

    formatted_system_prompt = planner_prompt_template.format(
        catalogue_json=catalogue_json,
        response_schemas=response_schemas,
        context_section=context_section,
        user_message=user_message,
        current_datetime=get_current_datetime_context(user_timezone, user_language),
        personnalite=personality_instruction or default_personality,
        user_language=user_language,
        conversation_history=conversation_history,
        window_size=window_size,
    )

    return [
        SystemMessage(content=formatted_system_prompt),
        HumanMessage(content=f"Generate ExecutionPlan for this query: {user_message}"),
    ]


# ============================
# HITL CLASSIFIER PROMPT
# ============================


def get_hitl_classifier_prompt(
    action_desc: str,
    response: str,
    user_timezone: str = DEFAULT_TIMEZONE,
    user_language: str = DEFAULT_LANGUAGE,
) -> str:
    """Get formatted HITL response classifier prompt from versioned file."""
    from src.core.config import get_settings

    settings = get_settings()

    hitl_prompt_template = load_prompt(
        "hitl_classifier_prompt", version=settings.hitl_classifier_prompt_version
    )

    return hitl_prompt_template.format(
        action_desc=action_desc,
        response=response,
        current_datetime=get_current_datetime_context(user_timezone, user_language),
    )


# ============================
# HITL ERROR & CLARIFICATION MESSAGES
# ============================

_HITL_CLASSIFICATION_FALLBACK_MESSAGES = {
    "fr": "Désolé, je n'ai pas bien compris. Peux-tu répondre par 'oui' pour confirmer ou 'non' pour annuler ?",
    "en": "Sorry, I didn't understand. Can you reply with 'yes' to confirm or 'no' to cancel?",
    "es": "Lo siento, no entendí bien. ¿Puedes responder 'sí' para confirmar o 'no' para cancelar?",
    "de": "Entschuldigung, ich habe nicht verstanden. Kannst du mit 'ja' bestätigen oder 'nein' abbrechen?",
    "it": "Scusa, non ho capito. Puoi rispondere 'sì' per confermare o 'no' per annullare?",
    "zh-CN": "抱歉，我没理解。请回复「是」确认或「否」取消。",
}

_HITL_CLARIFICATION_GENERIC_MESSAGES = {
    "fr": "Je ne suis pas sûr de comprendre. Confirmes-tu l'action (oui/non) ?",
    "en": "I'm not sure I understand. Do you confirm the action (yes/no)?",
    "es": "No estoy seguro de entender. ¿Confirmas la acción (sí/no)?",
    "de": "Ich bin mir nicht sicher, ob ich verstehe. Bestätigst du die Aktion (ja/nein)?",
    "it": "Non sono sicuro di aver capito. Confermi l'azione (sì/no)?",
    "zh-CN": "我不确定是否理解正确。请确认操作（是/否）？",
}


def get_hitl_classification_fallback_message(language: str = "fr") -> str:
    """Get HITL classification fallback message in user's language."""
    lang = language[:2] if len(language) > 2 and language != "zh-CN" else language
    return _HITL_CLASSIFICATION_FALLBACK_MESSAGES.get(
        lang, _HITL_CLASSIFICATION_FALLBACK_MESSAGES["fr"]
    )


def get_hitl_clarification_generic_message(language: str = "fr") -> str:
    """Get HITL clarification generic message in user's language."""
    lang = language[:2] if len(language) > 2 and language != "zh-CN" else language
    return _HITL_CLARIFICATION_GENERIC_MESSAGES.get(
        lang, _HITL_CLARIFICATION_GENERIC_MESSAGES["fr"]
    )


# Backward compatibility aliases
HITL_CLASSIFICATION_FALLBACK_MESSAGE = _HITL_CLASSIFICATION_FALLBACK_MESSAGES["fr"]
HITL_CLARIFICATION_GENERIC_MESSAGE = _HITL_CLARIFICATION_GENERIC_MESSAGES["fr"]


# ============================
# ERROR MESSAGES
# ============================

_ERROR_FALLBACK_MESSAGES = {
    "fr": {
        "with_node": "Désolé, une erreur s'est produite dans le nœud {node_name}. Pouvez-vous reformuler votre question ? (Error: {error_type})",
        "generic": "Désolé, une erreur s'est produite. Pouvez-vous reformuler votre question ? (Error: {error_type})",
    },
    "en": {
        "with_node": "Sorry, an error occurred in node {node_name}. Could you rephrase your question? (Error: {error_type})",
        "generic": "Sorry, an error occurred. Could you rephrase your question? (Error: {error_type})",
    },
    "es": {
        "with_node": "Lo siento, ocurrió un error en el nodo {node_name}. ¿Podrías reformular tu pregunta? (Error: {error_type})",
        "generic": "Lo siento, ocurrió un error. ¿Podrías reformular tu pregunta? (Error: {error_type})",
    },
    "de": {
        "with_node": "Entschuldigung, ein Fehler ist im Knoten {node_name} aufgetreten. Können Sie Ihre Frage umformulieren? (Error: {error_type})",
        "generic": "Entschuldigung, ein Fehler ist aufgetreten. Können Sie Ihre Frage umformulieren? (Error: {error_type})",
    },
    "it": {
        "with_node": "Scusa, si è verificato un errore nel nodo {node_name}. Puoi riformulare la tua domanda? (Error: {error_type})",
        "generic": "Scusa, si è verificato un errore. Puoi riformulare la tua domanda? (Error: {error_type})",
    },
    "zh-CN": {
        "with_node": "抱歉，节点 {node_name} 发生错误。请重新表述您的问题。(Error: {error_type})",
        "generic": "抱歉，发生了错误。请重新表述您的问题。(Error: {error_type})",
    },
}


def get_error_fallback_message(
    error_type: str, node_name: str | None = None, language: str = "fr"
) -> str:
    """Get standardized error message for node failures (i18n)."""
    lang = language[:2] if len(language) > 2 and language != "zh-CN" else language
    messages = _ERROR_FALLBACK_MESSAGES.get(lang, _ERROR_FALLBACK_MESSAGES["fr"])

    if node_name:
        return messages["with_node"].format(node_name=node_name, error_type=error_type)
    return messages["generic"].format(error_type=error_type)


def get_hitl_resumption_error_message(
    error: Exception, user_language: str = DEFAULT_LANGUAGE
) -> str:
    """Get error message for HITL resumption failures."""
    from typing import cast

    from src.domains.agents.api.error_messages import SSEErrorMessages, SupportedLanguage

    # Cast to SupportedLanguage (validated elsewhere, default to "fr" if invalid)
    lang = cast(
        SupportedLanguage,
        user_language if user_language in ("fr", "en", "es", "de", "it", "zh-CN") else "fr",
    )
    return SSEErrorMessages.hitl_resumption_error_simple(error=error, language=lang)


# ============================
# EXPORTS
# ============================

__all__ = [
    # From prompt_loader
    "PromptIntegrityError",
    "PromptLoadError",
    "PromptName",
    "PromptVersion",
    "calculate_prompt_hash",
    "get_available_versions",
    "get_prompt_metadata",
    "list_available_prompts",
    "load_prompt",
    "load_prompt_with_fallback",
    "validate_all_prompts",
    # Helpers
    "escape_braces",
    # Temporal context
    "DEFAULT_TIMEZONE",
    "format_with_current_datetime",
    "get_current_datetime_context",
    "get_period_of_day",
    "get_season",
    "is_weekend",
    # Prompt builders
    "get_response_prompt",
    "get_planner_prompt",
    "get_smart_planner_prompt",
    "get_smart_planner_multi_domain_prompt",
    "build_schema_reference_guide",
    "get_hitl_classifier_prompt",
    # HITL messages
    "get_hitl_classification_fallback_message",
    "get_hitl_clarification_generic_message",
    "HITL_CLASSIFICATION_FALLBACK_MESSAGE",
    "HITL_CLARIFICATION_GENERIC_MESSAGE",
    # Error messages
    "get_error_fallback_message",
    "get_hitl_resumption_error_message",
]
