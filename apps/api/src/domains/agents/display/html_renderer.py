"""
HTML Renderer - Modern Response Rendering Engine.

Orchestrates all components to render tool outputs as modern HTML.
Supports single domain, multi-domain, and nested (hierarchical) data.

Architecture v3 - Intelligence, Autonomy, Relevance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.core.config import settings
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.article_card import ArticleCard
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    Viewport,
)
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
from src.domains.agents.display.components.task_item import TaskItem
from src.domains.agents.display.components.weather_card import WeatherCard
from src.domains.agents.display.components.web_search_card import WebSearchCard
from src.domains.agents.display.config import (
    DisplayConfig,
    separator_simple,
)
from src.domains.agents.display.config import (
    Viewport as ViewportEnum,
)
from src.domains.agents.display.icons import Icons, icon
from src.domains.agents.orchestration.correlation_detector import CorrelatedCluster


@dataclass
class NestedData:
    """
    Represents hierarchical/nested data structure.

    Example: Contact → Emails from that contact
             Weather → Places to visit → Restaurants nearby
    """

    domain: str
    items: list[dict[str, Any]]
    children: list[NestedData] = field(default_factory=list)
    relation: str = ""  # "emails_from", "places_nearby", etc.


class HtmlRenderer:
    """
    Modern HTML rendering engine.

    Responsibilities:
    1. Route data to appropriate component
    2. Handle multi-domain rendering
    3. Support nested/hierarchical data
    4. Generate responsive HTML
    5. Add conversational sandwich (intro/outro)

    Usage:
        renderer = HtmlRenderer()
        html = renderer.render(
            domain="contacts",
            data={"contacts": [...]},
            config=display_config,
        )
    """

    def __init__(self) -> None:
        # Domain to component mapping
        # Keys must match CONTEXT_DOMAIN_* constants (result_key pattern)
        self._components: dict[str, BaseComponent] = {
            "contacts": ContactCard(),
            "emails": EmailCard(),
            "calendar": EventCard(),
            "calendars": EventCard(),  # CONTEXT_DOMAIN_CALENDARS (calendar list items)
            "events": EventCard(),
            "tasks": TaskItem(),
            "places": PlaceCard(),
            "locations": LocationCard(),  # CONTEXT_DOMAIN_LOCATION (GPS position)
            "weather": WeatherCard(),
            "weathers": WeatherCard(),  # CONTEXT_DOMAIN_WEATHER alias
            "drive": FileItem(),
            "files": FileItem(),
            "wikipedia": ArticleCard(),
            "wikipedias": ArticleCard(),  # CONTEXT_DOMAIN_WIKIPEDIA alias
            "articles": ArticleCard(),
            "perplexity": SearchResultCard(),
            "perplexitys": SearchResultCard(),  # CONTEXT_DOMAIN_PERPLEXITY alias
            "search": SearchResultCard(),
            "braves": SearchResultCard(),  # CONTEXT_DOMAIN_BRAVE alias
            "querys": SearchResultCard(),  # CONTEXT_DOMAIN_QUERY
            "web_search": WebSearchCard(),
            "web_searchs": WebSearchCard(),  # CONTEXT_DOMAIN_WEB_SEARCH alias
            # web_fetch: No card — content is inline in the LLM response text
            "reminders": ReminderCard(),
            "routes": RouteCard(),
            "mcps": McpResultCard(),  # CONTEXT_DOMAIN_MCP (evolution F2.3)
            "mcp_apps": McpAppSentinel(),  # CONTEXT_DOMAIN_MCP_APPS (evolution F2.5)
            "skill_apps": SkillAppSentinel(),  # CONTEXT_DOMAIN_SKILL_APPS (skill rich outputs)
        }

        # Domain to data key mapping
        # Keys must match CONTEXT_DOMAIN_* constants (result_key pattern)
        self._data_keys: dict[str, list[str]] = {
            "contacts": ["contacts", "items", "results"],
            "emails": ["emails", "messages", "items"],
            "calendar": ["events", "items"],
            "calendars": ["calendars", "items"],  # CONTEXT_DOMAIN_CALENDARS
            "events": ["events", "items"],
            "tasks": ["tasks", "items"],
            "places": ["places", "results", "items"],
            "locations": ["locations", "items"],  # CONTEXT_DOMAIN_LOCATION
            "weather": ["forecasts", "weather", "items"],
            "weathers": ["forecasts", "weather", "items"],  # CONTEXT_DOMAIN_WEATHER alias
            "drive": ["files", "items"],
            "files": ["files", "items"],
            "wikipedia": ["articles", "items", "results"],
            "wikipedias": ["articles", "items", "results"],  # CONTEXT_DOMAIN_WIKIPEDIA alias
            "articles": ["articles", "items"],
            "perplexity": ["results", "items"],
            "perplexitys": ["results", "items"],  # CONTEXT_DOMAIN_PERPLEXITY alias
            "search": ["results", "items"],
            "braves": ["results", "items"],  # CONTEXT_DOMAIN_BRAVE alias
            "querys": ["results", "items"],  # CONTEXT_DOMAIN_QUERY
            "web_search": ["results", "items"],
            "web_searchs": ["results", "items"],  # CONTEXT_DOMAIN_WEB_SEARCH alias
            # web_fetch: No card — content is inline in the LLM response text
            "reminders": ["reminders", "items"],
            "routes": ["route", "routes", "items"],
            "mcps": ["mcps", "mcp_results", "items"],
            "mcp_apps": ["mcp_apps", "items"],
            "skill_apps": ["skill_apps", "items"],
        }

    def render(
        self,
        domain: str,
        data: dict[str, Any],
        config: DisplayConfig,
    ) -> str:
        """
        Render data for a single domain (mono-domain).

        Separator pattern:
            ─────────────────────────── (bold)
            [card]
            [card]
            [card]
            ─────────────────────────── (bold)

        Args:
            domain: Domain name (contacts, emails, etc.)
            data: Structured data dict from tool output
            config: Display configuration

        Returns:
            HTML string
        """
        ctx = self._build_context(config)
        items = self._extract_items(domain, data)

        if not items:
            return self._render_empty(domain, ctx)

        component = self._get_component(domain)
        if not component:
            # Domain has no registered card component — skip rendering entirely.
            # This is intentional for domains like web_fetch where content is
            # inline in the LLM response text and doesn't need a visual card.
            return ""

        # Mono-domain: cards handle their own separators via render_list()
        # First card gets top bold separator, last card gets bottom bold separator
        return component.render_list(items, ctx)

    def render_multi(
        self,
        domains_data: dict[str, dict[str, Any]],
        config: DisplayConfig,
    ) -> str:
        """
        Render multiple domains together (multi-domain non-cluster).

        Separator pattern (all simple, no summary header):
            ─────────────────────────── (simple)
            📅 Événements (2)
            ─────────────────────────── (simple)
            [card]
            [card]
            ─────────────────────────── (simple)
            🚗 Itinéraire (2)
            ─────────────────────────── (simple)
            [card]
            [card]
            ─────────────────────────── (simple)

        Args:
            domains_data: Dict of domain -> data
            config: Display configuration

        Returns:
            HTML string with all domains
        """
        ctx = self._build_context(config)

        # Render each domain section with simple separators
        sections = []
        domain_list = list(domains_data.items())
        for _idx, (domain, data) in enumerate(domain_list):
            items = self._extract_items(domain, data)
            if not items:
                continue

            component = self._get_component(domain)
            if component:
                # Render cards without separators (managed at section level)
                cards_html, rendered_count = self._render_cards_without_separators(
                    component, items, ctx
                )
                # Skip section if all cards were filtered out (e.g., routes with no destination)
                if rendered_count == 0:
                    continue
                # Use DRY helper for section with standard separator pattern
                section = self._render_domain_section(domain, cards_html, ctx, rendered_count)
                sections.append(section)

        sections_html = "\n".join(sections)

        # Final simple separator at the end
        return f"""<div class="lia-multi-domain lia--{ctx.viewport.value}">
  <div class="lia-sections">
    {sections_html}
  </div>
  {separator_simple()}
</div>"""

    def render_correlated(
        self,
        clusters: list[CorrelatedCluster],
        uncorrelated: dict[str, list[dict[str, Any]]],
        config: DisplayConfig,
    ) -> str:
        """
        Render correlated clusters with uncorrelated items.

        Separator pattern (all simple, uncorrelated domains first, then clusters):
            ─────────────────────────── (simple)
            🌤️ Météo (1)
            ─────────────────────────── (simple)
            [card weather]
            ─────────────────────────── (simple)
            📅 Événements / 🚗 Itinéraire   <-- Combined cluster title
            ─────────────────────────── (simple)
            [card cluster 1: event + route]
            ─────────────────────────── (simple)
            [card cluster 2: event + route]
            ─────────────────────────── (simple)

        Correlated items (e.g., Event + Route pairs) are rendered together
        in clusters. Uncorrelated items are rendered by domain first.

        Args:
            clusters: List of CorrelatedCluster (from correlation_detector)
            uncorrelated: Dict of domain -> items for standard rendering
            config: Display configuration

        Returns:
            HTML string with uncorrelated sections then correlated clusters
        """
        ctx = self._build_context(config)
        html_parts: list[str] = []

        # 1. Render uncorrelated domains first (same pattern as render_multi)
        for domain, items in uncorrelated.items():
            if not items:
                continue
            component = self._get_component(domain)
            if component:
                # Render cards without separators (managed at section level)
                cards_html, rendered_count = self._render_cards_without_separators(
                    component, items, ctx
                )
                # Skip section if all cards were filtered out
                if rendered_count == 0:
                    continue
                # Use DRY helper for section with standard separator pattern
                html_parts.append(
                    self._render_domain_section(domain, cards_html, ctx, rendered_count)
                )

        # 2. Add combined title for correlated clusters (icon + domain1 / icon + domain2 / ...)
        if clusters:
            cluster_title = self._build_cluster_title(clusters, ctx.language)
            html_parts.append(f"""{separator_simple()}
<div class="lia-section lia-section--cluster">
  <h3 class="lia-section__title">{cluster_title}</h3>
  {separator_simple()}
</div>""")

        # 3. Render correlated clusters (first cluster has no separator - already in title section)
        for idx, cluster in enumerate(clusters):
            cluster_parts: list[str] = []

            # Build flat list of (component, payload)
            items_to_render: list[tuple[BaseComponent, dict[str, Any]]] = []

            # Parent item first
            parent_component = self._get_component(cluster.parent_domain)
            if parent_component:
                items_to_render.append((parent_component, cluster.parent_item or {}))

            # Child items - each is a (domain, payload) tuple
            for child_domain, child_payload in cluster.child_items:
                child_component = self._get_component(child_domain)
                if child_component:
                    items_to_render.append((child_component, child_payload or {}))

            # Render cards WITHOUT separators (handled at cluster level)
            for component, payload in items_to_render:
                item_html = self._render_single_card_without_separator(component, payload, ctx)
                # Filter out empty cards (e.g., routes with no destination)
                if item_html.strip():
                    cluster_parts.append(item_html)

            if cluster_parts:
                cluster_html = "\n  ".join(cluster_parts)

                # Cluster: separator before (except first - already in title section)
                separator = separator_simple() if idx > 0 else ""
                html_parts.append(f"""{separator}
<div class="lia-cluster" data-cluster-id="{cluster.cluster_id}">
  {cluster_html}
</div>""")

        if not html_parts:
            return ""

        all_html = "\n".join(html_parts)
        # Final simple separator at the end
        return f"""<div class="lia-correlated lia--{ctx.viewport.value}">
  {all_html}
  {separator_simple()}
</div>"""

    def render_nested(
        self,
        nested_data: NestedData,
        config: DisplayConfig,
    ) -> str:
        """
        Render hierarchical/nested data.

        Example: Contact X with their 3 latest emails

        Args:
            nested_data: NestedData structure
            config: Display configuration

        Returns:
            HTML string with nested structure
        """
        ctx = self._build_context(config)
        return self._render_nested_recursive(nested_data, ctx)

    def render_nested_list(
        self,
        nested_items: list[NestedData],
        config: DisplayConfig,
    ) -> str:
        """
        Render a list of nested data structures.

        Example: Multiple contacts, each with their emails

        Args:
            nested_items: List of NestedData
            config: Display configuration

        Returns:
            HTML string
        """
        ctx = self._build_context(config)
        parts = [self._render_nested_recursive(item, ctx) for item in nested_items]
        return f"""<div class="lia-nested-list lia--{ctx.viewport.value}">
  {chr(10).join(parts)}
</div>"""

    def _render_nested_recursive(
        self,
        nested: NestedData,
        ctx: RenderContext,
    ) -> str:
        """Recursively render nested data."""
        component = self._get_component(nested.domain)
        if not component:
            return ""

        # Render parent items
        parent_html = component.render_list(nested.items, ctx)

        # Render children if present
        children_html = ""
        if nested.children:
            # Increase nesting level for children
            child_ctx = RenderContext(
                viewport=ctx.viewport,
                language=ctx.language,
                timezone=ctx.timezone,
                show_secondary=ctx.show_secondary,
                max_items=ctx.max_items,
                nested_level=ctx.nested_level + 1,
                parent_domain=nested.domain,
            )

            child_parts = []
            for child in nested.children:
                child_parts.append(self._render_nested_recursive(child, child_ctx))

            children_html = f"""<div class="lia-nested__children" data-relation="{nested.relation}">
  {chr(10).join(child_parts)}
</div>"""

        return f"""<div class="lia-nested lia-nested--{nested.domain}" data-level="{ctx.nested_level}">
  <div class="lia-nested__parent">
    {parent_html}
  </div>
  {children_html}
</div>"""

    def _build_context(self, config: DisplayConfig) -> RenderContext:
        """Build render context from display config."""
        viewport_map = {
            ViewportEnum.MOBILE: Viewport.MOBILE,
            ViewportEnum.TABLET: Viewport.TABLET,
            ViewportEnum.DESKTOP: Viewport.DESKTOP,
        }
        return RenderContext(
            viewport=viewport_map.get(config.viewport, Viewport.DESKTOP),
            language=config.language,
            timezone=config.timezone,
            show_secondary=config.show_secondary_metadata,
            max_items=config.max_items_per_domain,
        )

    def _render_domain_section(
        self,
        domain: str,
        cards_html: str,
        ctx: RenderContext,
        item_count: int,
    ) -> str:
        """
        Render a domain section with standard separator pattern.

        Pattern:
            ─────────────────────────── (simple)
            📅 Domain Label
            ─────────────────────────── (simple)
            [cards]

        Used by render_multi() and render_correlated() for consistent section rendering.
        DRY: Extracts common section rendering logic.

        Note: item_count kept in signature for backwards compatibility but not displayed.

        Args:
            domain: Domain name (e.g., "events", "routes")
            cards_html: Pre-rendered cards HTML
            ctx: Render context
            item_count: Number of items (not displayed, kept for compatibility)

        Returns:
            HTML string for the section with separators
        """
        domain_label = self._get_domain_label(domain, ctx.language)

        return f"""{separator_simple()}
<div class="lia-section" data-domain="{domain}">
  <h3 class="lia-section__title">{domain_label}</h3>
  {separator_simple()}
  <div class="lia-section__cards">
    {cards_html}
  </div>
</div>"""

    def _render_cards_without_separators(
        self,
        component: BaseComponent,
        items: list[dict[str, Any]],
        ctx: RenderContext,
    ) -> tuple[str, int]:
        """
        Render cards without individual separators.

        Used by render_multi() and render_correlated() where separators
        are managed at section/cluster level, not at card level.

        Args:
            component: Component to render items with
            items: List of item payloads to render
            ctx: Render context

        Returns:
            Tuple of (HTML string of all cards joined by newlines, count of rendered cards)
            Empty cards (from validation failures) are filtered out.
        """
        card_parts = []
        for item in items[: ctx.max_items]:
            card_html = self._render_single_card_without_separator(component, item, ctx)
            # Filter out empty cards (e.g., routes with no destination)
            if card_html.strip():
                card_parts.append(card_html)
        return "\n".join(card_parts), len(card_parts)

    def _render_single_card_without_separator(
        self,
        component: BaseComponent,
        payload: dict[str, Any],
        ctx: RenderContext,
    ) -> str:
        """
        Render a single card without separators.

        Used internally by _render_cards_without_separators() and render_correlated()
        for consistent separator-free card rendering.

        Args:
            component: Component to render with
            payload: Item payload to render
            ctx: Render context

        Returns:
            HTML string of the card without separators
        """
        return component.render(  # type: ignore[call-arg]
            payload,
            ctx,
            is_first_item=False,  # No card-level separators
            is_last_item=False,
        )

    def _extract_items(self, domain: str, data: dict[str, Any]) -> list[dict]:
        """Extract items list from data dict."""
        if isinstance(data, list):
            return data

        # Try domain-specific keys
        keys = self._data_keys.get(domain, ["items", "results"])
        for key in keys:
            if key in data:
                value = data[key]
                if isinstance(value, list):
                    return value
                # Handle single dict item (e.g., route: {...} for routes domain)
                elif isinstance(value, dict):
                    return [value]

        # Single item case
        if "id" in data or "name" in data or "title" in data:
            return [data]

        return []

    def _get_component(self, domain: str) -> BaseComponent | None:
        """Get component for domain."""
        return self._components.get(domain)

    def _get_domain_label(self, domain: str, language: str = settings.default_language) -> str:
        """
        Get human-readable domain label with icon.

        Args:
            domain: Domain key (e.g., "contacts", "events", "routes")
            language: Language code for i18n (e.g., "fr", "en")

        Returns:
            Icon + translated label (e.g., "👤 Contacts", "📅 Événements")
        """
        # Map domains to icon names (str values from Icons class constants)
        # Keys must include CONTEXT_DOMAIN_* aliases (weathers, wikipedias, perplexitys)
        domain_icons: dict[str, str] = {
            "contacts": Icons.PERSON,
            "emails": Icons.EMAIL,
            "calendar": Icons.CALENDAR,
            "events": Icons.CALENDAR,
            "tasks": Icons.TASK,
            "places": Icons.LOCATION,
            "weather": Icons.SUNNY,
            "weathers": Icons.SUNNY,  # CONTEXT_DOMAIN_WEATHER alias
            "drive": Icons.FOLDER,
            "files": Icons.FOLDER,
            "wikipedia": Icons.ARTICLE,
            "wikipedias": Icons.ARTICLE,  # CONTEXT_DOMAIN_WIKIPEDIA alias
            "articles": Icons.ARTICLE,  # Wikipedia articles alias
            "perplexity": Icons.SEARCH,
            "perplexitys": Icons.SEARCH,  # CONTEXT_DOMAIN_PERPLEXITY alias
            "search": Icons.SEARCH,
            "braves": Icons.WEB,  # CONTEXT_DOMAIN_BRAVE alias
            "web_search": Icons.SEARCH,
            "web_searchs": Icons.SEARCH,  # CONTEXT_DOMAIN_WEB_SEARCH alias
            "reminders": Icons.REMINDER,
            "routes": Icons.ROUTE,
            "mcps": Icons.EXTENSION,  # MCP results (evolution F2.3)
            "mcp_apps": Icons.EXTENSION,  # MCP Apps (evolution F2.5)
        }

        # Get translated label from i18n
        label = V3Messages.get_domain_section_label(domain, language)

        if domain in domain_icons:
            icon_name = domain_icons[domain]
            return f"{icon(icon_name)} {label}"
        return label

    def _build_cluster_title(
        self,
        clusters: list[CorrelatedCluster],
        language: str = settings.default_language,
    ) -> str:
        """
        Build combined title for correlated clusters.

        Format: "icon + domain1 / icon + domain2 / ..."
        Dynamically includes all unique domains from clusters.

        Args:
            clusters: List of CorrelatedCluster
            language: Language code for i18n

        Returns:
            Combined title string with icons and domain labels separated by " / "
        """
        # Collect all unique domains from clusters (parent + all children)
        # Use dict to preserve insertion order (Python 3.7+)
        unique_domains: dict[str, None] = {}

        for cluster in clusters:
            unique_domains[cluster.parent_domain] = None
            for child_domain, _ in cluster.child_items:
                unique_domains[child_domain] = None

        # Build title: "icon + label / icon + label / ..."
        domain_labels = [
            self._get_domain_label(domain, language) for domain in unique_domains.keys()
        ]

        return " / ".join(domain_labels)

    def _render_empty(self, domain: str, ctx: RenderContext) -> str:
        """Render empty state."""
        no_results_text = V3Messages.get_no_results(ctx.language)
        return f"""<div class="lia-empty lia--{ctx.viewport.value}">
  <span class="lia-empty__icon">{icon(Icons.SEARCH)}</span>
  <span class="lia-empty__text">{no_results_text}</span>
</div>"""

    def _render_fallback(self, items: list[dict], ctx: RenderContext) -> str:
        """Render fallback for unknown domains."""
        lines = []
        for item in items[: ctx.max_items]:
            title = item.get("title") or item.get("name") or item.get("summary", "")
            url = item.get("url") or item.get("link", "")
            if url:
                lines.append(f'<div class="lia-fallback__item"><a href="{url}">{title}</a></div>')
            else:
                lines.append(f'<div class="lia-fallback__item">{title}</div>')

        return f"""<div class="lia-fallback lia--{ctx.viewport.value}">
  {chr(10).join(lines)}
</div>"""


# Singleton instance
_renderer: HtmlRenderer | None = None


def get_html_renderer() -> HtmlRenderer:
    """Get singleton HtmlRenderer instance."""
    global _renderer
    if _renderer is None:
        _renderer = HtmlRenderer()
    return _renderer


def reset_html_renderer() -> None:
    """Reset renderer for testing."""
    global _renderer
    _renderer = None
