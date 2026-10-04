"""
RouteCard Component - Modern Route/Directions Display v3.0.

Renders route information with:
- Travel mode badge with icon
- Duration and distance prominently displayed
- Traffic conditions indicator
- Origin and destination addresses
- Waypoints (if any)
- Collapsible turn-by-turn steps
- Action button to open in Google Maps

Mobile-first design with compact layout optimized for smartphone screens.
"""

from __future__ import annotations

from typing import Any

from src.core.i18n import resolve_language
from src.core.i18n_drafts import label_separator
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    escape_html,
    render_card_top,
    render_chip,
    render_chip_row,
    render_d_row,
    wrap_with_response,
)
from src.domains.agents.display.components.map_hero import render_map_hero
from src.domains.agents.display.components.route_journey import (
    render_route_alternatives,
    render_route_details,
    render_route_steps,
    render_route_tolls,
    render_waypoint_links,
    route_summary,
)
from src.domains.agents.display.components.route_map import render_route_map
from src.domains.agents.display.icons import (
    Icons,
    get_travel_mode_icon,
    icon,
)
from src.domains.agents.display.urls import build_route_url
from src.domains.agents.display.values import (
    list_values,
    nonnegative_integer,
    nonnegative_number,
    scalar_text,
)


class RouteCard(BaseComponent):
    """
    Modern route card component v3.0.

    Design (Mobile-First):
    - Header: Travel mode icon + "Origin → Destination"
    - Primary info: Duration (large) + Distance badge
    - Traffic badge (if available)
    - Route modifiers badges (tolls, highways, ferries avoided)
    - Collapsible turn-by-turn steps
    - Action button: Open in Maps
    """

    # Traffic condition colors
    TRAFFIC_CLASS = {
        "NORMAL": "lia-badge--success",
        "LIGHT": "lia-badge--success",
        "MODERATE": "lia-badge--warning",
        "HEAVY": "lia-badge--error",
    }

    def render(
        self,
        data: dict[str, Any],
        ctx: RenderContext,
        assistant_comment: str | None = None,
        suggested_actions: list[dict[str, str]] | None = None,
        with_wrapper: bool = True,
        is_first_item: bool = True,
        is_last_item: bool = True,
    ) -> str:
        """
        Render route as modern card with wrapper.

        Args:
            data: Route data from get_route_tool output
            ctx: Render context (viewport, language, timezone)
            assistant_comment: Optional comment from assistant above card
            suggested_actions: Optional action buttons below card
            with_wrapper: Whether to wrap with response zones
            is_first_item: If True, add top separator
            is_last_item: If True, add bottom separator

        Returns:
            HTML string for the route card
        """
        # Extract route data (support both nested and flat structures)
        nested = data.get("route")
        route = nested if isinstance(nested, dict) else data

        # Validation: don't render if destination is missing
        # This handles multi-domain cases where route depends on another domain
        # that couldn't provide an address
        destination = scalar_text(route.get("destination"))
        if not destination:
            return ""

        origin = scalar_text(route.get("origin"))
        travel_mode = scalar_text(route.get("travel_mode", "DRIVE"))
        distance_km = nonnegative_number(route.get("distance_km"))
        duration_minutes = nonnegative_integer(route.get("duration_minutes"))
        duration_formatted = scalar_text(route.get("duration_formatted"))
        duration_in_traffic = nonnegative_integer(route.get("duration_in_traffic_minutes"))
        traffic_conditions = scalar_text(route.get("traffic_conditions"))
        steps = list_values(route.get("steps"))
        maps_url = scalar_text(route.get("maps_url"))
        waypoints = [
            value for value in list_values(route.get("waypoints")) if isinstance(value, str)
        ]

        # Route modifiers
        avoid_tolls = route.get("avoid_tolls") is True
        avoid_highways = route.get("avoid_highways") is True
        avoid_ferries = route.get("avoid_ferries") is True

        # New features: static map, toll info, ETA
        static_map_url = scalar_text(route.get("static_map_url"))
        toll_info = route.get("toll_info") if isinstance(route.get("toll_info"), dict) else None
        eta_formatted = scalar_text(route.get("eta_formatted"))

        # Arrival-based route fields (for calendar event routing)
        is_arrival_based = route.get("is_arrival_based") is True
        target_arrival_formatted = scalar_text(route.get("target_arrival_formatted"))
        suggested_departure_formatted = scalar_text(route.get("suggested_departure_formatted"))

        # Format duration if not provided
        if not duration_formatted and duration_minutes is not None:
            duration_formatted = self._format_duration(duration_minutes, ctx.language)

        # Build maps URL if not provided
        if not maps_url and destination:
            maps_url = build_route_url(
                origin,
                destination,
                travel_mode,
                waypoints,
                avoid_tolls=avoid_tolls,
                avoid_highways=avoid_highways,
                avoid_ferries=avoid_ferries,
            )
        if len(waypoints) > 3:
            maps_url = ""

        # Build default actions if not provided
        if suggested_actions is None:
            suggested_actions = self._build_default_actions(maps_url, ctx)

        # Unified render - CSS handles responsive adaptation
        card_html = self._render_card(
            origin,
            destination,
            travel_mode,
            distance_km,
            duration_minutes,
            duration_formatted,
            duration_in_traffic,
            traffic_conditions,
            steps,
            waypoints,
            avoid_tolls,
            avoid_highways,
            avoid_ferries,
            maps_url,
            static_map_url,
            toll_info,
            eta_formatted,
            is_arrival_based,
            target_arrival_formatted,
            suggested_departure_formatted,
            ctx,
            route,
        )

        # Wrap with response zones if requested
        if with_wrapper:
            return wrap_with_response(
                card_html=card_html,
                assistant_comment=assistant_comment,
                suggested_actions=suggested_actions,
                domain="route",
                with_top_separator=is_first_item,
                with_bottom_separator=is_last_item,
            )
        return card_html

    def _build_default_actions(self, maps_url: str, ctx: RenderContext) -> list[dict[str, str]]:
        """Build default action buttons for route."""
        actions = []

        if maps_url:
            actions.append(
                {
                    "icon": Icons.MAP,
                    "label": V3Messages.get_open_in_maps(ctx.language),
                    "url": maps_url,
                }
            )

        return actions

    def _render_card(
        self,
        origin: str,
        destination: str,
        travel_mode: str,
        distance_km: float | None,
        duration_minutes: int | None,
        duration_formatted: str,
        duration_in_traffic: int | None,
        traffic_conditions: str,
        steps: list[object],
        waypoints: list[str],
        avoid_tolls: bool,
        avoid_highways: bool,
        avoid_ferries: bool,
        maps_url: str,
        static_map_url: str,
        toll_info: dict[str, object] | None,
        eta_formatted: str,
        is_arrival_based: bool,
        target_arrival_formatted: str,
        suggested_departure_formatted: str,
        ctx: RenderContext,
        data: dict[str, Any],
    ) -> str:
        """Unified route card using Design System v4 components."""
        nested_class = self._nested_class(ctx)

        # --- Static map image (uses existing lia-route__map CSS for full-width) ---
        hero_html = ""
        if static_map_url:
            hero_html = render_map_hero(
                static_map_url,
                maps_url,
                linked_alt=V3Messages.get_open_in_maps(ctx.language),
                plain_alt=V3Messages.get_route_label(ctx.language),
            )
        hero_html = render_route_map(data.get("route_map"), hero_html)

        # --- Card top: travel mode icon + "Origin → Destination" ---
        mode_icon = get_travel_mode_icon(travel_mode)
        # Traffic condition determines illus color
        traffic_color_map = {
            "NORMAL": "green",
            "LIGHT": "green",
            "MODERATE": "amber",
            "HEAVY": "red",
        }
        illus_color = traffic_color_map.get(traffic_conditions, "green")
        # Title: just "→ Destination" (origin shown in endpoints below)
        route_title = f"→ {escape_html(str(destination))}"
        title_html = f'<span class="lia-card-top__title">{route_title}</span>'
        card_top_html = render_card_top(mode_icon, illus_color, title_html)

        # --- Chip row 1: arrival + suggested departure ---
        chips_row1 = []
        if eta_formatted:
            eta_label = V3Messages.get_arrival_time(ctx.language)
            chips_row1.append(render_chip(f"{eta_label} {eta_formatted}", "indigo", Icons.SCHEDULE))
        if is_arrival_based and suggested_departure_formatted:
            departure_label = V3Messages.get_suggested_departure(ctx.language)
            departure_time = suggested_departure_formatted
            chips_row1.append(
                render_chip(f"{departure_label} {departure_time}", "amber", Icons.SCHEDULE)
            )
        chip_row_1 = render_chip_row(" ".join(chips_row1)) if chips_row1 else ""

        # --- Chip row 2: traffic + duration + distance + avoidances (with separator below) ---
        chips_row2 = []
        if traffic_conditions:
            traffic_label = V3Messages.get_traffic_condition(ctx.language, traffic_conditions)
            traffic_variant = {
                "NORMAL": "green",
                "LIGHT": "green",
                "MODERATE": "amber",
                "HEAVY": "red",
            }.get(traffic_conditions, "")
            chips_row2.append(render_chip(traffic_label, traffic_variant, "traffic"))
        if avoid_tolls:
            chips_row2.append(
                render_chip(V3Messages.get_route_avoidance(ctx.language, "tolls"), "", Icons.TOLL)
            )
        if avoid_highways:
            chips_row2.append(
                render_chip(
                    V3Messages.get_route_avoidance(ctx.language, "highways"), "", Icons.HIGHWAY
                )
            )
        if avoid_ferries:
            chips_row2.append(
                render_chip(
                    V3Messages.get_route_avoidance(ctx.language, "ferries"), "", Icons.FERRY
                )
            )
        chip_row_2 = render_chip_row(" ".join(chips_row2)) if chips_row2 else ""

        # --- Toll info ---
        extra_rows = []
        if toll_info and not list_values(data.get("toll_estimates")):
            toll_formatted = scalar_text(toll_info.get("formatted"))
            if toll_formatted:
                toll_label = V3Messages.get_toll_label(ctx.language)
                extra_rows.append(
                    render_d_row(
                        Icons.TOLL,
                        f"{toll_label}{label_separator(ctx.language)}{escape_html(toll_formatted)}",
                    )
                )
        extra_html = "\n".join(extra_rows)

        # --- Endpoints (preserved existing structure) ---
        origin_label = V3Messages.get_origin(ctx.language)
        dest_label = V3Messages.get_destination_label(ctx.language)

        waypoints_html = ""
        if waypoints:
            via_label = V3Messages.get_via(ctx.language)
            waypoint_items = [
                f'<span class="lia-route__waypoint">{escape_html(wp)}</span>' for wp in waypoints
            ]
            waypoints_html = f'<div class="lia-route__waypoints">{icon(Icons.FLAG_START, size="sm")} {via_label}{label_separator(ctx.language)}{", ".join(waypoint_items)}</div>'

        # Collapsible steps (preserved existing format)
        collapsible_html = render_route_details(data, ctx) + render_route_alternatives(
            data.get("alternatives"), ctx
        )

        return f"""<div class="lia-card lia-route {nested_class}">
{hero_html}
{card_top_html}
{route_summary(data, duration_formatted, ctx)}
{chip_row_1}
{chip_row_2}
{extra_html}
{render_route_tolls(data.get("toll_estimates"), ctx)}
<div class="lia-route__endpoints">
<div class="lia-route__endpoint">
<span class="lia-route__endpoint-icon">{icon(Icons.FLAG_START, size="sm", domain="route")}</span>
<div class="lia-route__endpoint-content">
<span class="lia-route__endpoint-label">{origin_label}</span>
<span class="lia-route__endpoint-value">{escape_html(origin) if origin else V3Messages.get_my_location(ctx.language)}</span>
</div>
</div>
{waypoints_html}
{render_waypoint_links(data, ctx) if len(waypoints) > 3 else ""}
<div class="lia-route__endpoint">
<span class="lia-route__endpoint-icon">{icon(Icons.FLAG_END, size="sm", domain="route")}</span>
<div class="lia-route__endpoint-content">
<span class="lia-route__endpoint-label">{dest_label}</span>
<span class="lia-route__endpoint-value">{escape_html(str(destination))}</span>
</div>
</div>
</div>
{collapsible_html}
</div>"""

    def _render_collapsible_steps(self, steps: object, ctx: RenderContext) -> str:
        return render_route_steps(steps, ctx)

    def _format_duration(self, minutes: int, language: str | None = None) -> str:
        """Format duration in minutes to human-readable string."""
        language = resolve_language(language)
        if minutes < 60:
            if language == "en":
                return f"{minutes} min"
            elif language == "de":
                return f"{minutes} Min."
            elif language == "zh-CN":
                return f"{minutes}分钟"
            else:
                return f"{minutes} min"

        hours = minutes // 60
        remaining_minutes = minutes % 60

        if language == "en":
            if remaining_minutes:
                return f"{hours}h {remaining_minutes}min"
            return f"{hours}h"
        elif language == "de":
            if remaining_minutes:
                return f"{hours} Std. {remaining_minutes} Min."
            return f"{hours} Std."
        elif language == "zh-CN":
            if remaining_minutes:
                return f"{hours}小时{remaining_minutes}分钟"
            return f"{hours}小时"
        else:
            # French, Spanish, Italian
            if remaining_minutes:
                return f"{hours}h{remaining_minutes:02d}"
            return f"{hours}h"

    def _build_route_url(
        self, origin: str, destination: str, travel_mode: str, waypoints: list[str] | None = None
    ) -> str:
        return build_route_url(origin, destination, travel_mode, waypoints)
