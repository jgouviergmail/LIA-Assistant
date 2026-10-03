"""
PlaceCard Component - Modern Place/Venue Display v3.0.

Renders places with:
- Wrapper for assistant comment + suggested actions
- Photo hero
- Rating and reviews
- Distance and price level
- Open/closed status
- Collapsible extended details (hours, reviews, features, accessibility)
- Action buttons (directions, call, website)
"""

from __future__ import annotations

from typing import Any

from src.core.constants import CURRENCY_DISPLAY_SYMBOLS
from src.core.i18n import resolve_language
from src.core.i18n_v3 import V3Messages
from src.domains.agents.constants import CONTEXT_DOMAIN_PLACES
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    escape_html,
    format_phone,
    phone_for_tel,
    render_card_top,
    render_chip,
    render_chip_row,
    render_chip_stars,
    render_d_row,
    safe_url,
    wrap_with_response,
)
from src.domains.agents.display.components.place_details import render_place_details
from src.domains.agents.display.components.place_hours import open_status, transition_time
from src.domains.agents.display.components.place_photo import (
    place_source_without_photo,
    render_place_photo,
)
from src.domains.agents.display.icons import Icons
from src.domains.agents.display.urls import build_directions_url, build_place_url
from src.domains.agents.display.values import (
    first_present,
    list_values,
    nonnegative_integer,
    rating_value,
    scalar_text,
)


class PlaceCard(BaseComponent):
    """
    Modern place card component v3.0.

    Design:
    - Response wrapper with assistant comment zone + actions zone
    - Photo hero (if available)
    - Rating with stars
    - Distance badge
    - Price level indicator
    - Open/closed status
    - Collapsible details (hours, reviews, features, accessibility)
    - Action buttons (call, directions, website)
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
        """
        Render place as modern card with wrapper.

        Args:
            data: Place data from Google Places API
            ctx: Render context (viewport, language, timezone)
            assistant_comment: Optional comment from assistant above card
            suggested_actions: Optional action buttons below card
            with_wrapper: Whether to wrap with response zones

        Returns:
            HTML string for the place card
        """
        # Extract data. ``displayName`` is an OBJECT in Places API v1 but a
        # plain string in registry payloads, and either may be explicitly null:
        # ``get(key, {})`` only defends against a MISSING key, so the ``.get``
        # chain used to raise and — because the caller catches AttributeError
        # around the whole render — silently dropped EVERY card of the answer.
        display_name = data.get("displayName")
        if isinstance(display_name, dict):
            display_name = display_name.get("text", "")
        name = scalar_text(data.get("name")) or scalar_text(display_name) or ""
        address = scalar_text(first_present(data, "formattedAddress", "address"))
        phone = scalar_text(
            first_present(data, "internationalPhoneNumber", "phone_international", "phone")
        )
        website = scalar_text(first_present(data, "websiteUri", "website"))
        rating = rating_value(data.get("rating"))
        reviews_count = (
            nonnegative_integer(
                first_present(data, "userRatingCount", "rating_count", "reviews_count")
            )
            or 0
        )
        price_level = data.get("priceLevel") or data.get("price_level", "")
        is_open = self._get_open_status(data)
        distance = scalar_text(data.get("distance"))
        types = [value for value in list_values(data.get("types")) if isinstance(value, str)]
        place_id = scalar_text(first_present(data, "place_id", "id"))

        # Build place URL for name link (opens Google Maps place page, not directions)
        query = f"{name}, {address}" if name and address else (name or address)
        url = build_place_url(place_id=place_id, query=query)

        # Build default actions if not provided
        if suggested_actions is None:
            suggested_actions = self._build_default_actions(name, address, phone, website, ctx)

        # Unified render - CSS handles responsive adaptation
        card_html = self._render_card(
            name,
            url,
            address,
            phone,
            website,
            rating,
            reviews_count,
            price_level,
            is_open,
            distance,
            types,
            ctx,
            data,
        )

        # Wrap with response zones if requested
        if with_wrapper:
            return wrap_with_response(
                card_html=card_html,
                assistant_comment=assistant_comment,
                suggested_actions=suggested_actions,
                domain=CONTEXT_DOMAIN_PLACES,
                with_top_separator=is_first_item,
                with_bottom_separator=is_last_item,
            )
        return card_html

    def _build_default_actions(
        self,
        name: str,
        address: str,
        phone: str,
        website: str,
        ctx: RenderContext,
    ) -> list[dict[str, str]]:
        """Build default action buttons for place."""
        actions = []

        # Directions (primary action) - use address or name as destination
        destination = address or name
        if destination:
            actions.append(
                {
                    "icon": Icons.DIRECTIONS,
                    "label": V3Messages.get_directions(ctx.language),
                    "url": build_directions_url(destination),
                }
            )

        # Call
        if phone:
            actions.append(
                {
                    "icon": Icons.PHONE,
                    "label": V3Messages.get_call(ctx.language),
                    "url": f"tel:{phone_for_tel(phone)}",
                }
            )

        # Website
        if website:
            actions.append(
                {
                    "icon": Icons.WEB,
                    "label": V3Messages.get_website(ctx.language),
                    "url": website,
                }
            )

        return actions

    def _closure_label(self, data: dict[str, Any], ctx: RenderContext) -> str:
        """Localized closure badge label ('' when the place is operational)."""
        business_status = data.get("business_status") or data.get("businessStatus") or ""
        if not business_status:
            return ""
        return V3Messages.get_business_status(ctx.language, str(business_status))

    def _open_status_class(self, is_open: bool | None) -> str:
        """Return CSS class for open/closed status."""
        if is_open is True:
            return "lia-place--open"
        elif is_open is False:
            return "lia-place--closed"
        return ""

    def _render_card(
        self,
        name: str,
        url: str,
        address: str,
        phone: str,
        website: str,
        rating: float | None,
        reviews_count: int,
        price_level: object,
        is_open: bool | None,
        distance: str,
        types: list[str],
        ctx: RenderContext,
        data: dict[str, Any],
    ) -> str:
        """Unified place card using Design System v4 components."""
        nested_class = self._nested_class(ctx)

        # Business status (audit 2026-08): a closed place must never render as
        # a normal one. Any non-empty status suppresses the open/closed chips
        # (a stale openNow must not contradict the closure).
        status_label = self._closure_label(data, ctx)
        if status_label:
            is_open = False
        open_class = self._open_status_class(is_open)

        # --- Hero photo ---
        hero_html = render_place_photo(data, name, ctx.language)

        # --- Card top: illustration + name ---
        illus_color = "green" if is_open else ("red" if is_open is False else "gray")
        # Google's own localized primary type beats the hand-rolled mapping
        type_tag = scalar_text(data.get("primary_type")) or self._get_type_tag(types, ctx.language)
        illus_icon = self._get_place_icon(types)
        title_html = f'<a class="lia-card-top__title" href="{safe_url(url)}" target="_blank">{escape_html(name)}</a>'
        card_top_html = render_card_top(illus_icon, illus_color, title_html)

        # --- Chip row 1: type + price + distance + stars (same line) ---
        chips_row1 = []
        if type_tag:
            # render_chip escapes its text; passing pre-escaped HTML would double-escape
            chips_row1.append(render_chip(str(type_tag), "indigo"))
        # Exact price range (audit-added) beats the legacy €€ approximation
        price_range_text = self._format_price_range(data.get("price_range"))
        if price_range_text:
            chips_row1.append(render_chip(price_range_text, "", Icons.PAYMENTS))
        elif price_level:
            chips_row1.append(
                render_chip(self._format_price(price_level, ctx.language), "", Icons.PAYMENTS)
            )
        if distance:
            chips_row1.append(render_chip(distance, "", Icons.DIRECTIONS))
        if rating is not None:
            chips_row1.append(render_chip_stars(rating, reviews_count))
        chip_row_1 = render_chip_row(" ".join(chips_row1)) if chips_row1 else ""

        # --- Chip row 3: closure badge OR open/closed + opens at ---
        chips_status = []
        if status_label:
            chips_status.append(render_chip(status_label, "red", "cancel"))
        elif is_open is True:
            open_label = V3Messages.get_open(ctx.language)
            chips_status.append(render_chip(open_label, "green", "check_circle"))
            # Show closing time if available
            close_time = self._get_closing_time(data, ctx)
            if close_time:
                closes_at_label = V3Messages.get_closes_at(ctx.language)
                chips_status.append(
                    render_chip(f"{closes_at_label} {close_time}", "", Icons.SCHEDULE)
                )
        elif is_open is False:
            closed_label = V3Messages.get_closed(ctx.language)
            chips_status.append(render_chip(closed_label, "red", "cancel"))
            next_open = self._get_next_open_time(data, ctx)
            if next_open:
                opens_at_label = V3Messages.get_opens_at(ctx.language)
                chips_status.append(
                    render_chip(f"{opens_at_label} {next_open}", "", Icons.SCHEDULE)
                )
        chip_row_3 = render_chip_row(" ".join(chips_status)) if chips_status else ""

        # --- Address (extra top margin instead of separator line) ---
        address_html = ""
        if address:
            directions_url = build_directions_url(address)
            link = (
                f'<a href="{safe_url(directions_url)}" target="_blank">{escape_html(address)}</a>'
            )
            addr_row = render_d_row(
                Icons.LOCATION,
                link,
                icon_style="font-variation-settings:'FILL' 1,'wght' 400,'GRAD' 0,'opsz' 20;color:#ef4444",
            )
            address_html = f'<div style="margin-top:var(--lia-space-lg)">{addr_row}</div>'

        # --- Phone ---
        phone_html = ""
        if phone:
            link = f'<a href="tel:{phone_for_tel(phone)}">{escape_html(format_phone(phone))}</a>'
            phone_html = render_d_row(Icons.PHONE, link)

        # --- Editorial summary ---
        editorial_html = ""
        summary_text = ""
        editorial = data.get("editorialSummary", {})
        if editorial:
            summary_text = (
                scalar_text(editorial.get("text"))
                if isinstance(editorial, dict)
                else scalar_text(editorial)
            )
        if not summary_text:
            summary_text = scalar_text(data.get("description"))
        if summary_text:
            editorial_html = f'<p class="lia-place__summary" style="font-size:var(--lia-text-sm);color:var(--lia-text-secondary);margin-top:var(--lia-space-xs);font-style:italic">{escape_html(summary_text)}</p>'

        # --- Collapsible ---
        collapsible_html = self._render_collapsible_details_v4(data, ctx)

        return f"""<div class="lia-card lia-place {open_class} {nested_class}">
{hero_html}
{card_top_html}
{chip_row_1}
{chip_row_3}
{address_html}
{phone_html}
{editorial_html}
{collapsible_html}
{place_source_without_photo(hero_html)}
</div>"""

    def _get_place_icon(self, types: list[str]) -> str:
        """Get Material Symbols icon name for place type."""
        type_icons = {
            "restaurant": "restaurant",
            "cafe": "coffee",
            "bar": "local_bar",
            "hotel": "hotel",
            "store": "store",
            "shopping_mall": "shopping_bag",
            "gym": "fitness_center",
            "hospital": "local_hospital",
            "pharmacy": "local_pharmacy",
            "school": "school",
            "museum": "museum",
            "park": "park",
            "gas_station": "local_gas_station",
            "airport": "flight",
            "train_station": "train",
        }
        for t in types:
            if t in type_icons:
                return type_icons[t]
        return "location_on"

    def _render_collapsible_details_v4(self, data: dict[str, Any], ctx: RenderContext) -> str:
        return render_place_details(data, ctx)

    def _get_next_open_time(self, data: dict[str, Any], ctx: RenderContext) -> str:
        return transition_time(data, ctx, opening=True)

    def _get_closing_time(self, data: dict[str, Any], ctx: RenderContext) -> str:
        return transition_time(data, ctx, opening=False)

    def _format_price_range(self, price_range: object) -> str:
        """Format the normalized price range ({start, end, currency}) as a chip.

        Returns "" when the payload is absent or unusable, so callers can fall
        back to the legacy price level. Open-ended ranges render the known
        bound alone (e.g. "100 €").
        """
        if not isinstance(price_range, dict):
            return ""
        start = scalar_text(price_range.get("start"))
        end = scalar_text(price_range.get("end"))
        if not start and not end:
            return ""
        currency = scalar_text(price_range.get("currency"))
        symbol = CURRENCY_DISPLAY_SYMBOLS.get(currency, currency)
        if start and end:
            amount = f"{start}–{end}"
        else:
            amount = start or end
        return f"{amount} {symbol}".strip()

    def _format_price(self, price_level: object, language: str | None = None) -> str:
        """Convert price level to € symbols."""
        if isinstance(price_level, str):
            if price_level.startswith("PRICE_LEVEL_"):
                level = price_level.replace("PRICE_LEVEL_", "")
                if level == "FREE":
                    return V3Messages.get_free(resolve_language(language))
                mapping = {
                    "INEXPENSIVE": "€",
                    "MODERATE": "€€",
                    "EXPENSIVE": "€€€",
                    "VERY_EXPENSIVE": "€€€€",
                }
                return mapping.get(level, price_level)
            return price_level
        level_number = nonnegative_integer(price_level)
        return "€" * level_number if level_number is not None and level_number <= 4 else ""

    def _get_open_status(self, data: dict[str, Any]) -> bool | None:
        return open_status(data)

    def _get_type_tag(self, types: list[str], language: str | None = None) -> str:
        """Get display type from types list."""
        for t in types:
            type_label = V3Messages.get_place_type(resolve_language(language), t)
            if type_label:
                return type_label
        return ""
