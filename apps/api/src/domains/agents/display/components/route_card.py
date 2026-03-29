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

from src.core.config import settings
from src.core.constants import (
    STATIC_MAP_DESKTOP_HEIGHT,
    STATIC_MAP_DESKTOP_WIDTH,
)
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    escape_html,
    render_card_top,
    render_chip,
    render_chip_row,
    render_collapsible,
    render_d_row,
    wrap_with_response,
)
from src.domains.agents.display.icons import (
    Icons,
    get_travel_mode_icon,
    icon,
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
        route = data.get("route", data)

        # Validation: don't render if destination is missing
        # This handles multi-domain cases where route depends on another domain
        # that couldn't provide an address
        destination = route.get("destination", "")
        if not destination:
            return ""

        origin = route.get("origin", "")
        travel_mode = route.get("travel_mode", "DRIVE")
        distance_km = route.get("distance_km", 0)
        duration_minutes = route.get("duration_minutes", 0)
        duration_formatted = route.get("duration_formatted", "")
        duration_in_traffic = route.get("duration_in_traffic_minutes")
        traffic_conditions = route.get("traffic_conditions", "")
        steps = route.get("steps", [])
        maps_url = route.get("maps_url", "")
        waypoints = route.get("waypoints", [])

        # Route modifiers
        avoid_tolls = route.get("avoid_tolls", False)
        avoid_highways = route.get("avoid_highways", False)
        avoid_ferries = route.get("avoid_ferries", False)

        # New features: static map, toll info, ETA
        static_map_url = route.get("static_map_url", "")
        toll_info = route.get("toll_info")
        eta_formatted = route.get("eta_formatted", "")

        # Arrival-based route fields (for calendar event routing)
        is_arrival_based = route.get("is_arrival_based", False)
        target_arrival_formatted = route.get("target_arrival_formatted", "")
        suggested_departure_formatted = route.get("suggested_departure_formatted", "")

        # Format duration if not provided
        if not duration_formatted and duration_minutes:
            duration_formatted = self._format_duration(duration_minutes, ctx.language)

        # Build maps URL if not provided
        if not maps_url and destination:
            maps_url = self._build_route_url(origin, destination, travel_mode, waypoints)

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
        distance_km: float,
        duration_minutes: int,
        duration_formatted: str,
        duration_in_traffic: int | None,
        traffic_conditions: str,
        steps: list,
        waypoints: list,
        avoid_tolls: bool,
        avoid_highways: bool,
        avoid_ferries: bool,
        maps_url: str,
        static_map_url: str,
        toll_info: dict | None,
        eta_formatted: str,
        is_arrival_based: bool,
        target_arrival_formatted: str,
        suggested_departure_formatted: str,
        ctx: RenderContext,
    ) -> str:
        """Unified route card using Design System v4 components."""
        nested_class = self._nested_class(ctx)

        # --- Static map image (uses existing lia-route__map CSS for full-width) ---
        hero_html = ""
        if static_map_url:
            map_url = f"{static_map_url}&width={STATIC_MAP_DESKTOP_WIDTH}&height={STATIC_MAP_DESKTOP_HEIGHT}"
            map_img = (
                f'<img src="{escape_html(map_url)}" alt="Route map" '
                f'class="lia-route__map-image" loading="lazy" />'
            )
            if maps_url:
                hero_html = (
                    f'<a href="{escape_html(maps_url)}" target="_blank" rel="noopener" '
                    f'class="lia-route__map-link">{map_img}</a>'
                )
            else:
                hero_html = f'<div class="lia-route__map">{map_img}</div>'

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
            import re as _re

            time_match = _re.search(r"\d{1,2}:\d{2}", suggested_departure_formatted)
            departure_time = time_match.group(0) if time_match else suggested_departure_formatted
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
        if duration_formatted:
            chips_row2.append(render_chip(duration_formatted, "green", "timer"))
        if distance_km:
            distance_str = (
                f"{distance_km:.1f} km" if distance_km >= 1 else f"{int(distance_km * 1000)} m"
            )
            chips_row2.append(render_chip(distance_str, "", "straighten"))
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
        if toll_info and not avoid_tolls:
            toll_formatted = toll_info.get("formatted", "")
            if toll_formatted:
                toll_label = V3Messages.get_toll_label(ctx.language)
                extra_rows.append(
                    render_d_row(Icons.TOLL, f"{toll_label}: {escape_html(toll_formatted)}")
                )
        extra_html = "\n".join(extra_rows)

        # --- Endpoints (preserved existing structure) ---
        origin_label = V3Messages.get_origin(ctx.language)
        dest_label = V3Messages.get_destination_label(ctx.language)

        waypoints_html = ""
        if waypoints:
            via_label = V3Messages.get_via(ctx.language)
            waypoint_items = [
                f'<span class="lia-route__waypoint">{escape_html(wp)}</span>'
                for wp in waypoints[:5]
            ]
            waypoints_html = f'<div class="lia-route__waypoints">{icon(Icons.FLAG_START, size="sm")} {via_label}: {", ".join(waypoint_items)}</div>'

        # Collapsible steps (preserved existing format)
        collapsible_html = self._render_collapsible_steps(steps, ctx)

        return f"""<div class="lia-card lia-route {nested_class}">
{hero_html}
{card_top_html}
{chip_row_1}
{chip_row_2}
{extra_html}
<div class="lia-route__endpoints">
<div class="lia-route__endpoint">
<span class="lia-route__endpoint-icon">{icon(Icons.FLAG_START, size="sm", domain="route")}</span>
<div class="lia-route__endpoint-content">
<span class="lia-route__endpoint-label">{origin_label}</span>
<span class="lia-route__endpoint-value">{escape_html(origin) if origin else V3Messages.get_my_location(ctx.language)}</span>
</div>
</div>
{waypoints_html}
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

    def _render_collapsible_steps(self, steps: list, ctx: RenderContext) -> str:
        """Render collapsible turn-by-turn steps section."""
        if not steps:
            return ""

        # Limit steps for readability (configurable via settings.routes_max_steps env var)
        steps_to_show = steps[: settings.routes_max_steps]

        step_items = []
        for i, step in enumerate(steps_to_show, 1):
            if isinstance(step, dict):
                instruction = step.get(
                    "instruction", step.get("navigationInstruction", {}).get("instructions", "")
                )
                distance = step.get("distance_meters", step.get("distanceMeters", 0))
                transit = step.get("transit")
                step_mode = step.get("travel_mode", "")

                if distance:
                    distance_km = distance / 1000
                    distance_str = (
                        f"{distance_km:.1f} km" if distance_km >= 1 else f"{int(distance)} m"
                    )
                else:
                    distance_str = ""

                # Build step content based on type
                if transit:
                    # Transit step: show colored line badge
                    step_html = self._render_transit_step(
                        i, transit, instruction, distance_str, ctx
                    )
                elif step_mode == "WALK":
                    # Walking step
                    step_html = self._render_walk_step(i, instruction, distance_str)
                else:
                    # Regular step
                    step_html = self._render_regular_step(i, instruction, distance_str)
            else:
                instruction = str(step)
                step_html = self._render_regular_step(i, instruction, "")

            step_items.append(step_html)

        # Add "more steps" indicator if truncated
        if len(steps) > settings.routes_max_steps:
            remaining = len(steps) - settings.routes_max_steps
            more_steps_label = V3Messages.get_more_steps(ctx.language, remaining)
            step_items.append(
                f'<div class="lia-route__step lia-route__step--more">'
                f'<span class="lia-route__step-more">{more_steps_label}</span>'
                f"</div>"
            )

        steps_label = V3Messages.get_route_steps(ctx.language)
        content_html = f'<div class="lia-route__steps">{"".join(step_items)}</div>'

        return render_collapsible(
            trigger_text=f"{steps_label} ({len(steps)})",
            content_html=content_html,
            initially_open=False,
            language=ctx.language,
        )

    def _render_transit_step(
        self, step_num: int, transit: dict, instruction: str, distance_str: str, ctx: RenderContext
    ) -> str:
        """Render a transit step with colored line badge."""
        line_name = transit.get("line_name", "")
        line_color = transit.get("line_color", "")
        line_text_color = transit.get("line_text_color", "")
        vehicle_type = transit.get("vehicle_type", "")
        headsign = transit.get("headsign", "")
        departure_stop = transit.get("departure_stop", "")
        arrival_stop = transit.get("arrival_stop", "")
        stop_count = transit.get("stop_count", 0)

        # Get vehicle icon based on type
        vehicle_icon = self._get_transit_vehicle_icon(vehicle_type)

        # Build line badge with actual line color
        style = ""
        if line_color:
            # Google returns colors like "#FFFFFF" or "FFFFFF"
            bg_color = line_color if line_color.startswith("#") else f"#{line_color}"
            text_color = line_text_color if line_text_color else "#FFFFFF"
            if not text_color.startswith("#"):
                text_color = f"#{text_color}"
            style = f'style="background-color: {bg_color}; color: {text_color};"'

        line_badge = (
            (
                f'<span class="lia-route__transit-badge" {style}>'
                f'{icon(vehicle_icon, size="xs", color="inherit")} {escape_html(line_name)}'
                f"</span>"
            )
            if line_name
            else ""
        )

        # Build stops info
        stops_info = ""
        if departure_stop and arrival_stop:
            stops_info = f'<span class="lia-route__transit-stops">{escape_html(departure_stop)} → {escape_html(arrival_stop)}</span>'

        # Stop count (localized with singular/plural handling)
        stop_count_html = ""
        if stop_count:
            stops_label = V3Messages.get_transit_stops(ctx.language, stop_count)
            stop_count_html = f'<span class="lia-route__transit-count">{stops_label}</span>'

        # Headsign (direction)
        headsign_html = ""
        if headsign:
            headsign_html = (
                f'<span class="lia-route__transit-headsign">→ {escape_html(headsign)}</span>'
            )

        return f"""<div class="lia-route__step lia-route__step--transit">
<span class="lia-route__step-number">{step_num}</span>
<div class="lia-route__step-content">
<div class="lia-route__transit-header">{line_badge}{headsign_html}</div>
{stops_info}
{stop_count_html}
</div>
</div>"""

    def _render_walk_step(self, step_num: int, instruction: str, distance_str: str) -> str:
        """Render a walking step."""
        distance_html = (
            f'<span class="lia-route__step-distance">{distance_str}</span>' if distance_str else ""
        )
        return f"""<div class="lia-route__step lia-route__step--walk">
<span class="lia-route__step-number">{step_num}</span>
<div class="lia-route__step-content">
<span class="lia-route__step-icon">{icon(Icons.WALK, size="xs")}</span>
<span class="lia-route__step-instruction">{escape_html(instruction)}</span>
{distance_html}
</div>
</div>"""

    def _render_regular_step(self, step_num: int, instruction: str, distance_str: str) -> str:
        """Render a regular navigation step."""
        distance_html = (
            f'<span class="lia-route__step-distance">{distance_str}</span>' if distance_str else ""
        )
        return f"""<div class="lia-route__step">
<span class="lia-route__step-number">{step_num}</span>
<span class="lia-route__step-instruction">{escape_html(instruction)}</span>
{distance_html}
</div>"""

    def _get_transit_vehicle_icon(self, vehicle_type: str) -> str:
        """Get the appropriate icon for a transit vehicle type."""
        vehicle_icons = {
            "BUS": Icons.TRANSIT,
            "SUBWAY": Icons.TRANSIT,
            "RAIL": Icons.TRANSIT,
            "HEAVY_RAIL": Icons.TRANSIT,
            "COMMUTER_TRAIN": Icons.TRANSIT,
            "HIGH_SPEED_TRAIN": Icons.TRANSIT,
            "LONG_DISTANCE_TRAIN": Icons.TRANSIT,
            "LIGHT_RAIL": Icons.TRANSIT,
            "METRO_RAIL": Icons.TRANSIT,
            "MONORAIL": Icons.TRANSIT,
            "TRAM": Icons.TRANSIT,
            "TROLLEYBUS": Icons.TRANSIT,
            "CABLE_CAR": Icons.TRANSIT,
            "FUNICULAR": Icons.TRANSIT,
            "FERRY": Icons.FERRY,
            "SHARE_TAXI": Icons.CAR,
            "OTHER": Icons.TRANSIT,
        }
        return (
            vehicle_icons.get(vehicle_type.upper(), Icons.TRANSIT)
            if vehicle_type
            else Icons.TRANSIT
        )

    def _format_duration(self, minutes: int, language: str = "fr") -> str:
        """Format duration in minutes to human-readable string."""
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
        self,
        origin: str,
        destination: str,
        travel_mode: str,
        waypoints: list | None = None,
    ) -> str:
        """Build Google Maps directions URL."""
        from urllib.parse import quote

        # Travel mode mapping for Google Maps
        mode_map = {
            "DRIVE": "driving",
            "WALK": "walking",
            "BICYCLE": "bicycling",
            "TRANSIT": "transit",
            "TWO_WHEELER": "driving",  # No specific mode, use driving
        }
        gm_mode = mode_map.get(travel_mode.upper(), "driving")

        # Build URL
        params = [
            "api=1",
            f"destination={quote(destination, safe='')}",
            f"travelmode={gm_mode}",
        ]

        if origin:
            params.append(f"origin={quote(origin, safe='')}")

        if waypoints:
            waypoints_str = "|".join(quote(wp, safe="") for wp in waypoints[:5])
            params.append(f"waypoints={waypoints_str}")

        return f"https://www.google.com/maps/dir/?{'&'.join(params)}"
