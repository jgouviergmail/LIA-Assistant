"""
LocationCard Component - Current Location Address Label.

Renders the user's current GPS position with:
- Static map and Street View, with an optional admitted dynamic map
- A locality heading and complete received address
- Country and postal code
- A labeled coordinate strip
- Google Maps link

Created: 2026-04-08
"""

from __future__ import annotations

from typing import Any

from src.core.i18n_cards import card_label
from src.core.i18n_v3 import V3Messages
from src.domains.agents.constants import CONTEXT_DOMAIN_LOCATION
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    build_directions_url,
    escape_html,
    render_card_top,
    render_chip,
    render_chip_row,
    safe_url,
    wrap_with_response,
)
from src.domains.agents.display.components.location_map import (
    location_map_point,
    render_location_map,
)
from src.domains.agents.display.components.map_hero import render_map_hero
from src.domains.agents.display.icons import Icons
from src.domains.agents.display.values import scalar_text
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class LocationCard(BaseComponent):
    """Location card for current GPS position.

    Renders LocationItem payload (formatted_address, locality, country,
    postal_code, latitude, longitude, static_map_url) from
    get_current_location_tool.
    """

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
        """Render current location as a card.

        Args:
            data: LocationItem payload (formatted_address, locality, country,
                  postal_code, latitude, longitude, static_map_url).
            ctx: Render context (viewport, language, timezone).
            assistant_comment: Optional comment from assistant above card.
            suggested_actions: Optional action buttons below card.
            with_wrapper: Whether to wrap with response zones.
            is_first_item: Whether this is the first item in a list.
            is_last_item: Whether this is the last item in a list.

        Returns:
            HTML string for the location card.
        """
        address = scalar_text(data.get("formatted_address"))
        locality = scalar_text(data.get("locality"))
        country = scalar_text(data.get("country"))
        postal_code = scalar_text(data.get("postal_code"))
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        static_map_url = scalar_text(data.get("static_map_url"))

        # Use the source's locality; never infer a street number or a town.
        display_name = locality or address or V3Messages.get_position(ctx.language)

        # Google Maps URL
        point = location_map_point(latitude, longitude)
        if point is not None:
            maps_url = f"https://www.google.com/maps/@{point.lat},{point.lng},15z"
        elif address:
            maps_url = build_directions_url(address)
        else:
            maps_url = ""

        # Build default actions
        if suggested_actions is None:
            suggested_actions = []
            if maps_url:
                suggested_actions.append(
                    {
                        "icon": Icons.MAP,
                        "label": V3Messages.get_directions(ctx.language),
                        "url": maps_url,
                    }
                )

        # --- Static map hero image (same pattern as RouteCard) ---
        hero_html = ""
        if static_map_url:
            hero_html = render_map_hero(
                static_map_url,
                maps_url,
                linked_alt=V3Messages.get_open_in_maps(ctx.language),
                plain_alt=display_name,
            )
        hero_html = render_location_map(point, display_name, address, hero_html)

        # --- Street View thumbnail (lot SV, 2026-08) ---
        # Only present when the producer confirmed imagery exists (free
        # metadata check) — the map shows WHERE, this shows WHAT it looks like.
        street_view_url = scalar_text(data.get("street_view_url"))
        if street_view_url:
            street_view_img = (
                f'<img src="{safe_url(street_view_url)}" alt="Street View" '
                f'class="lia-route__map-image" loading="lazy" />'
            )
            hero_html += f'<div class="lia-route__map">{street_view_img}</div>'

        # --- Address label: shared icon/title geometry, with a navigation stamp ---
        title_html = escape_html(display_name)
        if maps_url:
            title_html = (
                f'<a href="{safe_url(maps_url)}"'
                f' target="_blank">{escape_html(display_name)}</a>'
            )
        title_html = f'<h3 class="lia-card-top__title">{title_html}</h3>'
        card_top = render_card_top("navigation", "blue", title_html)

        # The locality is already shown whole in the heading.
        chips = []
        if country:
            chips.append(render_chip(country, "", "public"))
        if postal_code:
            chips.append(render_chip(postal_code, "", "pin_drop"))
        chip_row = render_chip_row(" ".join(chips)) if chips else ""

        # Keep the complete source address, including any number it contains.
        address_html = ""
        if address:
            addr_link = escape_html(address)
            if maps_url:
                addr_link = (
                    f'<a href="{safe_url(maps_url)}" target="_blank">' f"{escape_html(address)}</a>"
                )
            address_html = f'<p class="lia-location__address">{addr_link}</p>'

        # --- Coordinates ---
        coords_html = ""
        if point is not None:
            coords_html = (
                '<div class="lia-location__coordinates"><dl>'
                f'<div><dt>{escape_html(card_label("latitude", ctx.language))}</dt>'
                f"<dd>{point.lat:.6f}</dd></div>"
                f'<div><dt>{escape_html(card_label("longitude", ctx.language))}</dt>'
                f"<dd>{point.lng:.6f}</dd></div></dl>"
                '<span class="material-symbols-outlined" aria-hidden="true">'
                "my_location</span></div>"
            )

        nested_class = self._nested_class(ctx)

        card_html = f"""<div class="lia-card lia-place lia-location {nested_class}">
{hero_html}
<div class="lia-location__label">
{card_top}
{address_html}
{chip_row}
{coords_html}
</div>
</div>"""

        if with_wrapper:
            return wrap_with_response(
                card_html=card_html,
                assistant_comment=assistant_comment,
                suggested_actions=suggested_actions,
                domain=CONTEXT_DOMAIN_LOCATION,
                with_top_separator=is_first_item,
                with_bottom_separator=is_last_item,
            )
        return card_html
