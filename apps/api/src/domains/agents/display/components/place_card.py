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

import json
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
    render_collapsible,
    stars_rating,
    wrap_with_response,
)
from src.domains.agents.display.icons import Icons, icon
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
        """Unified place card - CSS handles responsive adaptation."""
        nested_class = self._nested_class(ctx)
        open_class = self._open_status_class(is_open)

        # Photo section (with gallery URLs for frontend lightbox)
        photo_html = self._render_photo_section(photo_url, name, data)

        # Rating with stars + reviews count
        # Note: stars_rating() already includes the rating value
        rating_html = ""
        if rating:
            reviews_label = V3Messages.get_reviews(ctx.language)
            reviews_text = f"({reviews_count} {reviews_label})" if reviews_count else ""
            rating_html = f"""<div class="lia-place__rating-block">
{stars_rating(rating)}
<span class="lia-place__reviews">{reviews_text}</span>
</div>"""

        # Status badge
        self._render_status_badge(is_open, ctx, full_label=True)

        # Header badges (top-right): type + budget + distance
        header_badges = []
        type_tag = self._get_type_tag(types, ctx.language)
        if type_tag:
            header_badges.append(f'<span class="lia-badge lia-badge--accent">{type_tag}</span>')
        # Budget badge between type and distance
        if price_level:
            header_badges.append(
                f'<span class="lia-badge lia-badge--subtle">{icon(Icons.PAYMENTS)} {self._format_price(price_level, ctx.language)}</span>'
            )
        if distance:
            header_badges.append(
                f'<span class="lia-badge lia-badge--subtle">{icon(Icons.DIRECTIONS)} {escape_html(distance)}</span>'
            )
        header_badges_html = " ".join(header_badges)

        # Meta badges: opening time if closed
        meta_badges = []
        if is_open is False:
            next_open = self._get_next_open_time(data, ctx)
            if next_open:
                opens_at_label = V3Messages.get_opens_at(ctx.language)
                meta_badges.append(
                    f'<span class="lia-badge lia-badge--subtle">{icon(Icons.SCHEDULE)} {opens_at_label} {escape_html(next_open)}</span>'
                )
        meta_badges_html = " ".join(meta_badges)

        # Phone info visible on main card
        phone_html = ""
        if phone:
            phone_html = f"""<div class="lia-place__phone">
{icon(Icons.PHONE, domain="place")}
<a href="tel:{phone_for_tel(phone)}">{escape_html(format_phone(phone))}</a>
</div>"""

        # Editorial summary (show preview on main card) - AFTER phone
        # Support both API raw format (editorialSummary.text) and tool normalized (description)
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
            # Show full description on desktop (not truncated)
            editorial_html = f'<p class="lia-place__summary">{escape_html(summary_text)}</p>'

        # Collapsible extended details
        collapsible_html = self._render_collapsible_details(data, ctx)

        return f"""<div class="lia-card lia-place {open_class} {nested_class}">
{photo_html}
<div class="lia-place__content">
<div class="lia-place__header">
<a href="{escape_html(url)}" class="lia-place__name" target="_blank">{escape_html(name)}</a>
<div class="lia-place__header-right">
{header_badges_html}
</div>
</div>
{rating_html}
<div class="lia-place__meta">
{f'<div class="lia-place__badges">{meta_badges_html}</div>' if meta_badges_html else ''}
{self._render_address(address, ctx, full=True) if address else ''}
{phone_html}
{editorial_html}
</div>
{collapsible_html}
</div>
</div>"""

    def _render_status_badge(
        self,
        is_open: bool | None,
        ctx: RenderContext,
        full_label: bool = False,
        hide_if_budget: bool = False,
    ) -> str:
        """Render open/closed status badge.

        Badge is rendered only when:
        - hide_if_budget=False (no budget badge present)
        - is_open is known (not None)

        Args:
            is_open: True if open, False if closed, None if unknown
            ctx: Render context
            full_label: Show full label like "Ouvert" vs "O" (not used, kept for compat)
            hide_if_budget: If True (budget badge present), don't show status badge

        Returns:
            HTML for status badge, or empty string
        """
        # Don't show badge if budget is present (redundant with border color)
        if hide_if_budget:
            return ""

        if is_open is None:
            return ""

        if is_open:
            open_label = V3Messages.get_open(ctx.language)
            return f'<span class="lia-badge lia-badge--success">{open_label}</span>'
        else:
            closed_label = V3Messages.get_closed(ctx.language)
            return f'<span class="lia-badge lia-badge--error">{closed_label}</span>'

    def _render_photo_section(self, photo_url: str, name: str, data: dict[str, Any]) -> str:
        """Render photo section with optional gallery URLs for frontend lightbox.

        DRY: Shared between _render_mobile() and _render_desktop().

        Args:
            photo_url: Main photo URL for thumbnail display
            name: Place name for alt text
            data: Full place data containing photo_urls array

        Returns:
            HTML for photo section, or empty string if no photo
        """
        if not photo_url:
            return ""

        # Add data-photo-urls attribute if multiple photos available
        photo_urls_attr = ""
        photo_urls = data.get("photo_urls", [])
        if photo_urls:
            photo_urls_attr = f' data-photo-urls="{escape_html(json.dumps(photo_urls))}"'

        return f"""<div class="lia-place__photo"{photo_urls_attr}>
<img src="{escape_html(photo_url)}" alt="{escape_html(name)}" loading="lazy">
</div>"""

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

    def _render_collapsible_details(self, data: dict[str, Any], ctx: RenderContext) -> str:
        """Render collapsible section with extended details.

        Order:
        1. Description (editorial summary)
        2. Opening hours
        3. Services & features
        4. Reviews (5 max)
        5. Accessibility
        6. Payment options
        """
        detail_sections = []

        # Note: Editorial summary/description is now shown in main section for all viewports
        # (CSS handles truncation on mobile via .lia-place__summary styling)

        # 1. Opening hours - support both API raw format AND tool normalized format
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
            hours_items = []
            for h in weekday_text[:7]:
                h_str = str(h)
                if ":" in h_str:
                    parts = h_str.split(":", 1)
                    day = parts[0].strip()
                    time_range = parts[1].strip() if len(parts) > 1 else ""
                    hours_items.append(
                        f'<div class="lia-place__hours-row">'
                        f'<span class="lia-place__hours-day">{escape_html(day)}</span>'
                        f'<span class="lia-place__hours-time">{escape_html(time_range)}</span>'
                        f"</div>"
                    )
                else:
                    hours_items.append(
                        f'<div class="lia-place__hours-row">{escape_html(h_str)}</div>'
                    )
            hours_html = "".join(hours_items)
            detail_sections.append(
                f'<div class="lia-place__hours">'
                f'<div class="lia-place__section-header">{icon(Icons.SCHEDULE)} {hours_label}</div>'
                f'<div class="lia-place__hours-list">{hours_html}</div>'
                f"</div>"
            )

        # 3. Services & features
        features = data.get("features", [])
        if features:
            feature_items = self._format_features(features, ctx.language)
            if feature_items:
                services_label = V3Messages.get_services_amenities(ctx.language)
                detail_sections.append(
                    f'<div class="lia-place__features">'
                    f'<div class="lia-place__section-header">{icon(Icons.STAR)} {services_label}</div>'
                    f'<div class="lia-place__features-list">{" ".join(feature_items)}</div>'
                    f"</div>"
                )

        # 4. Reviews (show up to 5) - support both API raw and tool normalized formats
        # API raw: reviews[].text.text, reviews[].authorAttribution.displayName
        # Tool normalized: reviews[].text (string), reviews[].relative_time
        reviews = data.get("reviews", [])
        if reviews and isinstance(reviews, list):
            review_items = []
            for review in reviews[:5]:
                if isinstance(review, dict):
                    # Author: try API format then tool format
                    author = ""
                    author_attr = review.get("authorAttribution", {})
                    if isinstance(author_attr, dict):
                        author = author_attr.get("displayName", "")
                    if not author:
                        author = review.get("author_name", "") or review.get("author", "")

                    # Text: try API format (nested) then tool format (string)
                    text = ""
                    text_obj = review.get("text", "")
                    if isinstance(text_obj, dict):
                        text = text_obj.get("text", "")
                    elif isinstance(text_obj, str):
                        text = text_obj

                    review_rating = review.get("rating", 0)
                    relative_time = review.get("relative_time", "") or review.get(
                        "relativePublishTimeDescription", ""
                    )

                    if text:
                        text_preview = text[:100] + "..." if len(text) > 100 else text
                        # Format: Author - relative_time - ★★★★☆ (colored stars at end)
                        # Generate colored star icons
                        stars_html = ""
                        if review_rating:
                            full_stars = int(review_rating)
                            empty_stars = 5 - full_stars
                            stars_html = (
                                '<span class="lia-place__review-stars">'
                                + "".join(
                                    f'<span class="lia-star lia-star--full">{icon(Icons.STAR, size="sm")}</span>'
                                    for _ in range(full_stars)
                                )
                                + "".join(
                                    f'<span class="lia-star lia-star--empty">{icon(Icons.STAR_OUTLINE, size="sm")}</span>'
                                    for _ in range(empty_stars)
                                )
                                + "</span>"
                            )
                        # Build info line: author - time  ★★★★☆ (space before stars, not dash)
                        info_parts = []
                        if author:
                            info_parts.append(f"<strong>{escape_html(author)}</strong>")
                        if relative_time:
                            info_parts.append(
                                f'<span class="lia-place__review-time">{escape_html(relative_time)}</span>'
                            )
                        info_html = " - ".join(info_parts)
                        if stars_html:
                            # Space before stars (like the rating under title), not " - "
                            info_html = f"{info_html} {stars_html}" if info_html else stars_html
                        review_items.append(
                            f'<div class="lia-place__review">'
                            f'<div class="lia-place__review-header">{info_html}</div>'
                            f"<p>{escape_html(text_preview)}</p>"
                            f"</div>"
                        )
            if review_items:
                reviews_title = V3Messages.get_reviews(ctx.language).capitalize()
                detail_sections.append(
                    f'<div class="lia-place__reviews-section">'
                    f'<div class="lia-place__section-header">{icon(Icons.CHAT)} {reviews_title}</div>'
                    f'<div class="lia-place__reviews-list">{"".join(review_items)}</div>'
                    f"</div>"
                )

        # Accessibility options
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
                    f'<div class="lia-place__detail-item">'
                    f"{icon(Icons.ACCESSIBLE)}"
                    f'<span>{", ".join(acc_features)}</span>'
                    f"</div>"
                )

        # Payment options
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
                    f'<div class="lia-place__detail-item">'
                    f"{icon(Icons.CREDIT_CARD)}"
                    f'<span>{", ".join(pay_methods)}</span>'
                    f"</div>"
                )

        # If we have details, wrap in collapsible
        if detail_sections:
            content_html = "\n".join(detail_sections)
            return render_collapsible(
                trigger_text=V3Messages.get_see_more(ctx.language),
                content_html=f'<div class="lia-place__extended">{content_html}</div>',
                initially_open=False,
                language=ctx.language,
            )

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

    def _render_address(
        self, address: str, ctx: RenderContext, full: bool = False, with_icon: bool = True
    ) -> str:
        """Render address with optional icon and directions link."""
        if not address:
            return ""

        # Truncate for tablet view
        display_address = address if full else address[:50] + ("..." if len(address) > 50 else "")
        directions_url = build_directions_url(address)

        icon_html = f"{icon(Icons.DIRECTIONS)}\n" if with_icon else ""

        return f"""<div class="lia-place__address">
{icon_html}<a href="{escape_html(directions_url)}" target="_blank" title="{V3Messages.get_directions(ctx.language)}">{escape_html(display_address)}</a>
</div>"""
