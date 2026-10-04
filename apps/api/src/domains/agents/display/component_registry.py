"""Exhaustive presentation decisions; result keys remain owned by the tool contract."""

from dataclasses import dataclass
from typing import Literal

from src.domains.agents.data_registry.models import RegistryItemType as Kind
from src.domains.agents.display.components.article_card import ArticleCard
from src.domains.agents.display.components.base import BaseComponent
from src.domains.agents.display.components.calendar_card import CalendarCard
from src.domains.agents.display.components.contact_card import ContactCard
from src.domains.agents.display.components.email_card import EmailCard
from src.domains.agents.display.components.event_card import EventCard
from src.domains.agents.display.components.file_item import FileItem
from src.domains.agents.display.components.location_card import LocationCard
from src.domains.agents.display.components.mcp_app_sentinel import McpAppSentinel
from src.domains.agents.display.components.mcp_result_card import McpResultCard
from src.domains.agents.display.components.place_card import PlaceCard
from src.domains.agents.display.components.reminder_card import ReminderCard
from src.domains.agents.display.components.route_card import RouteCard
from src.domains.agents.display.components.search_result_card import SearchResultCard
from src.domains.agents.display.components.skill_app_sentinel import SkillAppSentinel
from src.domains.agents.display.components.snapshot_cards import (
    HueLightCard,
    TicketCard,
)
from src.domains.agents.display.components.task_item import TaskItem
from src.domains.agents.display.components.weather_card import WeatherCard
from src.domains.agents.display.components.web_search_card import WebSearchCard
from src.domains.agents.tools.output import REGISTRY_TYPE_TO_KEY


@dataclass(frozen=True)
class Presentation:
    mode: Literal["card", "inline", "widget", "inactive"]
    component: type[BaseComponent] | None = None
    aliases: tuple[str, ...] = ()
    data_keys: tuple[str, ...] = ()
    reason: str = ""


PRESENTATIONS: dict[Kind, Presentation] = {
    Kind.CONTACT: Presentation("card", ContactCard, data_keys=("contacts", "items", "results")),
    Kind.EMAIL: Presentation("card", EmailCard, data_keys=("emails", "messages", "items")),
    Kind.EVENT: Presentation("card", EventCard, ("calendar",)),
    Kind.CALENDAR: Presentation("card", CalendarCard),
    Kind.TASK: Presentation("card", TaskItem),
    Kind.FILE: Presentation("card", FileItem, ("drive",)),
    Kind.PLACE: Presentation("card", PlaceCard, data_keys=("places", "results", "items")),
    Kind.LOCATION: Presentation("card", LocationCard),
    Kind.ROUTE: Presentation("card", RouteCard, data_keys=("route", "routes", "items")),
    Kind.WEATHER: Presentation(
        "card", WeatherCard, ("weather",), ("forecasts", "weather", "items")
    ),
    Kind.WIKIPEDIA_ARTICLE: Presentation(
        "card", ArticleCard, ("wikipedia", "articles"), ("articles", "items", "results")
    ),
    Kind.SEARCH_RESULT: Presentation(
        "card", SearchResultCard, ("perplexity", "search", "braves", "querys"), ("results", "items")
    ),
    Kind.WEB_SEARCH: Presentation("card", WebSearchCard, ("web_search",), ("results", "items")),
    Kind.REMINDER: Presentation("card", ReminderCard),
    Kind.MCP_RESULT: Presentation(
        "card", McpResultCard, data_keys=("mcps", "mcp_results", "items")
    ),
    Kind.HUE_LIGHT: Presentation("card", HueLightCard),
    Kind.TICKET: Presentation("card", TicketCard),
    Kind.NOTE: Presentation(
        "inline",
        reason="Authorized RAG excerpts use the existing ephemeral document result preview, not the final card registry.",
    ),
    Kind.MCP_APP: Presentation(
        "widget", McpAppSentinel, reason="Existing authenticated interactive app flow."
    ),
    Kind.SKILL_APP: Presentation(
        "widget", SkillAppSentinel, reason="Existing rich-output sentinel and sandbox flow."
    ),
    Kind.DRAFT: Presentation("widget", reason="Approval belongs to the existing HITL flow."),
    Kind.WEB_PAGE: Presentation(
        "inline",
        reason="Fetched page is evidence for the synthesized answer, not a duplicate content card.",
    ),
    Kind.BROWSER_PAGE: Presentation(
        "inline", reason="The accessibility tree is model evidence, never a user-facing raw tree."
    ),
    Kind.CHART: Presentation(
        "inactive", reason="No registry producer; charts use the existing skill rich-output flow."
    ),
    Kind.CALENDAR_SLOT: Presentation(
        "inactive",
        reason="No registry producer; calendar availability is currently returned by the tool in text.",
    ),
}


def build_components() -> tuple[dict[str, BaseComponent], dict[str, list[str]]]:
    """Each component instance is shared by its compatibility aliases."""
    components: dict[str, BaseComponent] = {}
    data_keys: dict[str, list[str]] = {}
    for kind, presentation in PRESENTATIONS.items():
        if presentation.component is None:
            continue
        canonical = REGISTRY_TYPE_TO_KEY[kind]
        component = presentation.component()
        for key in (canonical, *presentation.aliases):
            components[key] = component
            keys = presentation.data_keys or (canonical, "items")
            data_keys[key] = list(dict.fromkeys((*keys, canonical)))
    return components, data_keys
