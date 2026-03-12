"""
HTML Components for Modern Response Rendering.

Architecture v3 - Modern, Responsive, Class-based Design.

Components are viewport-aware and produce clean, semantic HTML
styled via CSS classes (lia-* namespace).

Design Principles:
- Modern card-based UI (shadows, rounded corners, gradients)
- Mobile-first responsive (adapts to viewport)
- CSS variables for theming (colors, spacing, dark mode ready)
- Semantic HTML5 (accessibility)
- BEM-like naming: lia-{component}__{element}--{modifier}

All styling is handled by frontend CSS (lia-components.css).
Components only produce the HTML structure with appropriate classes.
"""

from src.domains.agents.display.components.article_card import ArticleCard
from src.domains.agents.display.components.base import (
    BaseComponent,
    DateFormatType,
    RenderContext,
    Viewport,
    escape_html,
    format_date,
    format_email_body,
    format_full_date,
    format_phone,
    format_relative_date,
    html_to_text,
    truncate,
)
from src.domains.agents.display.components.contact_card import ContactCard
from src.domains.agents.display.components.email_card import EmailCard
from src.domains.agents.display.components.event_card import EventCard
from src.domains.agents.display.components.file_item import FileItem
from src.domains.agents.display.components.mcp_result_card import McpResultCard
from src.domains.agents.display.components.place_card import PlaceCard
from src.domains.agents.display.components.reminder_card import ReminderCard
from src.domains.agents.display.components.route_card import RouteCard
from src.domains.agents.display.components.search_result_card import SearchResultCard
from src.domains.agents.display.components.task_item import TaskItem
from src.domains.agents.display.components.weather_card import WeatherCard
from src.domains.agents.display.components.web_search_card import WebSearchCard

__all__ = [
    # Base
    "BaseComponent",
    "DateFormatType",
    "RenderContext",
    "Viewport",
    "escape_html",
    "format_date",
    "format_full_date",
    "format_phone",
    "format_relative_date",
    "truncate",
    # Domain Components
    "ContactCard",
    "EmailCard",
    "EventCard",
    "FileItem",
    "McpResultCard",
    "PlaceCard",
    "SearchResultCard",
    "TaskItem",
    "WeatherCard",
    "ArticleCard",
    "ReminderCard",
    "RouteCard",
    "WebSearchCard",
]
