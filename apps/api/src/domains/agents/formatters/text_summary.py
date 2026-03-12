"""
Text summary generation for LLM prompts.

This module provides functions for generating concise text summaries
of registry data for injection into LLM prompts. The summaries provide
context for intelligent LLM commenting while the actual data rendering
(HTML) is done after the LLM response via injection.

Usage:
    from src.domains.agents.formatters.text_summary import (
        generate_text_summary_for_llm,
        generate_data_for_filtering,
    )
"""

from typing import Any

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Domain labels by language for text summaries
# Keys must include CONTEXT_DOMAIN_* aliases (events, weathers, wikipedias, perplexitys)
DOMAIN_LABELS = {
    "fr": {
        "contacts": "Contact(s)",
        "emails": "Email(s)",
        "calendar": "Événement(s)",
        "calendars": "Agenda(s)",  # CONTEXT_DOMAIN_CALENDARS
        "events": "Événement(s)",  # CONTEXT_DOMAIN_EVENTS alias
        "places": "Lieu(x)",
        "locations": "Position(s)",  # CONTEXT_DOMAIN_LOCATION
        "tasks": "Tâche(s)",
        "files": "Fichier(s)",
        "drive": "Fichier(s)",
        "wikipedia": "Article(s)",
        "wikipedias": "Article(s)",  # CONTEXT_DOMAIN_WIKIPEDIA alias
        "perplexity": "Résultat(s)",
        "perplexitys": "Résultat(s)",  # CONTEXT_DOMAIN_PERPLEXITY alias
        "search": "Résultat(s)",
        "braves": "Résultat(s) Brave",  # CONTEXT_DOMAIN_BRAVE
        "querys": "Résultat(s)",  # CONTEXT_DOMAIN_QUERY
        "weather": "Météo",
        "weathers": "Météo",  # CONTEXT_DOMAIN_WEATHER alias
        "web_search": "Recherche(s) web",
        "web_searchs": "Recherche(s) web",  # CONTEXT_DOMAIN_WEB_SEARCH alias
        "web_fetch": "Page(s) web",  # CONTEXT_DOMAIN_WEB_FETCH
        "web_fetchs": "Page(s) web",  # CONTEXT_DOMAIN_WEB_FETCH alias
        "reminders": "Rappel(s)",  # CONTEXT_DOMAIN_REMINDERS
        "routes": "Itinéraire(s)",
        "mcps": "Résultat(s) MCP",  # CONTEXT_DOMAIN_MCP
        "mcp_apps": "Application(s) MCP",  # CONTEXT_DOMAIN_MCP_APPS
        "other": "Élément(s)",
    },
    "en": {
        "contacts": "Contact(s)",
        "emails": "Email(s)",
        "calendar": "Event(s)",
        "calendars": "Calendar(s)",  # CONTEXT_DOMAIN_CALENDARS
        "events": "Event(s)",  # CONTEXT_DOMAIN_EVENTS alias
        "places": "Place(s)",
        "locations": "Location(s)",  # CONTEXT_DOMAIN_LOCATION
        "tasks": "Task(s)",
        "files": "File(s)",
        "drive": "File(s)",
        "wikipedia": "Article(s)",
        "wikipedias": "Article(s)",  # CONTEXT_DOMAIN_WIKIPEDIA alias
        "perplexity": "Result(s)",
        "perplexitys": "Result(s)",  # CONTEXT_DOMAIN_PERPLEXITY alias
        "search": "Result(s)",
        "braves": "Brave result(s)",  # CONTEXT_DOMAIN_BRAVE
        "querys": "Result(s)",  # CONTEXT_DOMAIN_QUERY
        "weather": "Weather",
        "weathers": "Weather",  # CONTEXT_DOMAIN_WEATHER alias
        "web_search": "Web search(es)",
        "web_searchs": "Web search(es)",  # CONTEXT_DOMAIN_WEB_SEARCH alias
        "web_fetch": "Web page(s)",  # CONTEXT_DOMAIN_WEB_FETCH
        "web_fetchs": "Web page(s)",  # CONTEXT_DOMAIN_WEB_FETCH alias
        "reminders": "Reminder(s)",  # CONTEXT_DOMAIN_REMINDERS
        "routes": "Route(s)",
        "mcps": "MCP result(s)",  # CONTEXT_DOMAIN_MCP
        "mcp_apps": "MCP app(s)",  # CONTEXT_DOMAIN_MCP_APPS
        "other": "Item(s)",
    },
    "es": {
        "contacts": "Contacto(s)",
        "emails": "Correo(s)",
        "calendar": "Evento(s)",
        "calendars": "Calendario(s)",
        "events": "Evento(s)",
        "places": "Lugar(es)",
        "locations": "Ubicación(es)",
        "tasks": "Tarea(s)",
        "files": "Archivo(s)",
        "drive": "Archivo(s)",
        "wikipedia": "Artículo(s)",
        "wikipedias": "Artículo(s)",
        "perplexity": "Resultado(s)",
        "perplexitys": "Resultado(s)",
        "search": "Resultado(s)",
        "braves": "Resultado(s) Brave",
        "querys": "Resultado(s)",
        "weather": "Clima",
        "weathers": "Clima",
        "web_search": "Búsqueda(s) web",
        "web_searchs": "Búsqueda(s) web",
        "web_fetch": "Página(s) web",
        "web_fetchs": "Página(s) web",
        "reminders": "Recordatorio(s)",
        "routes": "Ruta(s)",
        "mcps": "Resultado(s) MCP",
        "mcp_apps": "Aplicación(es) MCP",
        "other": "Elemento(s)",
    },
    "de": {
        "contacts": "Kontakt(e)",
        "emails": "E-Mail(s)",
        "calendar": "Termin(e)",
        "calendars": "Kalender",
        "events": "Termin(e)",
        "places": "Ort(e)",
        "locations": "Standort(e)",
        "tasks": "Aufgabe(n)",
        "files": "Datei(en)",
        "drive": "Datei(en)",
        "wikipedia": "Artikel",
        "wikipedias": "Artikel",
        "perplexity": "Ergebnis(se)",
        "perplexitys": "Ergebnis(se)",
        "search": "Ergebnis(se)",
        "braves": "Brave-Ergebnis(se)",
        "querys": "Ergebnis(se)",
        "weather": "Wetter",
        "weathers": "Wetter",
        "web_search": "Websuche(n)",
        "web_searchs": "Websuche(n)",
        "web_fetch": "Webseite(n)",
        "web_fetchs": "Webseite(n)",
        "reminders": "Erinnerung(en)",
        "routes": "Route(n)",
        "mcps": "MCP-Ergebnis(se)",
        "mcp_apps": "MCP-App(s)",
        "other": "Element(e)",
    },
    "it": {
        "contacts": "Contatto/i",
        "emails": "Email",
        "calendar": "Evento/i",
        "calendars": "Calendario/i",
        "events": "Evento/i",
        "places": "Luogo/hi",
        "locations": "Posizione/i",
        "tasks": "Attività",
        "files": "File",
        "drive": "File",
        "wikipedia": "Articolo/i",
        "wikipedias": "Articolo/i",
        "perplexity": "Risultato/i",
        "perplexitys": "Risultato/i",
        "search": "Risultato/i",
        "braves": "Risultato/i Brave",
        "querys": "Risultato/i",
        "weather": "Meteo",
        "weathers": "Meteo",
        "web_search": "Ricerca/che web",
        "web_searchs": "Ricerca/che web",
        "web_fetch": "Pagina/e web",
        "web_fetchs": "Pagina/e web",
        "reminders": "Promemoria",
        "routes": "Percorso/i",
        "mcps": "Risultato/i MCP",
        "mcp_apps": "App MCP",
        "other": "Elemento/i",
    },
    "zh": {
        "contacts": "联系人",
        "emails": "邮件",
        "calendar": "日程",
        "calendars": "日历",
        "events": "日程",
        "places": "地点",
        "locations": "位置",
        "tasks": "任务",
        "files": "文件",
        "drive": "文件",
        "wikipedia": "文章",
        "wikipedias": "文章",
        "perplexity": "结果",
        "perplexitys": "结果",
        "search": "结果",
        "braves": "Brave结果",
        "querys": "结果",
        "weather": "天气",
        "weathers": "天气",
        "web_search": "网页搜索",
        "web_searchs": "网页搜索",
        "web_fetch": "网页",
        "web_fetchs": "网页",
        "reminders": "提醒",
        "routes": "路线",
        "mcps": "MCP结果",
        "mcp_apps": "MCP应用",
        "other": "项目",
    },
}


def generate_text_summary_for_items(
    items: list[dict[str, Any]],
    domain: str,
    user_language: str = "fr",
) -> str:
    """
    Generate concise text summary for raw items (not registry format).

    Used for resolved_context items which are raw payloads.
    Provides full data context for intelligent LLM commenting.

    Note: Optimized for voice synthesis - data available early for TTS trigger.

    Args:
        items: List of item dicts (raw payloads)
        domain: Domain type (contacts, emails, etc.)
        user_language: Language code

    Returns:
        Concise text summary with data details for LLM
    """
    if not items:
        return ""

    from src.domains.agents.display.llm_serializer import payload_to_text

    # Generate text summaries using generic serializer
    summaries = []
    for item in items:
        if isinstance(item, dict):
            text_summary = payload_to_text(item)
            if text_summary:
                summaries.append(text_summary)

    if not summaries:
        labels = DOMAIN_LABELS.get(user_language, DOMAIN_LABELS["en"])
        return f"{len(items)} {labels['other']}"

    labels = DOMAIN_LABELS.get(user_language, DOMAIN_LABELS["en"])
    label = labels.get(domain, labels["other"])
    count = len(summaries)

    # Include data details for intelligent LLM commenting
    items_text = "\n".join(f"  - {s}" for s in summaries)
    return f"**{count} {label}:**\n{items_text}"


def generate_text_summary_for_llm(
    data_registry: dict[str, Any] | None,
    user_language: str = "fr",
) -> str:
    """
    Generate a concise text summary for the LLM prompt.

    This function creates a detailed summary of the data that the LLM can use
    to generate intelligent conversational comments. The actual data rendering
    (HTML) is done AFTER the LLM via injection.

    Architecture V3.1:
    - LLM receives: Full data context for intelligent commenting
    - LLM generates: Brief, relevant comments based on actual data
    - HTML injection: <div class="lia-card">...</div> (added post-LLM)

    Note: Optimized for voice synthesis - data available early for TTS trigger.

    Args:
        data_registry: Registry dict with items
        user_language: Language code for summary

    Returns:
        Concise text summary with data details for LLM context
    """
    if not data_registry:
        return ""

    from src.domains.agents.display.llm_serializer import payload_to_text
    from src.domains.agents.utils.type_domain_mapping import get_result_key_from_type

    # Group items by result key (pluriel) for DOMAIN_LABELS lookup
    domain_items: dict[str, list[str]] = {}

    for _item_id, item in data_registry.items():
        # Handle both dict and Pydantic RegistryItem
        if hasattr(item, "type"):
            item_type = item.type.value if hasattr(item.type, "value") else str(item.type)
            payload = item.payload if hasattr(item, "payload") else {}
        else:
            item_type = item.get("type", "")
            if hasattr(item_type, "value"):
                item_type = item_type.value
            payload = item.get("payload", {})

        # Skip DRAFT and MCP_APP items (interactive widgets rendered in iframe,
        # not useful for LLM text commentary — payload contains html_content/tool_result)
        if item_type in ("DRAFT", "MCP_APP"):
            continue

        # Generate text summary using generic serializer
        text_summary = payload_to_text(payload) if payload else ""

        domain = get_result_key_from_type(item_type) or "other"

        if domain not in domain_items:
            domain_items[domain] = []
        if text_summary:
            domain_items[domain].append(text_summary)

    if not domain_items:
        return ""

    labels = DOMAIN_LABELS.get(user_language, DOMAIN_LABELS["en"])
    parts = []

    for domain, summaries in domain_items.items():
        label = labels.get(domain, labels["other"])
        count = len(summaries)
        # Include data details for intelligent LLM commenting
        items_text = "\n".join(f"  - {s}" for s in summaries)
        parts.append(f"**{count} {label}:**\n{items_text}")

    return "\n\n".join(parts)


def generate_data_for_filtering(
    data_registry: dict[str, Any] | None,
    user_language: str = "fr",
) -> str:
    """
    Generate enriched data summary for LLM context (filtering + commenting).

    Uses the generic payload serializer to create a detailed view of registry items.
    Each line includes:
    - Item ID for filtering (LLM returns relevant IDs in <relevant_ids> tag)
    - Full data details for intelligent commenting (emails, phones, addresses, etc.)

    This replaces the previous dual injection of {data_for_filtering} and {agent_results}.

    Format: [item_id] Name | email addresses: x@y.com | phone numbers: +33...

    Args:
        data_registry: Registry dict with items
        user_language: Language code for labels

    Returns:
        Formatted string with item IDs and full data details
    """
    if not data_registry:
        return ""

    from src.domains.agents.display.llm_serializer import payload_to_text

    lines: list[str] = []

    for item_id, item in data_registry.items():
        try:
            # Handle both dict and Pydantic RegistryItem
            if hasattr(item, "type"):
                item_type = item.type.value if hasattr(item.type, "value") else str(item.type)
                payload = item.payload if hasattr(item, "payload") else {}
            else:
                item_type = item.get("type", "")
                if hasattr(item_type, "value"):
                    item_type = item_type.value
                payload = item.get("payload", {})

            # Skip DRAFT and MCP_APP items (interactive widgets rendered in iframe,
            # not useful for LLM filtering — payload contains html_content/tool_result)
            if item_type in ("DRAFT", "MCP_APP"):
                continue

            # Use generic serializer for full data details
            text_summary = payload_to_text(payload) if payload else ""
            if text_summary:
                lines.append(f"[{item_id}] {text_summary}")
            else:
                # Fallback for empty payloads
                lines.append(f"[{item_id}] (données non disponibles)")

        except (ValueError, KeyError, TypeError, AttributeError) as e:
            # Log error but continue with other items
            logger.warning(
                "generate_data_for_filtering_item_error",
                item_id=item_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            continue

    return "\n".join(lines)
