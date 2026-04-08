"""
LocationCard Component - Current Location Display v1.0.

Renders the user's current GPS position with:
- Static map hero image (Google Static Maps via proxy)
- Map pin icon with address
- Locality and country chips
- Coordinates
- Google Maps link

Created: 2026-04-08
"""

from __future__ import annotations

from typing import Any

from src.core.constants import STATIC_MAP_DESKTOP_HEIGHT, STATIC_MAP_DESKTOP_WIDTH
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
    render_d_row,
    wrap_with_response,
)
from src.domains.agents.display.icons import Icons
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
        address = data.get("formatted_address", "")
        locality = data.get("locality", "")
        country = data.get("country", "")
        postal_code = data.get("postal_code", "")
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        static_map_url = data.get("static_map_url", "")

        # Display name: locality or first part of address
        display_name = locality or (address.split(",")[0] if address else "Position")

        # Google Maps URL
        if latitude and longitude:
            maps_url = f"https://www.google.com/maps/@{latitude},{longitude},15z"
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
            map_url = (
                f"{static_map_url}"
                f"&width={STATIC_MAP_DESKTOP_WIDTH}"
                f"&height={STATIC_MAP_DESKTOP_HEIGHT}"
            )
            map_img = (
                f'<img src="{escape_html(map_url)}" alt="Location map" '
                f'class="lia-route__map-image" loading="lazy" />'
            )
            if maps_url:
                hero_html = (
                    f'<a href="{escape_html(maps_url)}" target="_blank" rel="noopener" '
                    f'class="lia-route__map-link">{map_img}</a>'
                )
            else:
                hero_html = f'<div class="lia-route__map">{map_img}</div>'

        # --- Card top: pin icon + display name ---
        title_html = escape_html(display_name)
        if maps_url:
            title_html = (
                f'<a class="lia-card-top__title" href="{escape_html(maps_url)}"'
                f' target="_blank">{escape_html(display_name)}</a>'
            )
        card_top = render_card_top("location_on", "blue", title_html)

        # --- Chips: locality, country, postal code ---
        chips = []
        if locality:
            chips.append(render_chip(locality, "blue", Icons.LOCATION))
        if country:
            chips.append(render_chip(country, "", "public"))
        if postal_code:
            chips.append(render_chip(postal_code, "", "pin_drop"))
        chip_row = render_chip_row(" ".join(chips)) if chips else ""

        # --- Address row ---
        address_html = ""
        if address:
            addr_link = address
            if maps_url:
                addr_link = (
                    f'<a href="{escape_html(maps_url)}" target="_blank">'
                    f"{escape_html(address)}</a>"
                )
            address_html = render_d_row(
                Icons.LOCATION,
                addr_link,
                icon_style=(
                    "font-variation-settings:'FILL' 1,'wght' 400,'GRAD' 0,'opsz' 20;"
                    "color:#ef4444"
                ),
            )
            address_html = f'<div style="margin-top:var(--lia-space-lg)">{address_html}</div>'

        # --- Coordinates ---
        coords_html = ""
        if latitude is not None and longitude is not None:
            coords_text = f"{latitude:.6f}, {longitude:.6f}"
            coords_html = render_d_row("explore", escape_html(coords_text))

        nested_class = self._nested_class(ctx)

        card_html = f"""<div class="lia-card lia-place {nested_class}">
{hero_html}
{card_top}
{chip_row}
{address_html}
{coords_html}
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
