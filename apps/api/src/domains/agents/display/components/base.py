"""
Base Component for HTML Rendering.

Provides the foundation for all domain-specific components.
"""

from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import quote

if TYPE_CHECKING:
    pass

# Import separator helpers (DRY - centralized in config.py)
from src.domains.agents.display.config import separator_bold

# Import from icons module for Material Symbols support
from src.domains.agents.display.icons import (
    Icons,
    get_attachment_icon,
    icon,
    render_star_rating,
)

# =============================================================================
# Date Format Type
# =============================================================================

DateFormatType = Literal["full", "short", "relative", "day_month"]
"""
Date format types for the unified format_date helper:
- full: "Samedi 3 janvier 2026" / "Saturday, January 3, 2026"
- short: "03/01/2026" / "01/03/2026" / "03.01.2026" (country-specific FORMAT)
- relative: "Aujourd'hui" / "Hier" / "Lundi" / "12/01"
- day_month: "3 janvier" / "January 3" / "3. Januar" (for birthdays)
"""

# Relative date labels (not in i18n_dates.py)
TODAY_LABELS: dict[str, str] = {
    "fr": "Aujourd'hui",
    "en": "Today",
    "de": "Heute",
    "es": "Hoy",
    "it": "Oggi",
    "zh-CN": "今天",
}

YESTERDAY_LABELS: dict[str, str] = {
    "fr": "Hier",
    "en": "Yesterday",
    "de": "Gestern",
    "es": "Ayer",
    "it": "Ieri",
    "zh-CN": "昨天",
}


class Viewport(str, Enum):
    """Screen viewport sizes for responsive rendering."""

    MOBILE = "mobile"
    TABLET = "tablet"
    DESKTOP = "desktop"


@dataclass
class RenderContext:
    """Context for rendering components."""

    viewport: Viewport = Viewport.DESKTOP
    language: str = "fr"
    timezone: str = "Europe/Paris"  # User timezone for datetime formatting
    show_secondary: bool = True
    max_items: int = 5
    nested_level: int = 0  # For hierarchical rendering
    parent_domain: str | None = None  # For nested context


class BaseComponent(ABC):
    """
    Abstract base for all HTML components.

    Design Philosophy:
    - Components are pure functions: data in → HTML out
    - No side effects, no state
    - Viewport-aware rendering
    - CSS classes only (no inline styles)
    """

    @abstractmethod
    def render(self, data: dict[str, Any], ctx: RenderContext) -> str:
        """
        Render the component to HTML.

        Args:
            data: Domain-specific data dict
            ctx: Render context (viewport, language, etc.)

        Returns:
            HTML string with appropriate CSS classes
        """
        pass

    def render_list(
        self,
        items: list[dict[str, Any]],
        ctx: RenderContext,
    ) -> str:
        """
        Render a list of items.

        Each item's HTML is compacted to prevent Markdown parsing issues
        when the HTML is injected into mixed Markdown/HTML content.

        Separators are placed only at the boundaries:
        - Top separator above first item only
        - Bottom separator below last item only

        Args:
            items: List of data dicts
            ctx: Render context

        Returns:
            HTML string with all items, compacted for safe Markdown injection
        """
        if not items:
            return ""

        # Limit items
        items = items[: ctx.max_items]

        # Render each item with position-aware separator flags
        # Note: We render with tentative flags, then filter empty cards
        # Empty cards (e.g., routes with no destination) are excluded
        html_parts: list[str] = []
        total = len(items)
        for idx, item in enumerate(items):
            is_first = idx == 0
            is_last = idx == total - 1
            # Pass position flags - components should use these for separators
            rendered = self.render(  # type: ignore[call-arg]
                item,
                ctx,
                is_first_item=is_first,
                is_last_item=is_last,
            )
            # Filter out empty cards (validation failures return "")
            if rendered.strip():
                html_parts.append(compact_html(rendered))
        return "\n".join(html_parts)

    @staticmethod
    def _nested_class(ctx: RenderContext) -> str:
        """Get nested level class if applicable."""
        if ctx.nested_level > 0:
            return f"lia--nested-{min(ctx.nested_level, 3)}"
        return ""


# =============================================================================
# Utility Functions
# =============================================================================


def escape_html(text: str | None) -> str:
    """Safely escape HTML special characters."""
    if not text:
        return ""
    return html.escape(str(text))


def compact_html(html_string: str) -> str:
    """
    Compact HTML by removing unnecessary whitespace between tags.

    This is CRITICAL for Markdown/HTML mixing: when HTML is injected into
    Markdown content, newlines between tags can be misinterpreted as
    paragraph separators, causing tags like '</div>' to render as text.

    The compaction:
    - Removes whitespace (including newlines) between > and <
    - Preserves text content within tags
    - Keeps HTML valid and functional

    Example:
        Input:  '<div>\\n  <span>text</span>\\n</div>'
        Output: '<div><span>text</span></div>'

    Args:
        html_string: Raw HTML with potential whitespace between tags

    Returns:
        Compacted HTML safe for Markdown injection
    """
    if not html_string:
        return ""

    # Remove whitespace between closing/opening tags: >  \n  <
    compacted = re.sub(r">\s+<", "><", html_string)

    # Remove leading/trailing whitespace
    return compacted.strip()


def truncate(text: str | None, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to max length with suffix."""
    if not text:
        return ""
    text = str(text)
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def phone_for_tel(phone: str | None) -> str:
    """
    Clean phone number for tel: protocol.

    Removes all characters except digits and +.
    Example: "+33 1 23 45 67 89" -> "+33123456789"
    """
    if not phone:
        return ""
    return re.sub(r"[^\d+]", "", phone)


def format_phone(phone: str | None) -> str:
    """
    Format phone number for display.

    French format: 06.12.34.56.78
    International: as-is with spaces
    """
    if not phone:
        return ""

    # Remove all non-digits except +
    cleaned = re.sub(r"[^\d+]", "", phone)

    # French mobile (10 digits starting with 0)
    if len(cleaned) == 10 and cleaned.startswith("0"):
        return ".".join(cleaned[i : i + 2] for i in range(0, 10, 2))

    # French with country code (+33)
    if cleaned.startswith("+33") and len(cleaned) == 12:
        national = "0" + cleaned[3:]
        return ".".join(national[i : i + 2] for i in range(0, 10, 2))

    # Return original with some cleanup
    return re.sub(r"(\d{2})(?=\d)", r"\1 ", phone).strip()


def format_date(
    dt: datetime | str | int | None,
    language: str = "fr",
    timezone: str = "Europe/Paris",
    format_type: DateFormatType = "full",
    include_time: bool = False,
) -> str:
    """
    Unified date formatting helper with country-specific FORMATS.

    Uses i18n_dates for translations, this function handles FORMAT conventions:
    - France/Spain/Italy: dd/mm/yyyy
    - USA: mm/dd/yyyy
    - Germany: dd.mm.yyyy
    - China: yyyy年mm月dd日

    Args:
        dt: Datetime to format (datetime, ISO string, RFC 2822, or timestamp)
        language: Language code (fr, en, de, es, it, zh-CN)
        timezone: IANA timezone for display
        format_type: Format type to use:
            - "full": Full date with day name and year
            - "short": Numeric date (dd/mm/yyyy, mm/dd/yyyy, dd.mm.yyyy)
            - "relative": Relative date (Aujourd'hui, Hier, Lundi, dd/mm)
            - "day_month": Day and month only (for birthdays)
        include_time: If True, appends time (HH:MM) with localized preposition

    Returns:
        Formatted date string following country conventions
    """
    from src.core.i18n_dates import get_day_name, get_month_name, get_time_connector
    from src.core.time_utils import convert_to_user_timezone

    # Parse and convert to user timezone using existing infrastructure
    parsed_dt = convert_to_user_timezone(dt, timezone)
    if parsed_dt is None:
        # Fallback for unparseable strings
        if isinstance(dt, str):
            return dt[:10] if len(dt) >= 10 else dt
        return ""

    day_name = get_day_name(parsed_dt.weekday(), language)
    month_name = get_month_name(parsed_dt.month, language)
    day_num = parsed_dt.day
    month_num = parsed_dt.month
    year = parsed_dt.year

    # Build time suffix if requested (locale-aware)
    time_suffix = ""
    if include_time:
        if language == "en":
            time_str = parsed_dt.strftime("%I:%M %p").lstrip("0")  # 12h format
        else:
            time_str = parsed_dt.strftime("%H:%M")  # 24h format
        connector = get_time_connector(language)
        time_suffix = f" {connector} {time_str}" if connector else f" {time_str}"

    # FORMAT based on type and country conventions
    if format_type == "full":
        if language == "fr":
            base = f"{day_name} {day_num} {month_name} {year}"
        elif language == "de":
            base = f"{day_name}, {day_num}. {month_name} {year}"
        elif language == "es":
            base = f"{day_name}, {day_num} de {month_name} de {year}"
        elif language == "it":
            base = f"{day_name}, {day_num} {month_name} {year}"
        elif language == "zh-CN":
            base = f"{year}年{month_num}月{day_num}日 {day_name}"
        else:  # en
            base = f"{day_name}, {month_name} {day_num}, {year}"
        return f"{base}{time_suffix}"

    elif format_type == "short":
        # Country-specific numeric FORMAT
        if language == "en":
            base = f"{month_num:02d}/{day_num:02d}/{year}"  # mm/dd/yyyy
        elif language == "de":
            base = f"{day_num:02d}.{month_num:02d}.{year}"  # dd.mm.yyyy
        elif language == "zh-CN":
            base = f"{year}年{month_num}月{day_num}日"
        else:  # fr, es, it
            base = f"{day_num:02d}/{month_num:02d}/{year}"  # dd/mm/yyyy
        return f"{base}{time_suffix}"

    elif format_type == "day_month":
        # For birthdays - no year
        if language == "en":
            base = f"{month_name} {day_num}"
        elif language == "de":
            base = f"{day_num}. {month_name}"
        elif language == "zh-CN":
            base = f"{month_num}月{day_num}日"
        else:  # fr, es, it
            base = f"{day_num} {month_name}"
        return base  # No time for day_month format

    else:  # relative
        # Get current time for comparison
        try:
            from zoneinfo import ZoneInfo

            now = datetime.now(ZoneInfo(timezone))
        except Exception:
            now = datetime.now(parsed_dt.tzinfo) if parsed_dt.tzinfo else datetime.now()

        diff = now.date() - parsed_dt.date()

        if diff.days == 0:
            base = TODAY_LABELS.get(language, TODAY_LABELS["en"])
        elif diff.days == 1:
            base = YESTERDAY_LABELS.get(language, YESTERDAY_LABELS["en"])
        elif diff.days < 7:
            base = day_name
        else:
            # Short date without year - country-specific FORMAT
            if language == "en":
                base = f"{month_num:02d}/{day_num:02d}"
            elif language == "de":
                base = f"{day_num:02d}.{month_num:02d}"
            elif language == "zh-CN":
                base = f"{month_num}月{day_num}日"
            else:  # fr, es, it
                base = f"{day_num:02d}/{month_num:02d}"
        return f"{base}{time_suffix}"


def format_relative_date(
    dt: datetime | str | int | None,
    language: str = "fr",
    timezone: str = "Europe/Paris",
    include_time: bool = False,
) -> str:
    """
    Format datetime as relative string with optional time.

    Wrapper around format_date for backward compatibility.

    Args:
        dt: Datetime to format
        language: Language code
        timezone: IANA timezone
        include_time: If True, includes time (HH:MM)

    Returns:
        Localized relative date string
    """
    return format_date(dt, language, timezone, "relative", include_time)


def format_full_date(
    dt: datetime | str | int | None,
    language: str = "fr",
    timezone: str = "Europe/Paris",
    include_time: bool = False,
) -> str:
    """
    Format datetime as full localized date string.

    Wrapper around format_date for backward compatibility.

    Unlike format_relative_date which shows "Lundi" for recent dates,
    this function always shows the full date with day name, day number,
    month name, and year.

    Args:
        dt: Datetime to format (datetime, ISO string, RFC 2822, or timestamp)
        language: Language code (fr, en, es, de, it, zh-CN)
        timezone: IANA timezone for display
        include_time: If True, appends time (HH:MM) with localized preposition

    Returns:
        Localized full date string like:
        - "Samedi 3 janvier 2026" (fr)
        - "Saturday, January 3, 2026" (en)
        - "Samstag, 3. Januar 2026" (de)
    """
    return format_date(dt, language, timezone, "full", include_time)


def format_time(
    dt: datetime | str | None,
    language: str = "fr",
    timezone: str = "Europe/Paris",
) -> str:
    """
    Format time with locale-aware conventions.

    - English (en): 12-hour format with AM/PM (e.g., "2:30 PM")
    - Other languages: 24-hour format (e.g., "14:30")

    Args:
        dt: Datetime to format
        language: Language code for format convention
        timezone: IANA timezone for conversion

    Returns:
        Formatted time string
    """
    if not dt:
        return ""

    if isinstance(dt, str):
        try:
            if "T" in dt:
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            else:
                return dt
        except ValueError:
            return dt  # type: ignore

    if not isinstance(dt, datetime):
        return str(dt)

    # Convert to target timezone if aware
    try:
        import zoneinfo

        if dt.tzinfo is not None:
            target_tz = zoneinfo.ZoneInfo(timezone)
            dt = dt.astimezone(target_tz)
    except (ImportError, KeyError):
        pass

    # Format based on language convention
    if language == "en":
        # 12-hour format for English
        return dt.strftime("%I:%M %p").lstrip("0")
    else:
        # 24-hour format for other languages
        return dt.strftime("%H:%M")


def format_duration(
    start: datetime | str,
    end: datetime | str,
    language: str = "fr",
) -> str:
    """
    Format duration between two datetimes with localized labels.

    Args:
        start: Start datetime
        end: End datetime
        language: Language code for labels

    Returns:
        Formatted duration (e.g., "2h30", "45min", "1 hour 30 min")
    """
    if isinstance(start, str):
        try:
            start = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if isinstance(end, str):
        try:
            end = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except ValueError:
            return ""

    if not isinstance(start, datetime) or not isinstance(end, datetime):
        return ""

    delta = end - start
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        return ""

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60

    # Localized labels
    if language == "en":
        if hours > 0 and minutes > 0:
            h_label = "hour" if hours == 1 else "hours"
            return f"{hours} {h_label} {minutes} min"
        elif hours > 0:
            h_label = "hour" if hours == 1 else "hours"
            return f"{hours} {h_label}"
        else:
            return f"{minutes} min"
    elif language == "de":
        if hours > 0 and minutes > 0:
            return f"{hours} Std. {minutes} Min."
        elif hours > 0:
            return f"{hours} Std."
        else:
            return f"{minutes} Min."
    elif language == "zh-CN":
        if hours > 0 and minutes > 0:
            return f"{hours}小时{minutes}分钟"
        elif hours > 0:
            return f"{hours}小时"
        else:
            return f"{minutes}分钟"
    else:
        # French, Spanish, Italian - compact format
        if hours > 0 and minutes > 0:
            return f"{hours}h{minutes:02d}"
        elif hours > 0:
            return f"{hours}h"
        else:
            return f"{minutes}min"


def stars_rating(rating: float | None, max_stars: int = 5) -> str:
    """
    Generate star rating HTML with Material Symbols.

    Delegates to render_star_rating from icons module.
    """
    return render_star_rating(rating, max_stars)


def html_to_text(html_content: str | None, preserve_links: bool = False) -> str:
    """
    Convert HTML email content to clean, readable plain text.

    Handles common email HTML patterns including:
    - Block elements (div, p, br, hr) → newlines
    - Lists (ul, ol, li) → bullet points
    - Links → [text](url) or just text
    - Tables → basic text extraction
    - Whitespace normalization
    - HTML entities decoding

    Args:
        html_content: Raw HTML string from email body
        preserve_links: If True, format links as [text](url)

    Returns:
        Clean plain text suitable for display
    """
    if not html_content:
        return ""

    text = str(html_content)

    # 1. Decode HTML entities first
    text = html.unescape(text)

    # 2. Remove <head>, <style>, <script> blocks entirely
    text = re.sub(r"<head[^>]*>.*?</head>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)

    # 3. Handle links: extract text and optionally URL
    if preserve_links:
        # Format: [link text](url)
        def link_replacer(match: re.Match) -> str:
            attrs = match.group(1)
            link_text = match.group(2)
            href_match = re.search(r'href=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            if href_match and link_text.strip():
                url = href_match.group(1)
                # Skip mailto: links, just show email
                if url.startswith("mailto:"):
                    return link_text.strip()  # type: ignore[no-any-return]
                return f"[{link_text.strip()}]({url})"
            return link_text.strip()  # type: ignore[no-any-return]

        text = re.sub(
            r"<a\s+([^>]*)>(.*?)</a>", link_replacer, text, flags=re.DOTALL | re.IGNORECASE
        )
    else:
        # Just extract link text
        text = re.sub(r"<a\s+[^>]*>(.*?)</a>", r"\1", text, flags=re.DOTALL | re.IGNORECASE)

    # 4. Handle block elements with proper spacing
    # Headers → newline before and after
    text = re.sub(
        r"<h[1-6][^>]*>(.*?)</h[1-6]>", r"\n\n\1\n\n", text, flags=re.DOTALL | re.IGNORECASE
    )

    # Paragraphs → double newline
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "", text, flags=re.IGNORECASE)

    # Divs → single newline (common in email formatting)
    text = re.sub(r"</div>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<div[^>]*>", "", text, flags=re.IGNORECASE)

    # Line breaks
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)

    # Horizontal rules → separator line
    text = re.sub(r"<hr\s*/?>", "\n---\n", text, flags=re.IGNORECASE)

    # 5. Handle lists
    text = re.sub(r"<li[^>]*>", "\n• ", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[ou]l[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</[ou]l>", "\n", text, flags=re.IGNORECASE)

    # 6. Handle tables (basic: extract cell content with spacing)
    text = re.sub(r"<tr[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</tr>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<t[dh][^>]*>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"</t[dh]>", " | ", text, flags=re.IGNORECASE)
    text = re.sub(r"</?table[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?tbody[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</?thead[^>]*>", "", text, flags=re.IGNORECASE)

    # 7. Handle blockquotes (common in email replies)
    text = re.sub(r"<blockquote[^>]*>", "\n> ", text, flags=re.IGNORECASE)
    text = re.sub(r"</blockquote>", "\n", text, flags=re.IGNORECASE)

    # 8. Bold/italic → keep text, remove tags
    text = re.sub(r"</?(?:b|strong)[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(?:i|em)[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(?:u|s|strike)[^>]*>", "", text, flags=re.IGNORECASE)

    # 9. Remove all remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # 10. Normalize whitespace
    # Multiple spaces → single space
    text = re.sub(r"[ \t]+", " ", text)

    # Multiple newlines → max 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Clean up leading/trailing whitespace on each line
    lines = [line.strip() for line in text.split("\n")]

    # Remove consecutive empty lines (keep max 1 empty line between paragraphs)
    cleaned_lines = []
    previous_was_empty = False
    for line in lines:
        if line:  # Non-empty line
            cleaned_lines.append(line)
            previous_was_empty = False
        elif not previous_was_empty:  # First empty line after content
            cleaned_lines.append(line)
            previous_was_empty = True
        # Skip consecutive empty lines

    text = "\n".join(cleaned_lines)

    # Remove empty lines at start/end
    text = text.strip()

    # 11. Handle common email signatures patterns (optional cleanup)
    # Remove excessive dashes often used as separators
    text = re.sub(r"[-_]{5,}", "---", text)

    return text


def format_email_body(
    body: str | None,
    max_length: int = 500,
    preserve_links: bool = False,
) -> tuple[str, bool]:
    """
    Format email body for display with truncation.

    Args:
        body: Raw email body (HTML or plain text)
        max_length: Maximum characters to display
        preserve_links: If True, format links as [text](url)

    Returns:
        Tuple of (formatted_text, is_truncated)
    """
    if not body:
        return "", False

    # Convert HTML to text
    text = html_to_text(body, preserve_links=preserve_links)

    # Truncate if needed
    is_truncated = len(text) > max_length
    if is_truncated:
        # Try to truncate at word boundary
        truncated = text[:max_length]
        last_space = truncated.rfind(" ")
        if last_space > max_length * 0.8:  # Only if we don't lose too much
            truncated = truncated[:last_space]
        text = truncated

    return text, is_truncated


def markdown_links_to_html(
    text: str,
    url_shorten_threshold: int = 50,
    link_label: str = "Lien",
) -> str:
    """
    Convert Markdown links [text](url) to HTML <a> tags with URL shortening.

    This is a utility function for converting Markdown-style links to proper
    HTML hyperlinks, with support for shortening long URLs.

    Handles:
    - Escapes regular text for HTML safety
    - Converts [text](url) to <a href="url">text</a>
    - Shortens display text for long URLs (> threshold)
    - Preserves all other text content

    Args:
        text: Text with potential Markdown links
        url_shorten_threshold: URLs longer than this show link_label instead
        link_label: Label to display for shortened URLs (default: "Lien")

    Returns:
        HTML-safe string with clickable links

    Example:
        >>> markdown_links_to_html("Click [here](https://example.com)", 50, "Link")
        'Click <a href="https://example.com" target="_blank" rel="noopener">here</a>'

        >>> markdown_links_to_html("[](https://very-long-url.com/path)", 30, "Link")
        '<a href="https://very-long-url.com/path" target="_blank" rel="noopener">Link</a>'
    """
    # Pattern to match Markdown links: [text](url)
    link_pattern = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

    result_parts = []
    last_end = 0

    for match in link_pattern.finditer(text):
        # Add escaped text before this match
        before_text = text[last_end : match.start()]
        result_parts.append(escape_html(before_text))

        link_text = match.group(1)
        url = match.group(2)

        # Determine display text: use link_text if provided, else shorten URL
        if link_text.strip():
            display_text = link_text
        elif len(url) > url_shorten_threshold:
            display_text = link_label
        else:
            display_text = url

        # Build HTML link
        escaped_url = escape_html(url)
        escaped_display = escape_html(display_text)
        result_parts.append(
            f'<a href="{escaped_url}" target="_blank" rel="noopener">{escaped_display}</a>'
        )

        last_end = match.end()

    # Add remaining text after last match
    if last_end < len(text):
        result_parts.append(escape_html(text[last_end:]))

    return "".join(result_parts)


def build_directions_url(destination: str) -> str:
    """
    Build a Google Maps Directions URL for the given destination.

    Uses Google Maps Directions API format which will automatically use
    the user's current location (GPS on mobile, or prompt on desktop).

    This is the centralized function for all address/location links across
    all card components to ensure consistent behavior.

    Args:
        destination: Address or location name to navigate to

    Returns:
        Google Maps Directions URL

    Example:
        >>> build_directions_url("123 Main St, Paris")
        'https://www.google.com/maps/dir/?api=1&destination=123%20Main%20St%2C%20Paris'
    """
    from urllib.parse import quote

    encoded_destination = quote(destination, safe="")
    return f"https://www.google.com/maps/dir/?api=1&destination={encoded_destination}"


def build_place_url(place_id: str | None = None, query: str | None = None) -> str:
    """
    Build a Google Maps Place URL to view a place's page (not directions).

    Args:
        place_id: Google Place ID (e.g., 'ChIJ...')
        query: Fallback search query (name + address) if no place_id

    Returns:
        Google Maps Place/Search URL

    Example:
        >>> build_place_url(place_id="ChIJN1t_tDeuEmsRUsoyG83frY4")
        'https://www.google.com/maps/place/?q=place_id:ChIJN1t_tDeuEmsRUsoyG83frY4'
        >>> build_place_url(query="Eiffel Tower, Paris")
        'https://www.google.com/maps/search/?api=1&query=Eiffel%20Tower%2C%20Paris'
    """
    from urllib.parse import quote

    if place_id:
        # Direct place page with place_id
        return f"https://www.google.com/maps/place/?q=place_id:{place_id}"
    elif query:
        # Search URL as fallback
        encoded_query = quote(query, safe="")
        return f"https://www.google.com/maps/search/?api=1&query={encoded_query}"
    return ""


# =============================================================================
# Response Wrapper Helpers (v3.0)
# =============================================================================


def wrap_with_response(
    card_html: str,
    assistant_comment: str | None = None,
    suggested_actions: list[dict[str, str]] | None = None,
    domain: str = "",
    with_separators: bool = True,
    with_top_separator: bool | None = None,
    with_bottom_separator: bool | None = None,
    show_action_buttons: bool | None = None,
) -> str:
    """
    Wrap a card with LLM assistant comment and suggested actions.

    Creates the structure with separators:
    1. Top separator (optional - for first element only)
    2. Assistant comment (above card, optional)
    3. Card content (middle)
    4. Suggested actions (below card, optional)
    5. Bottom separator (optional - for last element only)

    Args:
        card_html: The rendered card HTML
        assistant_comment: Optional text comment from the assistant
        suggested_actions: List of action dicts with keys:
            - icon: Emoji or icon string
            - label: Button text
            - action: Action identifier (e.g., "reply", "archive")
            - url: Optional URL for link actions
        domain: Domain name for action button styling (e.g., "email", "calendar")
        with_separators: Legacy param - if True, adds both separators (default)
        with_top_separator: If set, overrides with_separators for top only
        with_bottom_separator: If set, overrides with_separators for bottom only
        show_action_buttons: If None, reads from V3_DISPLAY_SHOW_ACTION_BUTTONS env config.
            If False, action buttons are not rendered even if suggested_actions is provided.

    Returns:
        Wrapped HTML with all zones and separators
    """
    # Determine action button visibility from config if not explicitly set
    if show_action_buttons is None:
        from src.core.config.agents import get_v3_display_config

        show_action_buttons = get_v3_display_config().show_action_buttons

    # Determine separator visibility
    show_top = with_top_separator if with_top_separator is not None else with_separators
    show_bottom = with_bottom_separator if with_bottom_separator is not None else with_separators

    parts = []

    # Top separator (uses centralized separator_bold from config.py)
    if show_top:
        parts.append(separator_bold())

    parts.append('<div class="lia-response-wrapper">')

    # Zone 1: Assistant comment
    if assistant_comment:
        escaped_comment = escape_html(assistant_comment)
        parts.append(f'<div class="lia-assistant-comment">{escaped_comment}</div>')

    # Zone 2: Card content
    parts.append(card_html)

    # Zone 3: Suggested actions (only if enabled via config)
    if suggested_actions and show_action_buttons:
        parts.append('<div class="lia-suggested-actions">')
        for action in suggested_actions:
            parts.append(
                render_action_button(
                    icon=action.get("icon", ""),
                    label=action.get("label", ""),
                    action=action.get("action", ""),
                    url=action.get("url"),
                    domain=domain,
                )
            )
        parts.append("</div>")

    parts.append("</div>")

    # Bottom separator (uses centralized separator_bold from config.py)
    if show_bottom:
        parts.append(separator_bold())

    return compact_html("".join(parts))


def render_action_button(
    icon: str,
    label: str,
    action: str = "",
    url: str | None = None,
    domain: str = "",
    primary: bool = False,
) -> str:
    """
    Render a suggested action button with Material Symbols icon.

    Args:
        icon: Material Symbols icon name (e.g., "mail", "reply", "forward")
        label: Button text
        action: Action identifier for JavaScript handlers
        url: Optional URL (renders as <a> instead of <button>)
        domain: Domain for styling (email, calendar, contact, etc.)
        primary: If True, use primary button styling

    Returns:
        Button or anchor HTML
    """
    classes = ["lia-action-btn"]
    if domain:
        classes.append(f"lia-action-btn--{domain}")
    if primary:
        classes.append("lia-action-btn--primary")

    class_str = " ".join(classes)
    # Use Material Symbols format for icons
    icon_html = (
        (
            f'<span class="lia-action-btn__icon" aria-hidden="true">'
            f'<span class="material-symbols-outlined">{icon}</span>'
            f"</span>"
        )
        if icon
        else ""
    )
    escaped_label = escape_html(label)

    if url:
        return (
            f'<a href="{escape_html(url)}" class="{class_str}" target="_blank" rel="noopener">'
            f"{icon_html}{escaped_label}</a>"
        )
    else:
        data_attr = f'data-action="{escape_html(action)}"' if action else ""
        return f'<button type="button" class="{class_str}" {data_attr}>{icon_html}{escaped_label}</button>'


# =============================================================================
# Collapsible Component Helpers
# =============================================================================


def render_collapsible(
    trigger_text: str,
    content_html: str,
    initially_open: bool = False,
    language: str = "fr",
) -> str:
    """
    Render a collapsible section using <details>/<summary>.

    Args:
        trigger_text: Text for the trigger/toggle button
        content_html: HTML content to show when expanded
        initially_open: If True, section starts expanded
        language: Language for accessibility labels

    Returns:
        Collapsible HTML using native <details>/<summary>
    """
    if not content_html:
        return ""

    open_attr = " open" if initially_open else ""
    escaped_trigger = escape_html(trigger_text)

    return compact_html(
        f"""
        <div class="lia-collapsible-wrapper">
            <hr class="lia-separator lia-separator--collapsible" />
            <details class="lia-collapsible"{open_attr}>
                <summary class="lia-collapsible__trigger">
                    <span>{escaped_trigger}</span>
                    <span class="lia-collapsible__icon">{icon(Icons.EXPAND)}</span>
                </summary>
                <div class="lia-collapsible__content">
                    {content_html}
                </div>
            </details>
        </div>
    """
    )


# =============================================================================
# Label/Badge Helpers
# =============================================================================


def render_labels(
    labels: list[str | dict[str, str]],
    max_labels: int = 5,
) -> str:
    """
    Render a list of label chips.

    Args:
        labels: List of label strings or dicts with {name, type}
            - type can be: "default", "important", "category", "social", "promotions"
        max_labels: Maximum labels to display

    Returns:
        HTML for label chips
    """
    if not labels:
        return ""

    labels = labels[:max_labels]
    label_html_parts = []

    for label in labels:
        if isinstance(label, dict):
            name = escape_html(label.get("name", ""))
            label_type = label.get("type", "default")
        else:
            name = escape_html(str(label))
            # Auto-detect type from common label names
            label_lower = name.lower()
            if label_lower in ("important", "starred", "urgent"):
                label_type = "important"
            elif label_lower in ("social", "forums"):
                label_type = "social"
            elif label_lower in ("promotions", "updates"):
                label_type = "promotions"
            elif label_lower.startswith("category_"):
                label_type = "category"
            else:
                label_type = "default"

        type_class = f"lia-label--{label_type}" if label_type != "default" else ""
        label_html_parts.append(f'<span class="lia-label {type_class}">{name}</span>')

    return f'<div class="lia-labels">{" ".join(label_html_parts)}</div>'


# =============================================================================
# Attachment Helpers
# =============================================================================

# ATTACHMENT_ICONS moved to icons.py as ATTACHMENT_TYPE_ICONS
# Use get_attachment_icon() from icons module instead


def get_attachment_type(
    filename: str | None = None,
    mime_type: str | None = None,
) -> tuple[str, str]:
    """
    Get attachment icon and CSS class from filename or MIME type.

    Delegates to get_attachment_icon from icons module for Material Symbols.

    Args:
        filename: File name with extension
        mime_type: MIME type string

    Returns:
        Tuple of (icon_name, css_class_suffix)
    """
    return get_attachment_icon(filename, mime_type)


def format_file_size(size_bytes: int | None) -> str:
    """Format file size in human-readable form."""
    if not size_bytes:
        return ""

    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size_bytes) < 1024.0:
            if unit == "B":
                return f"{size_bytes}{unit}"
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0  # type: ignore
    return f"{size_bytes:.1f}TB"


def render_attachment(
    filename: str,
    size: int | None = None,
    mime_type: str | None = None,
    url: str | None = None,
) -> str:
    """
    Render a single attachment chip with Material Symbols icon.

    Args:
        filename: File name
        size: File size in bytes
        mime_type: MIME type
        url: Download URL

    Returns:
        Attachment HTML
    """
    icon_name, type_class = get_attachment_type(filename, mime_type)
    escaped_name = escape_html(filename)
    size_html = (
        f'<span class="lia-attachment__size">({format_file_size(size)})</span>' if size else ""
    )

    tag = "a" if url else "span"
    href = f'href="{escape_html(url)}" target="_blank" rel="noopener"' if url else ""

    # Use Material Symbols format for icon
    icon_html = (
        f'<span class="lia-attachment__icon" aria-hidden="true">'
        f'<span class="material-symbols-outlined">{icon_name}</span>'
        f"</span>"
    )

    return compact_html(
        f"""
        <{tag} class="lia-attachment lia-attachment--{type_class}" {href}>
            {icon_html}
            <span class="lia-attachment__name" title="{escaped_name}">{escaped_name}</span>
            {size_html}
        </{tag}>
    """
    )


def render_attachments(
    attachments: list[dict[str, Any]],
    max_attachments: int = 5,
) -> str:
    """
    Render a list of attachment chips.

    Args:
        attachments: List of attachment dicts with keys:
            - filename (required)
            - size (optional, in bytes)
            - mimeType (optional)
            - url (optional)
        max_attachments: Maximum attachments to display

    Returns:
        Attachments container HTML
    """
    if not attachments:
        return ""

    attachments = attachments[:max_attachments]
    parts = ['<div class="lia-attachments">']

    for att in attachments:
        # Build proxy URL for Gmail attachments when IDs are available
        att_id = att.get("attachment_id")
        msg_id = att.get("message_id")
        if att_id and msg_id:
            from src.core.config import settings

            fname = quote(att.get("filename", "attachment"), safe="")
            safe_msg_id = quote(msg_id, safe="")
            safe_att_id = quote(att_id, safe="")
            api_base = settings.api_url.rstrip("/")
            url = f"{api_base}/api/v1/connectors/gmail/attachment/{safe_msg_id}/{safe_att_id}?filename={fname}"
        else:
            url = att.get("url", att.get("downloadUrl", att.get("gmail_url")))

        parts.append(
            render_attachment(
                filename=att.get("filename", att.get("name", "file")),
                size=att.get("size"),
                mime_type=att.get("mimeType", att.get("mime_type")),
                url=url,
            )
        )

    parts.append("</div>")
    return compact_html("".join(parts))


# =============================================================================
# Indicator Helpers
# =============================================================================


def render_unread_indicator() -> str:
    """Render pulsing unread indicator dot."""
    return '<span class="lia-indicator-unread"></span>'


def render_thread_badge(count: int) -> str:
    """Render thread message count badge."""
    if count <= 1:
        return ""
    return f'<span class="lia-badge-thread">{count} msg</span>'


def render_attachment_badge(count: int) -> str:
    """Render attachment count badge with Material Symbols icon."""
    if count <= 0:
        return ""
    icon_html = (
        f'<span class="lia-badge-attachment__icon" aria-hidden="true">'
        f'<span class="material-symbols-outlined">{Icons.ATTACHMENT}</span>'
        f"</span>"
    )
    return f'<span class="lia-badge-attachment">{icon_html}{count}</span>'


# =============================================================================
# Card Utility Helpers - Standardized Card Structure
# These helpers use the new .lia-card__* CSS utilities for consistent card layouts
# =============================================================================


def render_badges(
    badges: list[dict[str, str]],
    max_badges: int = 4,
) -> str:
    """
    Render a list of badge chips using existing .lia-badge CSS.

    Different from render_labels() which is for category labels.
    Badges are for status/counts (e.g., "3 messages", "Urgent").

    Args:
        badges: List of badge dicts with keys:
            - text (required): Badge text
            - variant (optional): primary, success, warning, danger, info, subtle
            - icon (optional): Material Symbols icon name
        max_badges: Maximum badges to display

    Returns:
        HTML for badge chips wrapped in .lia-badges container
    """
    if not badges:
        return ""

    badges = badges[:max_badges]
    parts = ['<div class="lia-badges">']

    for badge in badges:
        text = escape_html(badge.get("text", ""))
        variant = badge.get("variant", "subtle")
        icon_name = badge.get("icon")

        variant_class = f"lia-badge--{variant}" if variant != "default" else ""
        icon_html = f"{icon(icon_name)} " if icon_name else ""

        parts.append(f'<span class="lia-badge {variant_class}">{icon_html}{text}</span>')

    parts.append("</div>")
    return compact_html("".join(parts))


def render_card_header(
    title: str,
    url: str | None = None,
    subtitle: str | None = None,
    meta: str | None = None,
    badges: list[dict[str, str]] | None = None,
) -> str:
    """
    Render standardized card header row.

    Uses .lia-card__header CSS layout with main/end sections.

    Args:
        title: Card title text
        url: Optional link URL for title (adds underline effect)
        subtitle: Optional subtitle text below title
        meta: Optional meta text (date, count, etc.) - right aligned
        badges: Optional list of badge dicts for render_badges()

    Returns:
        Compacted HTML for card header

    Example:
        >>> render_card_header(
        ...     title="Meeting Notes",
        ...     url="https://...",
        ...     subtitle="Project Alpha",
        ...     meta="Today",
        ...     badges=[{"text": "Important", "variant": "warning"}]
        ... )
    """
    title_class = "lia-card__title lia-title-underline" if url else "lia-card__title"
    if url:
        title_tag = f'<a href="{escape_html(url)}" class="{title_class}">{escape_html(title)}</a>'
    else:
        title_tag = f'<span class="{title_class}">{escape_html(title)}</span>'

    subtitle_html = (
        f'<div class="lia-card__subtitle">{escape_html(subtitle)}</div>' if subtitle else ""
    )
    meta_html = f'<span class="lia-card__meta">{escape_html(meta)}</span>' if meta else ""
    badges_html = render_badges(badges) if badges else ""

    return compact_html(
        f"""
        <div class="lia-card__header">
            <div class="lia-card__header-main">
                {title_tag}
                {subtitle_html}
            </div>
            <div class="lia-card__header-end">
                {meta_html}
                {badges_html}
            </div>
        </div>
    """
    )


def render_detail_item(
    icon_name: str,
    content: str,
    url: str | None = None,
) -> str:
    """
    Render a detail item with icon (address, phone, email, etc.).

    Uses .lia-detail-item CSS utility for consistent icon + text layout.

    Args:
        icon_name: Material Symbols icon name (e.g., "location_on", "phone")
        content: Text content to display
        url: Optional link URL (makes content clickable)

    Returns:
        Compacted HTML for detail item

    Example:
        >>> render_detail_item("phone", "+33 1 23 45 67 89", url="tel:+33123456789")
        >>> render_detail_item("location_on", "123 Main St, Paris")
    """
    if url:
        content_html = f'<a href="{escape_html(url)}">{escape_html(content)}</a>'
    else:
        content_html = escape_html(content)

    return compact_html(
        f"""<div class="lia-detail-item">
        {icon(icon_name)}
        <span>{content_html}</span>
    </div>"""
    )


def render_quote_block(
    content: str,
    accent_color: str | None = None,
) -> str:
    """
    Render a quote/description block with accent border.

    Uses .lia-quote-block CSS utility for bordered text blocks.
    Useful for bios, descriptions, notes, etc.

    Args:
        content: Text content (will be HTML escaped)
        accent_color: Optional CSS color value for left border
                     (defaults to --lia-primary via CSS)

    Returns:
        HTML for quote block

    Example:
        >>> render_quote_block("This is a bio text...")
        >>> render_quote_block("Important note", accent_color="var(--lia-warning)")
    """
    style = f' style="border-left-color: {accent_color}"' if accent_color else ""
    return f'<div class="lia-quote-block"{style}>{escape_html(content)}</div>'
