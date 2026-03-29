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

from src.core.i18n_v3 import V3Messages
from src.domains.agents.constants import CONTEXT_DOMAIN_PLACES
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    build_directions_url,
    build_place_url,
    escape_html,
    format_phone,
    phone_for_tel,
    render_card_hero,
    render_card_top,
    render_chip,
    render_chip_row,
    render_chip_stars,
    render_collapsible,
    render_d_item,
    render_d_row,
    render_kv_rows,
    render_review,
    render_section_header,
    wrap_with_response,
)
from src.domains.agents.display.icons import Icons
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


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
        # Extract data
        name = data.get("name") or data.get("displayName", {}).get("text", "")
        address = data.get("formattedAddress") or data.get("address", "")
        phone = data.get("internationalPhoneNumber") or data.get("phone", "")
        website = data.get("websiteUri") or data.get("website", "")
        rating = data.get("rating")
        reviews_count = (
            data.get("userRatingCount") or data.get("rating_count") or data.get("reviews_count", 0)
        )
        price_level = data.get("priceLevel") or data.get("price_level", "")
        is_open = self._get_open_status(data)
        distance = data.get("distance", "")
        photo_url = data.get("photo_url", "")
        types = data.get("types", [])
        place_id = data.get("place_id") or data.get("id", "")

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
            photo_url,
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
        price_level: str,
        is_open: bool | None,
        distance: str,
        photo_url: str,
        types: list,
        ctx: RenderContext,
        data: dict[str, Any],
    ) -> str:
        """Unified place card using Design System v4 components."""
        nested_class = self._nested_class(ctx)
        open_class = self._open_status_class(is_open)

        # --- Hero photo ---
        hero_html = render_card_hero(photo_url, name) if photo_url else ""

        # --- Card top: illustration + name ---
        illus_color = "green" if is_open else ("red" if is_open is False else "gray")
        type_tag = self._get_type_tag(types, ctx.language)
        illus_icon = self._get_place_icon(types)
        title_html = f'<a class="lia-card-top__title" href="{escape_html(url)}" target="_blank">{escape_html(name)}</a>'
        card_top_html = render_card_top(illus_icon, illus_color, title_html)

        # --- Chip row 1: type + distance ---
        # --- Chip row 1: type + price + distance + stars (same line) ---
        chips_row1 = []
        if type_tag:
            chips_row1.append(render_chip(type_tag, "indigo"))
        if price_level:
            chips_row1.append(
                render_chip(self._format_price(price_level, ctx.language), "", Icons.PAYMENTS)
            )
        if distance:
            chips_row1.append(render_chip(distance, "", Icons.DIRECTIONS))
        if rating:
            chips_row1.append(render_chip_stars(rating, reviews_count))
        chip_row_1 = render_chip_row(" ".join(chips_row1)) if chips_row1 else ""

        # --- Chip row 3: open/closed + opens at (no separator) ---
        chips_status = []
        if is_open is True:
            open_label = V3Messages.get_open(ctx.language)
            chips_status.append(render_chip(open_label, "green", "check_circle"))
            # Show closing time if available
            close_time = self._get_closing_time(data)
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
            link = f'<a href="{escape_html(directions_url)}" target="_blank">{escape_html(address)}</a>'
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
                editorial.get("text", "") if isinstance(editorial, dict) else str(editorial)
            )
        if not summary_text:
            summary_text = data.get("description", "")
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
</div>"""

    def _get_place_icon(self, types: list) -> str:
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
        """Render collapsible details using v4 components with section headers."""
        detail_sections: list[str] = []
        is_first = True

        # 1. Opening hours as KV rows
        weekday_text = None
        opening_hours = data.get("currentOpeningHours", {}) or data.get("openingHours", {})
        if opening_hours and isinstance(opening_hours, dict):
            weekday_text = opening_hours.get("weekdayDescriptions", []) or opening_hours.get(
                "weekday_text", []
            )
        if not weekday_text:
            weekday_text = data.get("opening_hours", [])
        if weekday_text and isinstance(weekday_text, list) and len(weekday_text) > 0:
            hours_label = V3Messages.get_opening_hours(ctx.language)
            detail_sections.append(
                render_section_header(hours_label, Icons.SCHEDULE, "amber", first=is_first)
            )
            is_first = False
            # Parse hours into key-value pairs
            pairs = []
            for h in weekday_text[:7]:
                h_str = str(h)
                if ":" in h_str:
                    parts = h_str.split(":", 1)
                    day = parts[0].strip()
                    time_range = parts[1].strip() if len(parts) > 1 else ""
                    pairs.append((day, time_range))
                else:
                    pairs.append((h_str, ""))
            detail_sections.append(render_kv_rows(pairs))

        # 2. Services & features
        features = data.get("features", [])
        if features:
            feature_items = self._format_features(features, ctx.language)
            if feature_items:
                services_label = V3Messages.get_services_amenities(ctx.language)
                detail_sections.append(
                    render_section_header(services_label, Icons.STAR, "purple", first=is_first)
                )
                is_first = False
                detail_sections.append(
                    f'<div style="display:flex;flex-wrap:wrap;gap:var(--lia-space-xs)">'
                    f'{" ".join(feature_items)}</div>'
                )

        # 3. Reviews
        reviews = data.get("reviews", [])
        if reviews and isinstance(reviews, list):
            review_items = []
            for rev in reviews[:5]:
                if isinstance(rev, dict):
                    author = ""
                    author_attr = rev.get("authorAttribution", {})
                    if isinstance(author_attr, dict):
                        author = author_attr.get("displayName", "")
                    if not author:
                        author = rev.get("author_name", "") or rev.get("author", "")

                    text = ""
                    text_obj = rev.get("text", "")
                    if isinstance(text_obj, dict):
                        text = text_obj.get("text", "")
                    elif isinstance(text_obj, str):
                        text = text_obj

                    review_rating = int(rev.get("rating", 0))
                    relative_time = rev.get("relative_time", "") or rev.get(
                        "relativePublishTimeDescription", ""
                    )

                    if text and author:
                        text_preview = text[:100] + "..." if len(text) > 100 else text
                        review_items.append(
                            render_review(author, relative_time, review_rating, text_preview)
                        )
            if review_items:
                reviews_title = V3Messages.get_reviews(ctx.language).capitalize()
                detail_sections.append(
                    render_section_header(reviews_title, Icons.CHAT, "indigo", first=is_first)
                )
                is_first = False
                detail_sections.extend(review_items)

        # 4. Accessibility
        accessibility = data.get("accessibilityOptions", {})
        if accessibility:
            acc_features = []
            if accessibility.get("wheelchairAccessibleEntrance"):
                acc_features.append(V3Messages.get_accessibility(ctx.language, "entrance"))
            if accessibility.get("wheelchairAccessibleParking"):
                acc_features.append(V3Messages.get_accessibility(ctx.language, "parking"))
            if accessibility.get("wheelchairAccessibleSeating"):
                acc_features.append(V3Messages.get_accessibility(ctx.language, "seating"))
            if accessibility.get("wheelchairAccessibleRestroom"):
                acc_features.append(V3Messages.get_accessibility(ctx.language, "restroom"))
            if acc_features:
                detail_sections.append(
                    render_section_header(
                        V3Messages.get_accessibility_title(ctx.language),
                        Icons.ACCESSIBLE,
                        "blue",
                        first=is_first,
                    )
                )
                is_first = False
                detail_sections.append(
                    render_d_item(
                        "check_circle", ", ".join(acc_features), icon_style="color:#10b981"
                    )
                )

        # 5. Payment options
        payment = data.get("paymentOptions", {})
        if payment:
            pay_methods = []
            if payment.get("acceptsCreditCards"):
                pay_methods.append(V3Messages.get_payment(ctx.language, "credit_cards"))
            if payment.get("acceptsCashOnly"):
                pay_methods.append(V3Messages.get_payment(ctx.language, "cash_only"))
            if payment.get("acceptsNfc"):
                pay_methods.append(V3Messages.get_payment(ctx.language, "contactless"))
            if pay_methods:
                detail_sections.append(
                    render_section_header(
                        V3Messages.get_payment_title(ctx.language),
                        Icons.CREDIT_CARD,
                        "teal",
                        first=is_first,
                    )
                )
                detail_sections.append(
                    render_d_item(
                        "check_circle", ", ".join(pay_methods), icon_style="color:#10b981"
                    )
                )

        if detail_sections:
            content_html = "\n".join(detail_sections)
            return render_collapsible(
                trigger_text=V3Messages.get_see_more(ctx.language),
                content_html=content_html,
                initially_open=False,
                language=ctx.language,
                with_separator=False,
            )

        return ""

    def _get_next_open_time(self, data: dict[str, Any], ctx: RenderContext) -> str:
        """Get next opening time if place is closed."""
        # Try to extract next opening from opening hours
        weekday_text = None
        opening_hours = data.get("currentOpeningHours", {}) or data.get("openingHours", {})
        if opening_hours and isinstance(opening_hours, dict):
            weekday_text = opening_hours.get("weekdayDescriptions", []) or opening_hours.get(
                "weekday_text", []
            )
        if not weekday_text:
            weekday_text = data.get("opening_hours", [])

        if weekday_text and isinstance(weekday_text, list) and len(weekday_text) > 0:
            # Return the first opening time from today or tomorrow
            from datetime import datetime

            try:
                # Get current day name in the user's language
                today_idx = datetime.now().weekday()
                if today_idx < len(weekday_text):
                    today_hours = weekday_text[today_idx]
                    # Extract opening time (format: "Lundi: 09:00 – 18:00" or similar)
                    if ":" in today_hours and "–" in today_hours:
                        parts = today_hours.split(":", 1)
                        if len(parts) > 1:
                            time_part = parts[1].strip()
                            if "–" in time_part:
                                open_time = time_part.split("–")[0].strip()
                                return open_time  # type: ignore[no-any-return]
            except (ValueError, IndexError, TypeError):
                logger.debug("place_card_opening_hours_parse_error")
        return ""

    def _get_closing_time(self, data: dict[str, Any]) -> str:
        """Get closing time for today if place is open."""
        weekday_text = None
        opening_hours = data.get("currentOpeningHours", {}) or data.get("openingHours", {})
        if opening_hours and isinstance(opening_hours, dict):
            weekday_text = opening_hours.get("weekdayDescriptions", []) or opening_hours.get(
                "weekday_text", []
            )
        if not weekday_text:
            weekday_text = data.get("opening_hours", [])

        if weekday_text and isinstance(weekday_text, list) and len(weekday_text) > 0:
            from datetime import datetime

            try:
                today_idx = datetime.now().weekday()
                if today_idx < len(weekday_text):
                    today_hours = str(weekday_text[today_idx])
                    if ":" in today_hours and "–" in today_hours:
                        parts = today_hours.split(":", 1)
                        if len(parts) > 1:
                            time_part = parts[1].strip()
                            if "–" in time_part:
                                close_time = time_part.split("–")[1].strip()
                                return close_time  # type: ignore[no-any-return]
            except (ValueError, IndexError, TypeError):
                logger.debug("place_card_closing_time_parse_error")
        return ""

    def _format_price(self, price_level: str, language: str = "fr") -> str:
        """Convert price level to € symbols."""
        if isinstance(price_level, str):
            if price_level.startswith("PRICE_LEVEL_"):
                level = price_level.replace("PRICE_LEVEL_", "")
                if level == "FREE":
                    return V3Messages.get_free(language)
                mapping = {
                    "INEXPENSIVE": "€",
                    "MODERATE": "€€",
                    "EXPENSIVE": "€€€",
                    "VERY_EXPENSIVE": "€€€€",
                }
                return mapping.get(level, price_level)
            return price_level
        return "€" * int(price_level) if price_level else ""

    def _get_open_status(self, data: dict) -> bool | None:
        """Get open/closed status."""
        # Tool normalized format: open_now directly at root level
        if "open_now" in data:
            return data["open_now"]  # type: ignore[no-any-return]
        # API raw format: currentOpeningHours.openNow
        if "currentOpeningHours" in data:
            return data["currentOpeningHours"].get("openNow")  # type: ignore[no-any-return]
        # Legacy format: opening_hours.open_now
        if "opening_hours" in data and isinstance(data["opening_hours"], dict):
            return data["opening_hours"].get("open_now")
        # Fallback: is_open
        if "is_open" in data:
            return data["is_open"]  # type: ignore[no-any-return]
        return None

    def _get_type_tag(self, types: list, language: str = "fr") -> str:
        """Get display type from types list."""
        for t in types:
            type_label = V3Messages.get_place_type(language, t)
            if type_label:
                return type_label
        return ""

    def _format_features(self, features: list, language: str = "fr") -> list[str]:
        """Format place features/services as badges."""
        result = []
        for feature in features:
            if isinstance(feature, str):
                feature_label = V3Messages.get_place_feature(language, feature)
                if feature_label:
                    result.append(
                        f'<span class="lia-badge lia-badge--subtle">{feature_label}</span>'
                    )
        return result
