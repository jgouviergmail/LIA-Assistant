"""Agent builders (LangChain v1)."""

from src.domains.agents.graphs.brave_agent_builder import build_brave_agent
from src.domains.agents.graphs.calendar_agent_builder import build_calendar_agent
from src.domains.agents.graphs.contacts_agent_builder import build_contacts_agent
from src.domains.agents.graphs.drive_agent_builder import build_drive_agent
from src.domains.agents.graphs.emails_agent_builder import build_emails_agent
from src.domains.agents.graphs.health_agent_builder import build_health_agent
from src.domains.agents.graphs.hue_agent_builder import build_hue_agent
from src.domains.agents.graphs.perplexity_agent_builder import build_perplexity_agent
from src.domains.agents.graphs.places_agent_builder import build_places_agent
from src.domains.agents.graphs.query_agent_builder import build_query_agent
from src.domains.agents.graphs.routes_agent_builder import build_routes_agent
from src.domains.agents.graphs.tasks_agent_builder import build_tasks_agent
from src.domains.agents.graphs.weather_agent_builder import build_weather_agent
from src.domains.agents.graphs.web_fetch_agent_builder import build_web_fetch_agent
from src.domains.agents.graphs.web_search_agent_builder import build_web_search_agent
from src.domains.agents.graphs.wikipedia_agent_builder import build_wikipedia_agent

__all__ = [
    # OAuth agents (Google)
    "build_contacts_agent",
    "build_emails_agent",
    "build_calendar_agent",
    "build_drive_agent",
    "build_tasks_agent",
    # API key agents
    "build_weather_agent",
    "build_wikipedia_agent",
    "build_perplexity_agent",
    "build_brave_agent",
    "build_web_search_agent",
    "build_web_fetch_agent",
    "build_places_agent",
    "build_routes_agent",
    # Smart Home agents
    "build_hue_agent",
    # Internal agents (no external API)
    "build_query_agent",
    # Health Metrics agent (v1.17.2)
    "build_health_agent",
]
