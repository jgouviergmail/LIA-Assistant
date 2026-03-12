"""
Field Extraction Libraries for Google API Responses.

This module provides reusable field extraction utilities for Google API responses.
The static _extract_* methods are used throughout the codebase for consistent
data extraction from raw Google API responses.

Architecture:
- BaseFormatter: Abstract base with format_item() template method
- ContactsFormatter: Field extractors for Google People API
- GmailFormatter: Field extractors for Gmail API

Key Usage Patterns:
1. Static extraction methods (ACTIVELY USED):
   - ContactsFormatter._extract_emails(person)
   - ContactsFormatter._extract_phones(person)
   - GmailFormatter._extract_body_truncated(message)
   - GmailFormatter._extract_attachments(message)

2. Schema extraction (ACTIVELY USED):
   - FIELD_EXTRACTORS dict used by SchemaExtractor
   - OPERATION_DEFAULT_FIELDS dict for operation-specific fields

3. format_item() for single item formatting (ACTIVELY USED):
   - Used by schema_extractor.py to instantiate formatters

Usage Example:
    from src.domains.agents.tools.formatters import ContactsFormatter, GmailFormatter

    # Extract specific fields from raw API data
    emails = ContactsFormatter._extract_emails(person)
    body = GmailFormatter._extract_body_truncated(message)
    attachments = GmailFormatter._extract_attachments(message)

    # Schema extraction for tool validation
    from src.domains.agents.tools.schema_extractor import SchemaExtractor
    extractor = SchemaExtractor()
    schema = extractor.extract_from_formatter(ContactsFormatter, operation="search")
"""

import html
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import structlog

from src.core.field_names import (
    FIELD_METADATA,
    FIELD_RESOURCE_NAME,
)
from src.core.i18n_api_messages import APIMessages
from src.core.i18n_dates import (
    get_day_name,
    get_month_name,
    get_time_connector,
)

logger = structlog.get_logger(__name__)


class BaseFormatter(ABC):
    """
    Abstract base formatter for tool responses.

    Provides common infrastructure for formatting API results into standardized
    JSON responses consumed by LLMs.

    Handles automatically:
    - Success/error envelope
    - Timestamp metadata
    - Cache freshness tracking
    - Data source transparency
    - JSON serialization with Unicode support
    """

    def __init__(self, tool_name: str, operation: str) -> None:
        """
        Initialize formatter.

        Args:
            tool_name: Tool identifier (e.g., "search_contacts_tool")
            operation: Operation name for metrics (e.g., "search", "list")
        """
        self.tool_name = tool_name
        self.operation = operation
        self.logger = logger.bind(tool=tool_name, operation=operation)

    @abstractmethod
    def format_item(
        self, raw_item: dict[str, Any], fields: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Format a single raw API item.

        Subclasses must implement this to transform raw API response
        into clean, LLM-friendly dict.

        Args:
            raw_item: Raw item from API (e.g., Google People person object)
            fields: List of fields to include (None = all fields)

        Returns:
            Formatted item dict
        """
        pass

    @abstractmethod
    def _get_items_key(self) -> str:
        """
        Get the key for items list in response.

        Returns:
            Key name (e.g., "contacts", "emails", "events")
        """
        pass


class ContactsFormatter(BaseFormatter):
    """
    Formatter for Google Contacts responses.

    Handles all Google People API person object formatting with field extraction.
    """

    # Field extractors (reusable across all contact tools)
    # Maps Google API field names to extraction functions
    # Reference: https://developers.google.com/people/api/rest/v1/people
    FIELD_EXTRACTORS: dict[str, Callable[[dict[str, Any]], Any]] = {
        # Always included
        FIELD_RESOURCE_NAME: lambda person: person.get("resourceName", ""),
        # IDENTITY (9 fields)
        "photos": lambda person: ContactsFormatter._extract_photos(person),
        "names": lambda person: ContactsFormatter._extract_name(person),
        "nicknames": lambda person: ContactsFormatter._extract_nicknames(person),
        "emailAddresses": lambda person: ContactsFormatter._extract_emails(person),
        "phoneNumbers": lambda person: ContactsFormatter._extract_phones(person),
        "addresses": lambda person: ContactsFormatter._extract_addresses(person),
        "locations": lambda person: ContactsFormatter._extract_locations(person),
        "imClients": lambda person: ContactsFormatter._extract_im_clients(person),
        "calendarUrls": lambda person: ContactsFormatter._extract_calendar_urls(person),
        # PERSONNEL (7 fields)
        "birthdays": lambda person: ContactsFormatter._extract_birthdays(person),
        "relations": lambda person: ContactsFormatter._extract_relations(person),
        "events": lambda person: ContactsFormatter._extract_events(person),
        "interests": lambda person: ContactsFormatter._extract_interests(person),
        "biographies": lambda person: ContactsFormatter._extract_biographies(person),
        "occupations": lambda person: ContactsFormatter._extract_occupations(person),
        # "metadata": Technical metadata (sources, object_type) - not useful for end users
        # Kept in code for potential future internal use, but excluded from LLM context
        # lambda person: ContactsFormatter._extract_metadata(person),
        # PROFESSIONNEL (2 fields)
        "organizations": lambda person: ContactsFormatter._extract_organizations(person),
        "skills": lambda person: ContactsFormatter._extract_skills(person),
    }

    # Operation-specific default fields (token optimization)
    # Different operations have different verbosity needs:
    # - list: Minimalist (name, emails, phones) for quick browsing (~100 tokens/contact)
    # - search: Essential identification (name, photo, emails, phones, addresses, birthday) (~200 tokens/contact)
    # - details: Full details with 20 curated fields (~600 tokens/contact)
    OPERATION_DEFAULT_FIELDS = {
        "list": [FIELD_RESOURCE_NAME, "names", "emailAddresses", "phoneNumbers"],
        "search": [
            FIELD_RESOURCE_NAME,
            "names",
            "photos",  # Profile photo for visual identification
            "emailAddresses",
            "phoneNumbers",
            "addresses",
            "birthdays",
        ],
        # Full details: 20 curated fields organized by category
        "details": [
            # IDENTITY (9 fields)
            "photos",
            "names",
            "nicknames",
            "emailAddresses",
            "phoneNumbers",
            "addresses",
            "locations",
            "imClients",
            "calendarUrls",
            # PERSONNEL (7 fields)
            "birthdays",
            "relations",
            "events",
            "interests",
            "biographies",
            "occupations",
            "metadata",
            # PROFESSIONNEL (2 fields)
            "organizations",
            "skills",
            # TECHNIQUE (1 field)
            FIELD_RESOURCE_NAME,
        ],
    }

    # Legacy fallback (for backwards compatibility)
    DEFAULT_FIELDS = [FIELD_RESOURCE_NAME, "names", "emailAddresses", "phoneNumbers"]

    def __init__(
        self,
        tool_name: str,
        operation: str,
        user_timezone: str = "UTC",
        locale: str = "fr-FR",
    ) -> None:
        """
        Initialize Contacts formatter.

        Args:
            tool_name: Tool identifier (e.g., "search_contacts_tool")
            operation: Operation name ("search", "list", "details")
            user_timezone: User's IANA timezone (e.g., "Europe/Paris")
            locale: User's locale (e.g., "fr-FR", "en-US")
        """
        super().__init__(tool_name, operation)
        self.user_timezone = user_timezone
        self.locale = locale

    def format_item(
        self, raw_item: dict[str, Any], fields: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Format a single contact person object.

        Args:
            raw_item: Raw Google People person object
            fields: List of fields to include (None = operation-specific defaults)

        Returns:
            Formatted contact dict
        """
        # Determine fields to include
        if fields is None:
            # Use operation-specific defaults for token optimization
            # Falls back to legacy DEFAULT_FIELDS if operation not recognized
            fields_to_include = self.OPERATION_DEFAULT_FIELDS.get(
                self.operation, self.DEFAULT_FIELDS
            )
            self.logger.debug(
                "using_operation_default_fields",
                operation=self.operation,
                fields_count=len(fields_to_include),
                fields=fields_to_include,
            )
        else:
            # Fields parameter already uses Google API field names
            # Always include resource_name as identifier
            fields_to_include = [FIELD_RESOURCE_NAME]
            for field in fields:
                if field not in fields_to_include:
                    fields_to_include.append(field)

        # Extract fields using extractors
        contact_info: dict[str, Any] = {}
        for field in fields_to_include:
            extractor = self.FIELD_EXTRACTORS.get(field)
            if extractor:
                contact_info[field] = extractor(raw_item)
            else:
                # Unknown field - log warning
                self.logger.warning(
                    "unknown_field_in_formatter",
                    field=field,
                    available_fields=list(self.FIELD_EXTRACTORS.keys()),
                )

        return contact_info

    def _get_items_key(self) -> str:
        """Get the key for contacts list in response."""
        return "contacts"

    # =========================================================================
    # FIELD EXTRACTION HELPERS (from google_contacts_tools.py)
    # =========================================================================

    @staticmethod
    def _extract_name(person: dict[str, Any]) -> str:
        """Extract display name from person object."""
        names = person.get("names", [])
        if names:
            return str(names[0].get("displayName", APIMessages.unknown_name()))
        return APIMessages.unknown_name()

    @staticmethod
    def _extract_emails(person: dict[str, Any]) -> list[dict[str, str]]:
        """
        Extract email addresses with types from person object.

        Returns list of dicts with 'value' and 'type' keys.
        Type can be: home, work, other (from Google API).
        """
        email_addresses = person.get("emailAddresses", [])
        return [
            {
                "value": email.get("value", ""),
                "type": email.get("type", ""),
            }
            for email in email_addresses
            if email.get("value")
        ]

    @staticmethod
    def _extract_phones(person: dict[str, Any]) -> list[dict[str, str]]:
        """
        Extract phone numbers with types from person object.

        Returns list of dicts with 'value' and 'type' keys.
        Type can be: home, work, mobile, main, homeFax, workFax, otherFax, pager, other.
        """
        phone_numbers = person.get("phoneNumbers", [])
        return [
            {
                "value": phone.get("value", ""),
                "type": phone.get("type", ""),
            }
            for phone in phone_numbers
            if phone.get("value")
        ]

    @staticmethod
    def _extract_addresses(person: dict[str, Any]) -> list[dict[str, str]]:
        """
        Extract and normalize addresses from person object.

        Cleans up the formattedValue by:
        - Normalizing line breaks (\\r\\n, \\r → \\n)
        - Removing excessive consecutive line breaks
        - Trimming whitespace on each line
        - Removing empty lines

        Returns clean, multi-line addresses ready for display.
        """
        addresses = person.get("addresses", [])
        result: list[dict[str, str]] = []

        for addr in addresses:
            formatted_value = addr.get("formattedValue", "")
            if not formatted_value:
                continue

            # Normalize line breaks (Windows \\r\\n, Mac \\r → Unix \\n)
            normalized = formatted_value.replace("\r\n", "\n").replace("\r", "\n")

            # Split into lines, strip whitespace, remove empty lines
            lines = [line.strip() for line in normalized.split("\n") if line.strip()]

            # Rejoin with single line breaks
            clean_address = "\n".join(lines)

            result.append(
                {
                    "formatted": clean_address,
                    "type": addr.get("type", ""),
                }
            )

        return result

    @staticmethod
    def _extract_organizations(person: dict[str, Any]) -> list[dict[str, str]]:
        """Extract organizations from person object."""
        organizations = person.get("organizations", [])
        return [
            {
                "name": org.get("name", ""),
                "title": org.get("title", ""),
                "department": org.get("department", ""),
            }
            for org in organizations
        ]

    @staticmethod
    def _extract_birthdays(person: dict[str, Any]) -> list[str]:
        """
        Extract and format birthdays from person object.

        Uses format_google_birthday() for localized, unambiguous date formatting.
        Format: "03 novembre 1975" (without day of week, without time).

        Note: Currently uses default locale "fr-FR". In future, this should receive
        user's locale from ContactsFormatter constructor (similar to GmailFormatter).
        """
        birthdays = person.get("birthdays", [])
        formatted_birthdays: list[str] = []

        for birthday in birthdays:
            date = birthday.get("date", {})
            if date:
                year = date.get("year")
                month = date.get("month")
                day = date.get("day")

                # Use localized date formatter (no ambiguity, proper i18n)
                # Note: For static extractors, use default locale. Instance methods
                # should pass locale from FormattingContext when available.
                from src.core.constants import DEFAULT_LOCALE

                formatted = format_google_birthday(
                    year=year,
                    month=month,
                    day=day,
                    locale=DEFAULT_LOCALE,
                )
                formatted_birthdays.append(formatted)

        return formatted_birthdays

    @staticmethod
    def _extract_photos(person: dict[str, Any]) -> list[dict[str, str]]:
        """
        Extract photos from person object.

        Google API returns:
        - default: true → Generated avatar (letter + colored background)
        - default: absent/false → Real uploaded photo

        We store "is_default" as string "True" for generated avatars.
        Handlers filter based on this to show only real photos.
        """
        photos = person.get("photos", [])
        result: list[dict[str, str]] = []

        for photo in photos:
            url = photo.get("url", "")
            if not url:
                continue

            photo_data: dict[str, str] = {"url": url}

            # Mark if this is a Google-generated avatar (not a real uploaded photo)
            # Google's "default" field = True means it's a generated avatar
            if is_default := photo.get("default"):
                photo_data["is_default"] = str(is_default)

            result.append(photo_data)

        return result

    @staticmethod
    def _extract_nicknames(person: dict[str, Any]) -> list[str]:
        """Extract nicknames from person object."""
        nicknames = person.get("nicknames", [])
        return [nick.get("value", "") for nick in nicknames if nick.get("value")]

    @staticmethod
    def _extract_locations(person: dict[str, Any]) -> list[dict[str, str]]:
        """Extract locations (office, building, desk) from person object."""
        locations = person.get("locations", [])
        result: list[dict[str, str]] = []
        for location in locations:
            value = location.get("value", "")
            if not value:
                continue
            loc_data: dict[str, str] = {"value": value}
            if loc_type := location.get("type"):
                loc_data["type"] = loc_type
            if building_id := location.get("buildingId"):
                loc_data["building_id"] = building_id
            if floor := location.get("floor"):
                loc_data["floor"] = floor
            result.append(loc_data)
        return result

    @staticmethod
    def _extract_im_clients(person: dict[str, Any]) -> list[dict[str, str]]:
        """Extract instant messaging clients from person object."""
        im_clients = person.get("imClients", [])
        result: list[dict[str, str]] = []
        for im in im_clients:
            username = im.get("username", "")
            if not username:
                continue
            im_data: dict[str, str] = {"username": username}
            if protocol := im.get("protocol"):
                im_data["protocol"] = protocol
            if im_type := im.get("type"):
                im_data["type"] = im_type
            if formatted_protocol := im.get("formattedProtocol"):
                im_data["formatted_protocol"] = formatted_protocol
            result.append(im_data)
        return result

    @staticmethod
    def _extract_calendar_urls(person: dict[str, Any]) -> list[dict[str, str]]:
        """Extract calendar URLs from person object."""
        calendar_urls = person.get("calendarUrls", [])
        result: list[dict[str, str]] = []
        for cal in calendar_urls:
            url = cal.get("url", "")
            if not url:
                continue
            cal_data: dict[str, str] = {"url": url}
            if cal_type := cal.get("type"):
                cal_data["type"] = cal_type
            if formatted_type := cal.get("formattedType"):
                cal_data["formatted_type"] = formatted_type
            result.append(cal_data)
        return result

    @staticmethod
    def _extract_relations(person: dict[str, Any]) -> list[dict[str, str]]:
        """Extract relations from person object."""
        relations = person.get("relations", [])
        result: list[dict[str, str]] = []
        for relation in relations:
            person_name = relation.get("person", "")
            if not person_name:
                continue
            rel_data: dict[str, str] = {"person": person_name}
            if rel_type := relation.get("type"):
                rel_data["type"] = rel_type
            if formatted_type := relation.get("formattedType"):
                rel_data["formatted_type"] = formatted_type
            result.append(rel_data)
        return result

    @staticmethod
    def _extract_events(person: dict[str, Any]) -> list[dict[str, str]]:
        """Extract events (anniversary, etc.) from person object."""
        events = person.get("events", [])
        result: list[dict[str, str]] = []
        for event in events:
            date = event.get("date", {})
            if not date:
                continue
            year = date.get("year", "")
            month = date.get("month", "")
            day = date.get("day", "")
            formatted_date = f"{day}/{month}/{year}" if year else f"{day}/{month}"
            event_data: dict[str, str] = {"date": formatted_date}
            if event_type := event.get("type"):
                event_data["type"] = event_type
            if formatted_type := event.get("formattedType"):
                event_data["formatted_type"] = formatted_type
            result.append(event_data)
        return result

    @staticmethod
    def _extract_interests(person: dict[str, Any]) -> list[str]:
        """Extract interests from person object."""
        interests = person.get("interests", [])
        return [interest.get("value", "") for interest in interests if interest.get("value")]

    @staticmethod
    def _extract_biographies(person: dict[str, Any]) -> list[str]:
        """Extract biographies from person object."""
        biographies = person.get("biographies", [])
        return [bio.get("value", "") for bio in biographies if bio.get("value")]

    @staticmethod
    def _extract_occupations(person: dict[str, Any]) -> list[str]:
        """Extract occupations from person object."""
        occupations = person.get("occupations", [])
        return [occ.get("value", "") for occ in occupations if occ.get("value")]

    @staticmethod
    def _extract_skills(person: dict[str, Any]) -> list[str]:
        """Extract skills from person object."""
        skills = person.get("skills", [])
        return [skill.get("value", "") for skill in skills if skill.get("value")]

    @staticmethod
    def _extract_metadata(person: dict[str, Any]) -> dict[str, Any]:
        """Extract metadata from person object."""
        metadata = person.get(FIELD_METADATA, {})
        if not metadata:
            return {}
        result: dict[str, Any] = {}
        if sources := metadata.get("sources"):
            result["sources"] = [
                {"type": source.get("type", ""), "id": source.get("id", "")}
                for source in sources
                if source.get("type")
            ]
        if object_type := metadata.get("objectType"):
            result["object_type"] = object_type
        return result

    def _format_metadata_timestamp(self, timestamp_iso: str) -> str | None:
        """
        Format metadata timestamp for user display.

        Uses default timezone and locale for formatting.

        Note: For instance methods with access to context, pass user_timezone and locale
        from FormattingContext. For static extractors, use centralized defaults.

        Args:
            timestamp_iso: ISO timestamp string

        Returns:
            Formatted timestamp (e.g., "Monday, November 17, 2025 at 2:30 PM")
        """
        from src.core.constants import DEFAULT_LOCALE, DEFAULT_TIMEZONE

        return format_google_datetime(
            timestamp_ms=timestamp_iso,
            user_timezone=DEFAULT_TIMEZONE,
            locale=DEFAULT_LOCALE,
            include_time=True,
        )


# =============================================================================
# DATE/TIME FORMATTING UTILITIES (for all Google Connectors)
# =============================================================================


def format_google_datetime(
    timestamp_ms: int | str | None,
    user_timezone: str = "UTC",
    locale: str = "fr-FR",
    include_time: bool = True,
) -> str:
    """
    Format Gmail/Google timestamp for user display.

    Converts Gmail internalDate (milliseconds since epoch) to user-friendly
    format in user's timezone and locale.

    Args:
        timestamp_ms: Timestamp in milliseconds (Gmail internalDate format) or ISO string
        user_timezone: IANA timezone (e.g., "Europe/Paris", "America/New_York")
        locale: Locale for formatting (e.g., "fr-FR", "en-US")
        include_time: Include time (HH:MM) in output (default True)

    Returns:
        Formatted string:
        - With time: "lundi 03 novembre 2025 à 14:05"
        - Without time: "lundi 03 novembre 2025"

    Examples:
        >>> format_google_datetime(1700000000000, "Europe/Paris", "fr-FR")
        "mercredi 15 novembre 2023 à 01:13"

        >>> format_google_datetime(1700000000000, "America/New_York", "en-US")
        "Tuesday, November 14, 2023 at 7:13 PM"
    """
    if not timestamp_ms:
        # Extract language from locale for i18n
        lang = (
            locale.split("-")[0].lower()
            if locale and "-" in locale
            else (locale.lower() if locale else "fr")
        )
        if locale and locale.lower() == "zh-cn":
            lang = "zh-CN"
        return APIMessages.date_unknown(lang)

    try:
        # Handle both int and string inputs
        if isinstance(timestamp_ms, str):
            # Try parsing as ISO string first
            try:
                dt = datetime.fromisoformat(timestamp_ms.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                # Fallback: try as milliseconds string
                timestamp_ms = int(timestamp_ms)
                dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
        else:
            # Convert milliseconds to datetime (UTC)
            dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)

        # Convert to user timezone
        import zoneinfo

        user_tz = zoneinfo.ZoneInfo(user_timezone)
        dt_local = dt.astimezone(user_tz)

        # Format date with i18n-aware names (using centralized i18n_dates module)
        # Get day and month names using helper functions
        day_of_week = dt_local.weekday()
        month = dt_local.month
        day = dt_local.strftime("%d")  # "03", "17", etc.
        year = dt_local.year

        day_name = get_day_name(day_of_week, locale)
        month_name = get_month_name(month, locale)

        # Extract language for special formatting (zh-CN needs different structure)
        language = (
            locale.lower()
            if locale and locale.lower() == "zh-cn"
            else (
                locale.split("-")[0].lower()
                if locale and "-" in locale
                else locale.lower() if locale else "fr"
            )
        )
        if language == "zh-cn":
            language = "zh-CN"

        # Format based on language
        if language == "zh-CN":
            # Chinese format: "2025年11月17日 星期日"
            date_str = f"{year}年{month}月{int(day)}日 {day_name}"
        else:
            # Western format: "lundi 03 novembre 2025"
            date_str = f"{day_name} {day} {month_name} {year}"

        if include_time:
            # Format time: "14:05" (HH:MM, no seconds)
            time_str = dt_local.strftime("%H:%M")
            # Connector word varies by language (from centralized TIME_CONNECTORS)
            time_connector = get_time_connector(locale)
            if language == "zh-CN":
                return f"{date_str} {time_str}"
            else:
                return f"{date_str} {time_connector} {time_str}"
        else:
            return date_str

    except (ValueError, OSError, KeyError) as e:
        logger.warning(
            "date_formatting_error",
            timestamp_ms=timestamp_ms,
            user_timezone=user_timezone,
            error=str(e),
        )
        lang = (
            locale.split("-")[0].lower()
            if locale and "-" in locale
            else (locale.lower() if locale else "fr")
        )
        if locale and locale.lower() == "zh-cn":
            lang = "zh-CN"
        return APIMessages.date_invalid(lang)


def format_google_time_only(
    timestamp_ms: int | str | None,
    user_timezone: str = "UTC",
) -> str:
    """
    Format timestamp as time only (HH:MM).

    Args:
        timestamp_ms: Timestamp in milliseconds or ISO string
        user_timezone: IANA timezone

    Returns:
        Formatted time string: "14:05"

    Examples:
        >>> format_google_time_only(1700000000000, "Europe/Paris")
        "01:13"
    """
    if not timestamp_ms:
        return "--:--"

    try:
        if isinstance(timestamp_ms, str):
            try:
                dt = datetime.fromisoformat(timestamp_ms.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                timestamp_ms = int(timestamp_ms)
                dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
        else:
            dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)

        import zoneinfo

        user_tz = zoneinfo.ZoneInfo(user_timezone)
        dt_local = dt.astimezone(user_tz)

        return dt_local.strftime("%H:%M")

    except (ValueError, OSError, KeyError) as e:
        logger.warning(
            "time_formatting_error",
            timestamp_ms=timestamp_ms,
            user_timezone=user_timezone,
            error=str(e),
        )
        return "--:--"


def format_google_birthday(
    year: int | str | None,
    month: int | str | None,
    day: int | str | None,
    locale: str = "fr-FR",
) -> str:
    """
    Format Google Contacts birthday for user display.

    Converts Google People API birthday object (year/month/day components) to
    localized date format WITHOUT time and WITHOUT day of week.

    Args:
        year: Birth year (optional, can be None if age is private)
        month: Birth month (1-12)
        day: Birth day (1-31)
        locale: Locale for formatting (e.g., "fr-FR", "en-US")

    Returns:
        Formatted string:
        - With year: "03 novembre 1975"
        - Without year: "03 novembre"

    Examples:
        >>> format_google_birthday(1975, 11, 3, "fr-FR")
        "03 novembre 1975"

        >>> format_google_birthday(None, 11, 3, "fr-FR")
        "03 novembre"

        >>> format_google_birthday(1975, 11, 3, "en-US")
        "November 3, 1975"

    Note:
        Google People API returns birthdays as separate year/month/day integers,
        NOT as timestamps. This avoids timezone-related ambiguity (birthdays are
        calendar dates, not moments in time).
    """

    # Helper to get language from locale
    def _get_lang() -> str:
        if locale and locale.lower() == "zh-cn":
            return "zh-CN"
        return (
            locale.split("-")[0].lower()
            if locale and "-" in locale
            else (locale.lower() if locale else "fr")
        )

    if not month or not day:
        return APIMessages.date_invalid(_get_lang())

    try:
        # Convert to integers if strings
        month_int = int(month) if month else None
        day_int = int(day) if day else None
        year_int = int(year) if year else None

        if not month_int or not day_int:
            return APIMessages.date_invalid(_get_lang())

        # Validate ranges
        if not (1 <= month_int <= 12):
            return APIMessages.date_invalid(_get_lang())
        if not (1 <= day_int <= 31):
            return APIMessages.date_invalid(_get_lang())

        # Get month name using centralized i18n_dates module
        month_name = get_month_name(month_int, locale)
        day_str = f"{day_int:02d}"  # Leading zero (03, 17, etc.)

        # Extract language for special formatting (zh-CN, en need different structure)
        language = (
            locale.lower()
            if locale and locale.lower() == "zh-cn"
            else (
                locale.split("-")[0].lower()
                if locale and "-" in locale
                else locale.lower() if locale else "fr"
            )
        )
        if language == "zh-cn":
            language = "zh-CN"

        # Format based on language
        if language == "zh-CN":
            # Chinese format: "1975年11月3日" or "11月3日"
            if year_int:
                return f"{year_int}年{month_int}月{day_int}日"
            else:
                return f"{month_int}月{day_int}日"
        elif language == "en":
            # English format: "November 3, 1975" or "November 3"
            if year_int:
                return f"{month_name} {day_int}, {year_int}"
            else:
                return f"{month_name} {day_int}"
        else:
            # Western format: "03 novembre 1975" or "03 novembre"
            if year_int:
                return f"{day_str} {month_name} {year_int}"
            else:
                return f"{day_str} {month_name}"

    except (ValueError, IndexError, TypeError) as e:
        logger.warning(
            "birthday_formatting_error",
            year=year,
            month=month,
            day=day,
            locale=locale,
            error=str(e),
        )
        return APIMessages.date_invalid(_get_lang())


# =============================================================================
# GMAIL FORMATTER
# =============================================================================


class GmailFormatter(BaseFormatter):
    """
    Formatter for Gmail email responses.

    Handles Gmail message object formatting with field extraction.
    Optimized for minimal token usage in search mode.
    """

    # Field extractors for Gmail messages
    # Reference: https://developers.google.com/gmail/api/reference/rest/v1/users.messages
    FIELD_EXTRACTORS: dict[str, Callable[[dict[str, Any], str, str], Any]] = {
        # Always included
        "id": lambda msg, tz, loc: msg.get("id", ""),
        "threadId": lambda msg, tz, loc: msg.get("threadId", ""),
        # Search mode fields (lightweight)
        "from": lambda msg, tz, loc: GmailFormatter._extract_from(msg, loc),
        "from_email": lambda msg, tz, loc: GmailFormatter._extract_from_email(msg),
        "to": lambda msg, tz, loc: GmailFormatter._extract_to(msg),
        "cc": lambda msg, tz, loc: GmailFormatter._extract_cc(msg),
        "subject": lambda msg, tz, loc: GmailFormatter._extract_subject(msg, loc),
        "date": lambda msg, tz, loc: GmailFormatter._extract_date(msg, tz, loc),
        "snippet": lambda msg, tz, loc: GmailFormatter._extract_snippet(msg),
        "is_unread": lambda msg, tz, loc: GmailFormatter._extract_is_unread(msg),
        "gmail_url": lambda msg, tz, loc: GmailFormatter._extract_email_web_url(msg),
        # Details mode fields (comprehensive)
        "body": lambda msg, tz, loc: GmailFormatter._extract_body_truncated(msg, loc),
        "labels": lambda msg, tz, loc: msg.get("labelIds", []),
        "headers": lambda msg, tz, loc: GmailFormatter._extract_all_headers(msg),
        "attachments": lambda msg, tz, loc: GmailFormatter._extract_attachments(msg, loc),
        "internalDate": lambda msg, tz, loc: msg.get("internalDate"),
    }

    # Operation-specific default fields (token optimization)
    OPERATION_DEFAULT_FIELDS = {
        # Search: Minimal fields for quick browsing (~150 tokens/email)
        "search": [
            "id",
            "from",
            "from_email",
            "to",
            "cc",
            "subject",
            "date",
            "snippet",
            "is_unread",
            "gmail_url",
        ],
        # Details: Full email content (~500-800 tokens/email)
        "details": [
            "id",
            "threadId",
            "from",
            "from_email",
            "to",
            "cc",
            "subject",
            "date",
            "snippet",
            "body",
            "is_unread",
            "labels",
            "headers",
            "attachments",
            "gmail_url",
        ],
    }

    DEFAULT_FIELDS = OPERATION_DEFAULT_FIELDS["search"]

    def __init__(
        self,
        tool_name: str,
        operation: str,
        user_timezone: str = "UTC",
        locale: str = "fr-FR",
    ) -> None:
        """
        Initialize Gmail formatter.

        Args:
            tool_name: Tool identifier (e.g., "search_emails_tool")
            operation: Operation name ("search", "details")
            user_timezone: User's IANA timezone (e.g., "Europe/Paris")
            locale: User's locale (e.g., "fr-FR", "en-US")
        """
        super().__init__(tool_name, operation)
        self.user_timezone = user_timezone
        self.locale = locale

    def format_item(
        self, raw_item: dict[str, Any], fields: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Format a single Gmail message object.

        Args:
            raw_item: Raw Gmail message object
            fields: List of fields to include (None = operation-specific defaults)

        Returns:
            Formatted email dict
        """
        # Determine fields to include
        if fields is None:
            fields_to_include = self.OPERATION_DEFAULT_FIELDS.get(
                self.operation, self.DEFAULT_FIELDS
            )
            self.logger.debug(
                "using_operation_default_fields",
                operation=self.operation,
                fields_count=len(fields_to_include),
            )
        else:
            # Always include id as identifier
            fields_to_include = ["id"]
            for field in fields:
                if field not in fields_to_include:
                    fields_to_include.append(field)

        # Extract fields using extractors
        email_info: dict[str, Any] = {}
        for field in fields_to_include:
            extractor = self.FIELD_EXTRACTORS.get(field)
            if extractor:
                email_info[field] = extractor(raw_item, self.user_timezone, self.locale)
            else:
                self.logger.warning(
                    "unknown_field_in_gmail_formatter",
                    field=field,
                    available_fields=list(self.FIELD_EXTRACTORS.keys()),
                )

        return email_info

    def _get_items_key(self) -> str:
        """Get the key for emails list in response."""
        return "emails"

    # =========================================================================
    # FIELD EXTRACTION HELPERS
    # =========================================================================

    @staticmethod
    def _extract_headers_dict(message: dict[str, Any]) -> dict[str, str]:
        """Extract headers as dict from message payload."""
        headers: dict[str, str] = {}
        payload = message.get("payload", {})
        for header in payload.get("headers", []):
            name = header.get("name", "").lower()
            value = header.get("value", "")
            if name and value:
                headers[name] = value
        return headers

    @staticmethod
    def _extract_from(message: dict[str, Any], locale: str = "fr-FR") -> str:
        """Extract sender full header (name + email)."""
        headers = GmailFormatter._extract_headers_dict(message)
        if from_header := headers.get("from"):
            return from_header
        lang = (
            locale.split("-")[0].lower()
            if locale and "-" in locale
            else (locale.lower() if locale else "fr")
        )
        if locale and locale.lower() == "zh-cn":
            lang = "zh-CN"
        return APIMessages.sender_unknown(lang)

    @staticmethod
    def _extract_from_email(message: dict[str, Any]) -> str:
        """Extract sender email address only (without name).

        Parses RFC 5322 format: "Name" <email@domain.com> -> email@domain.com
        """
        import re

        from_header = GmailFormatter._extract_from(message)

        # Try to extract email from angle brackets: "Name" <email>
        match = re.search(r"<([^>]+)>", from_header)
        if match:
            return match.group(1).strip()

        # If no brackets, check if it's already just an email
        if "@" in from_header and "<" not in from_header:
            return from_header.strip()

        # Fallback: return original
        return from_header

    @staticmethod
    def _extract_to(message: dict[str, Any]) -> list[str]:
        """Extract recipient email addresses."""
        headers = GmailFormatter._extract_headers_dict(message)
        to_header = headers.get("to", "")
        if not to_header:
            return []
        # Split by comma and strip whitespace
        return [addr.strip() for addr in to_header.split(",") if addr.strip()]

    @staticmethod
    def _extract_cc(message: dict[str, Any]) -> list[str]:
        """Extract CC email addresses."""
        headers = GmailFormatter._extract_headers_dict(message)
        cc_header = headers.get("cc", "")
        if not cc_header:
            return []
        return [addr.strip() for addr in cc_header.split(",") if addr.strip()]

    @staticmethod
    def _extract_subject(message: dict[str, Any], locale: str = "fr-FR") -> str:
        """Extract email subject."""
        headers = GmailFormatter._extract_headers_dict(message)
        if subject := headers.get("subject"):
            return subject
        lang = (
            locale.split("-")[0].lower()
            if locale and "-" in locale
            else (locale.lower() if locale else "fr")
        )
        if locale and locale.lower() == "zh-cn":
            lang = "zh-CN"
        return APIMessages.no_subject(lang)

    @staticmethod
    def _extract_date(message: dict[str, Any], user_timezone: str, locale: str) -> str:
        """Extract and format email date."""
        internal_date = message.get("internalDate")
        return format_google_datetime(internal_date, user_timezone, locale, include_time=True)

    @staticmethod
    def _extract_snippet(message: dict[str, Any]) -> str:
        """Extract email snippet (preview text).

        Gmail API returns snippets with HTML entities (&#39; for ', &amp; for &, etc.)
        We decode these for proper display.
        """
        snippet = message.get("snippet", "")
        # Decode HTML entities (&#39; -> ', &amp; -> &, etc.)
        if snippet:
            snippet = html.unescape(snippet)
        # Limit snippet to 200 chars max for token efficiency
        if len(snippet) > 200:
            return snippet[:197] + "..."
        return snippet

    @staticmethod
    def _extract_is_unread(message: dict[str, Any]) -> bool:
        """Check if email is unread."""
        labels = message.get("labelIds", [])
        return "UNREAD" in labels

    @staticmethod
    def _extract_email_web_url(message: dict[str, Any]) -> str:
        """Generate web URL for this email message.

        Returns a provider-specific URL:
        - Gmail: direct link to the message in Gmail web
        - Apple: empty string (iCloud Mail has no per-message URL)
        - Future providers: extend as needed

        Args:
            message: Normalized email message dict.

        Returns:
            Web URL string, or empty string if no web link available.
        """
        provider = message.get("_provider")
        message_id = message.get("id", "")
        if not message_id:
            return ""
        if provider == "apple":
            # Apple iCloud Mail has no web URL for individual messages
            return ""
        if provider == "microsoft":
            # Microsoft normalizer stores the web link from Graph API
            return message.get("webLink", "")
        # Default: Gmail
        return f"https://mail.google.com/mail/u/0/#all/{message_id}"

    @staticmethod
    def _extract_body(message: dict[str, Any]) -> str:
        """Extract email body content (provider-aware).

        - Apple: body is at top-level (plain text, returned as-is)
        - Microsoft: body is at top-level (HTML, converted to plain text)
        - Gmail: body is in payload.parts (base64url encoded, needs recursive extraction)
        """
        # Fast path: top-level body (Apple/Microsoft normalizer, or already enriched)
        top_level_body = message.get("body")
        if isinstance(top_level_body, str) and top_level_body:
            provider = message.get("_provider")
            if provider == "microsoft":
                # Microsoft Graph returns HTML body — convert to readable plain text
                from src.domains.connectors.clients.google_gmail_client import (
                    HTMLToTextConverter,
                )

                try:
                    from src.core.config import settings

                    converter = HTMLToTextConverter(
                        url_shorten_threshold=settings.emails_url_shorten_threshold
                    )
                    converter.feed(top_level_body)
                    return converter.get_text()
                except Exception:
                    # Fallback: basic HTML stripping
                    import re

                    text = re.sub(r"<[^>]+>", "", top_level_body)
                    return html.unescape(text).strip()
            return top_level_body

        # Gmail path: extract from payload parts
        payload = message.get("payload", {})
        if not payload:
            return ""

        # Import here to avoid circular dependency
        from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient

        return GoogleGmailClient._extract_body_recursive(payload)

    @staticmethod
    def _extract_body_truncated(message: dict[str, Any], locale: str = "fr-FR") -> str:
        """
        Extract email body with truncation for long emails.

        Truncates body at configured max length and adds a continuation link.
        Provider-aware: Gmail gets a clickable link, Apple gets plain truncation.

        Args:
            message: Normalized email message dict (Gmail or Apple format).
            locale: User's locale for i18n messages.

        Returns:
            Body text, truncated with continuation marker if too long.
        """
        from src.core.config import settings

        body = GmailFormatter._extract_body(message)
        if not body:
            return ""

        # Decode HTML entities (&#39; -> ', &amp; -> &, etc.)
        body = html.unescape(body)

        max_length = settings.emails_body_max_length

        # Check if truncation is needed
        if len(body) <= max_length:
            return body

        # Get language from locale
        lang = (
            locale.split("-")[0].lower()
            if locale and "-" in locale
            else (locale.lower() if locale else "fr")
        )
        if locale and locale.lower() == "zh-cn":
            lang = "zh-CN"

        # Truncate and add continuation link (provider-aware)
        email_url = GmailFormatter._extract_email_web_url(message)
        truncated_body = body[:max_length].rstrip()

        # Find last complete sentence or paragraph for cleaner cut
        # Look for sentence endings near the cut point
        for end_marker in ["\n\n", ". ", ".\n", "! ", "!\n", "? ", "?\n"]:
            last_end = truncated_body.rfind(end_marker)
            if last_end > max_length * 0.8:  # Keep at least 80% of allowed length
                truncated_body = truncated_body[: last_end + len(end_marker)]
                break

        # Add continuation link (with web URL for Gmail, plain truncation for Apple)
        truncated_body = truncated_body.rstrip()
        if email_url:
            truncated_body += "\n\n" + APIMessages.email_read_more(email_url, lang)
        else:
            truncated_body += "\n\n" + APIMessages.message_truncated(lang)

        return truncated_body

    @staticmethod
    def _extract_all_headers(message: dict[str, Any]) -> dict[str, str]:
        """Extract all headers as dict."""
        return GmailFormatter._extract_headers_dict(message)

    @staticmethod
    def _extract_attachments(
        message: dict[str, Any], locale: str = "fr-FR"
    ) -> list[dict[str, str]]:
        """
        Extract attachments from email message.

        Returns list of attachments with filename and Gmail URL.

        Args:
            message: Gmail message object
            locale: User's locale for i18n placeholders

        Returns:
            List of dicts with keys:
            - filename: Attachment filename
            - gmail_url: URL to view/download attachment in Gmail
            - mime_type: MIME type of attachment
            - size: Size in bytes (if available)

        Example:
            >>> attachments = _extract_attachments(message)
            >>> print(attachments)
            [
                {
                    "filename": "document.pdf",
                    "gmail_url": "https://mail.google.com/mail/u/0/#all/18f3c...",
                    "mime_type": "application/pdf",
                    "size": 245678
                }
            ]

        Note:
            Gmail API requires format=full to get attachment metadata.
            Attachment bodies are NOT extracted (use attachmentId if needed).
        """
        # Get language from locale
        lang = (
            locale.split("-")[0].lower()
            if locale and "-" in locale
            else (locale.lower() if locale else "fr")
        )
        if locale and locale.lower() == "zh-cn":
            lang = "zh-CN"

        attachments = []
        payload = message.get("payload", {})
        message_id = message.get("id", "")

        def _extract_from_parts(parts: list[dict[str, Any]]) -> None:
            """Recursively extract attachments from message parts."""
            for part in parts:
                # Check if this part is an attachment
                filename = part.get("filename", "")
                mime_type = part.get("mimeType", "")
                body = part.get("body", {})
                attachment_id = body.get("attachmentId")

                # Gmail marks attachments with either:
                # 1. Non-empty filename
                # 2. Content-Disposition: attachment header
                # Accept attachment if Gmail provides an attachmentId, even if filename is empty
                if attachment_id:
                    # Build Gmail URL (same as message URL, Gmail handles attachment display)
                    gmail_url = (
                        f"https://mail.google.com/mail/u/0/#all/{message_id}" if message_id else ""
                    )

                    if not filename:
                        filename = APIMessages.attachment_placeholder(lang)

                    attachments.append(
                        {
                            "filename": filename,
                            "gmail_url": gmail_url,
                            "mime_type": mime_type,
                            "size": body.get("size", 0),
                            "attachment_id": attachment_id,
                            "message_id": message_id,
                        }
                    )

                # Recurse into nested parts (multipart messages)
                if "parts" in part:
                    _extract_from_parts(part["parts"])

        # Start extraction from payload
        if "parts" in payload:
            _extract_from_parts(payload["parts"])

        return attachments

    def _format_metadata_timestamp(self, timestamp_iso: str) -> str | None:
        """
        Format metadata timestamp for user display.

        Uses user's timezone and locale for formatting.

        Args:
            timestamp_iso: ISO timestamp string

        Returns:
            Formatted timestamp (e.g., "lundi 17 novembre 2025 à 14:30")
        """
        return format_google_datetime(
            timestamp_ms=timestamp_iso,
            user_timezone=self.user_timezone,
            locale=self.locale,
            include_time=True,
        )


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "BaseFormatter",
    "ContactsFormatter",
    "GmailFormatter",
    "format_google_datetime",
    "format_google_time_only",
    "format_google_birthday",
]
