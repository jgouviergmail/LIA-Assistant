"""
Core semantic catalogue and its verified entity/value extensions.

Types are organised as schema.org-inspired metadata. Native manifests and
explicit MCP schemas describe actual producers and consumers; editorial
relations never authorize value conversion (ADR-090, ADR-233).

Hierarchy:
- Thing (root)
  - Person → Contact
  - Place → PostalAddress, GeoCoordinates
  - Event → CalendarEvent
  - Intangible → Identifier, QuantitativeValue, DateTime, etc.
  - CreativeWork → DigitalDocument, Message, etc.
"""

from src.domains.agents.semantic.entity_types import (
    CALENDAR_EVENT,
    CONTACT,
    EMAIL_MESSAGE,
    PLACE,
    SMS_MESSAGE,
)
from src.domains.agents.semantic.native_types import load_native_types
from src.domains.agents.semantic.resource_handle_types import load_resource_handle_types
from src.domains.agents.semantic.semantic_type import SemanticType, TypeCategory
from src.domains.agents.semantic.type_registry import TypeRegistry
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# ROOT TYPES (schema.org Thing hierarchy)
# =============================================================================

THING = SemanticType(
    name="Thing",
    category=TypeCategory.IDENTITY,
    description="The most generic type of item (schema.org Thing)",
    uri="http://schema.org/Thing",
    examples=[],
)

# =============================================================================
# PERSON HIERARCHY (Identity types)
# =============================================================================

PERSON = SemanticType(
    name="Person",
    parent="Thing",
    category=TypeCategory.IDENTITY,
    description="A person (alive, dead, undead, or fictional)",
    uri="http://schema.org/Person",
)


# =============================================================================
# CONTACT POINT (Identity subtypes)
# =============================================================================

CONTACT_POINT = SemanticType(
    name="ContactPoint",
    parent="Thing",
    category=TypeCategory.IDENTITY,
    description="A contact point (email, phone, etc.)",
    uri="http://schema.org/ContactPoint",
)

EMAIL_ADDRESS = SemanticType(
    name="email_address",
    parent="ContactPoint",
    category=TypeCategory.IDENTITY,
    description="Email address (RFC 5322 compliant)",
    format_pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
    examples=["john@example.com", "user+tag@domain.co.uk"],
    related_types=["contact_id", "person_name", "message_id"],
    source_domains=["contact", "email", "event"],
    used_in_tools=[
        "get_contacts_tool",
        "send_email_tool",
        "create_event_tool",
        "get_emails_tool",
    ],
)

PHONE_NUMBER = SemanticType(
    name="phone_number",
    parent="ContactPoint",
    category=TypeCategory.IDENTITY,
    description="Phone number (international or local format)",
    examples=["+33612345678", "06 12 34 56 78"],
    related_types=["contact_id", "person_name"],
    source_domains=["contact", "place"],
    used_in_tools=["get_contacts_tool", "get_places_tool"],
)

PERSON_NAME = SemanticType(
    name="person_name",
    parent="Text",
    category=TypeCategory.IDENTITY,
    description="Person's name (first, last, or full name)",
    examples=["Jean Dupont", "Marie", "Dupont"],
    related_types=["contact_id", "email_address", "phone_number"],
    source_domains=["contact"],
    used_in_tools=["get_contacts_tool", "create_contact_tool"],
)

# =============================================================================
# PLACE HIERARCHY (Location types)
# =============================================================================


POSTAL_ADDRESS = SemanticType(
    name="PostalAddress",
    parent="Place",
    category=TypeCategory.LOCATION,
    description="The mailing address",
    uri="http://schema.org/PostalAddress",
    properties={
        "streetAddress": "str",
        "addressLocality": "locality",
        "addressCountry": "country_code",
        "postalCode": "postal_code",
    },
    related_types=["coordinate", "place_id"],
    narrower_types=["physical_address"],
)

PHYSICAL_ADDRESS = SemanticType(
    name="physical_address",
    parent="PostalAddress",
    category=TypeCategory.LOCATION,
    description="Physical postal address or location description",
    examples=["10 Rue de la Paix, Paris", "Eiffel Tower", "home"],
    related_types=["coordinate", "place_id", "formatted_address"],
    broader_types=["PostalAddress"],
    source_domains=["contact", "place", "event", "route"],
    used_in_tools=[
        "get_route_tool",
        "get_places_tool",
        "get_contacts_tool",
        "create_event_tool",
        "get_weather_forecast_tool",  # Weather needs location from events
    ],
)

FORMATTED_ADDRESS = SemanticType(
    name="formatted_address",
    parent="PostalAddress",
    category=TypeCategory.LOCATION,
    description="Fully formatted address string",
    examples=["10 Rue de la Paix, 75002 Paris, France"],
    related_types=["physical_address"],
    source_domains=[],
)

GEO_COORDINATES = SemanticType(
    name="GeoCoordinates",
    parent="Place",
    category=TypeCategory.LOCATION,
    description="Geographic coordinates (latitude/longitude pair)",
    uri="http://schema.org/GeoCoordinates",
    properties={"latitude": "latitude", "longitude": "longitude"},
)

COORDINATE = SemanticType(
    name="coordinate",
    parent="GeoCoordinates",
    category=TypeCategory.LOCATION,
    description="Geographic coordinates (latitude/longitude)",
    examples=["48.8566, 2.3522", "(48.8566, 2.3522)"],
    properties={"latitude": "latitude", "longitude": "longitude"},
    related_types=["physical_address", "place_id", "PostalAddress"],
    source_domains=["place", "route"],
    used_in_tools=["get_places_tool", "get_route_tool"],
)

# Location components
COUNTRY_CODE = SemanticType(
    name="country_code",
    parent="Text",
    category=TypeCategory.LOCATION,
    description="ISO 3166-1 alpha-2 country code",
    examples=["FR", "US", "DE"],
    source_domains=["contact"],
)

POSTAL_CODE = SemanticType(
    name="postal_code",
    parent="Text",
    category=TypeCategory.LOCATION,
    description="Postal code or ZIP code",
    examples=["75002", "10001", "SW1A 1AA"],
    source_domains=["place", "contact"],
)

LOCALITY = SemanticType(
    name="locality",
    parent="Text",
    category=TypeCategory.LOCATION,
    description="City, town, or locality name",
    examples=["Paris", "New York", "London"],
    source_domains=["place", "contact"],
)


RADIUS_METERS = SemanticType(
    name="radius_meters",
    parent="QuantitativeValue",
    category=TypeCategory.MEASUREMENT,
    description="Search radius in meters",
    source_domains=[],
)

# =============================================================================
# EVENT HIERARCHY
# =============================================================================

EVENT = SemanticType(
    name="Event",
    parent="Thing",
    category=TypeCategory.TEMPORAL,
    description="An event happening at a certain time and location",
    uri="http://schema.org/Event",
)


# =============================================================================
# INTANGIBLE TYPES (Identifiers, Measurements, etc.)
# =============================================================================

INTANGIBLE = SemanticType(
    name="Intangible",
    parent="Thing",
    category=TypeCategory.RESOURCE_ID,
    description="A utility class that serves as the umbrella for a number of 'intangible' things",
    uri="http://schema.org/Intangible",
)

# =============================================================================
# IDENTIFIER HIERARCHY (Resource IDs)
# =============================================================================

IDENTIFIER = SemanticType(
    name="Identifier",
    parent="Intangible",
    category=TypeCategory.RESOURCE_ID,
    description="Generic identifier for resources",
    uri="http://schema.org/PropertyValue",
)

EVENT_ID = SemanticType(
    name="event_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Unique identifier for calendar event",
    source_domains=["event"],
    used_in_tools=["get_events_tool", "update_event_tool", "delete_event_tool"],
)

CALENDAR_ID = SemanticType(
    name="calendar_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Unique identifier for calendar",
    source_domains=["event"],
    used_in_tools=["list_calendars_tool", "get_events_tool"],
)

CONTACT_ID = SemanticType(
    name="contact_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Unique identifier for contact",
    related_types=["person_name", "email_address", "phone_number"],
    source_domains=["contact"],
    used_in_tools=["get_contacts_tool", "update_contact_tool"],
)

FILE_ID = SemanticType(
    name="file_id",
    related_types=["attachment_info"],
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Unique identifier for file (Google Drive)",
    source_domains=["file"],
    used_in_tools=["get_files_tool"],
)

FOLDER_ID = SemanticType(
    name="folder_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Unique identifier for folder (Google Drive)",
    source_domains=[],
)

MESSAGE_ID = SemanticType(
    name="message_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Unique identifier for email message",
    related_types=["thread_id", "email_address", "attachment_info"],
    source_domains=["email"],
    used_in_tools=["get_emails_tool", "reply_email_tool"],
)

THREAD_ID = SemanticType(
    name="thread_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Unique identifier for email thread",
    related_types=["message_id"],
    source_domains=["email"],
)

TASK_ID = SemanticType(
    name="task_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Unique identifier for task",
    source_domains=["task"],
    used_in_tools=["get_tasks_tool", "update_task_tool"],
)

TASK_LIST_ID = SemanticType(
    name="task_list_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Unique identifier for task list",
    source_domains=["task"],
)

PLACE_ID = SemanticType(
    name="place_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Unique identifier for place (Google Places)",
    related_types=["physical_address", "coordinate", "PostalAddress"],
    source_domains=["place"],
    used_in_tools=["get_places_tool"],
)

REMINDER_ID = SemanticType(
    name="reminder_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Unique identifier for reminder",
    source_domains=["reminder"],
)

WIKIPEDIA_PAGE_ID = SemanticType(
    name="wikipedia_page_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Unique identifier for Wikipedia page",
    source_domains=["wikipedia"],
)

# =============================================================================
# TYPE IDENTIFIERS (Enumerations for types)
# =============================================================================

FILE_MIME_TYPE = SemanticType(
    name="file_mime_type",
    parent="Text",
    category=TypeCategory.CATEGORY,
    description="MIME type of file",
    examples=["application/pdf", "image/jpeg", "text/plain"],
    source_domains=["file"],
)

EMAIL_LABEL = SemanticType(
    name="email_label",
    parent="Text",
    category=TypeCategory.CATEGORY,
    description="A user mail label name (system labels such as INBOX cannot be created, renamed or deleted)",
    examples=["Work", "Invoices", "Travel/2026"],
    source_domains=["email"],
)

PLACE_TYPE = SemanticType(
    name="place_type",
    parent="Text",
    category=TypeCategory.CATEGORY,
    description="Type of place (restaurant, hotel, etc.)",
    examples=["restaurant", "hotel", "cafe", "store"],
    source_domains=["place"],
)

# =============================================================================
# TEMPORAL TYPES (DateTime hierarchy)
# =============================================================================

DATE_TIME = SemanticType(
    name="DateTime",
    parent="Intangible",
    category=TypeCategory.TEMPORAL,
    description="A combination of date and time",
    uri="http://schema.org/DateTime",
)

DATETIME = SemanticType(
    name="datetime",
    parent="DateTime",
    category=TypeCategory.TEMPORAL,
    description="ISO 8601 datetime string",
    examples=["2024-01-15T14:30:00Z", "2024-01-15T14:30:00+01:00"],
    validation_rules=["Must be valid ISO 8601 datetime"],
    source_domains=["event", "task"],
)

TIMEZONE = SemanticType(
    name="timezone",
    parent="Text",
    category=TypeCategory.TEMPORAL,
    description="IANA timezone identifier",
    examples=["Europe/Paris", "America/New_York", "UTC"],
    validation_rules=["Must be valid IANA timezone"],
    source_domains=[],
)


MODIFICATION_TIMESTAMP = SemanticType(
    name="modification_timestamp",
    parent="DateTime",
    category=TypeCategory.TEMPORAL,
    description="Last modification timestamp",
    source_domains=["file"],
)

BIRTHDAY = SemanticType(
    name="birthday",
    parent="Date",
    category=TypeCategory.TEMPORAL,
    description="Person's birthday date",
    source_domains=[],
)

RECENCY_FILTER = SemanticType(
    name="recency_filter",
    parent="Text",
    category=TypeCategory.TEMPORAL,
    description="Freshness window of a web search, in the vocabulary of each search tool",
    examples=["day", "week", "month", "year", "pd", "pw", "pm", "py"],
    source_domains=[],
)

FORMATTED_TIME = SemanticType(
    name="formatted_time",
    parent="Text",
    category=TypeCategory.TEMPORAL,
    description="Human-readable formatted time string",
    examples=["14:30", "2:30 PM", "14h30"],
    source_domains=[],
)

TRIGGER_DATETIME = SemanticType(
    name="trigger_datetime",
    parent="DateTime",
    category=TypeCategory.TEMPORAL,
    description="Datetime when reminder triggers",
    source_domains=["reminder"],
)

EVENT_START_DATETIME = SemanticType(
    name="event_start_datetime",
    parent="DateTime",
    category=TypeCategory.TEMPORAL,
    description=(
        "Calendar event start time - represents when the user needs to ARRIVE at the destination. "
        "For route planning, use as arrival_time. For weather forecasts, use as date parameter."
    ),
    examples=["2024-01-15T14:30:00+01:00", "2024-01-20T09:00:00Z"],
    source_domains=["event"],
    used_in_tools=["get_route_tool", "get_weather_forecast_tool"],
)

# =============================================================================
# QUANTITATIVE VALUE HIERARCHY (Measurements)
# =============================================================================

QUANTITATIVE_VALUE = SemanticType(
    name="QuantitativeValue",
    parent="Intangible",
    category=TypeCategory.MEASUREMENT,
    description="A point value or interval for quantifiable characteristics",
    uri="http://schema.org/QuantitativeValue",
)

DISTANCE = SemanticType(
    name="distance",
    parent="QuantitativeValue",
    category=TypeCategory.MEASUREMENT,
    description="Distance in meters or kilometers",
    examples=["1500m", "2.5km"],
    source_domains=["route", "place"],
    used_in_tools=["get_route_tool"],
)

TEMPERATURE = SemanticType(
    name="temperature",
    parent="QuantitativeValue",
    category=TypeCategory.MEASUREMENT,
    description="Temperature value (Celsius or Fahrenheit)",
    examples=["20°C", "68°F"],
    source_domains=["weather"],
)

HUMIDITY = SemanticType(
    name="humidity",
    parent="QuantitativeValue",
    category=TypeCategory.MEASUREMENT,
    description="Humidity percentage",
    examples=["65%", "80%"],
    source_domains=["weather"],
)

WIND_SPEED = SemanticType(
    name="wind_speed",
    parent="QuantitativeValue",
    category=TypeCategory.MEASUREMENT,
    description="Wind speed (km/h or mph)",
    examples=["15 km/h", "9 mph"],
    source_domains=["weather"],
)


RATING = SemanticType(
    name="rating",
    parent="QuantitativeValue",
    category=TypeCategory.MEASUREMENT,
    description="User rating (typically 1-5 scale)",
    examples=["4.5", "3.8"],
    source_domains=["place"],
)

FILE_SIZE = SemanticType(
    name="file_size",
    parent="QuantitativeValue",
    category=TypeCategory.MEASUREMENT,
    description="File size in bytes",
    examples=["1024", "2048000"],
    source_domains=["file"],
)

CONFIDENCE_SCORE = SemanticType(
    name="confidence_score",
    parent="QuantitativeValue",
    category=TypeCategory.MEASUREMENT,
    description="Confidence score (0.0-1.0)",
    examples=["0.85", "0.92"],
    source_domains=["agents"],
)

PRICE_LEVEL = SemanticType(
    name="price_level",
    parent="Text",
    category=TypeCategory.CONTENT,
    description="Localized place price-level label, not a numeric amount or API filter code",
    source_domains=["place"],
)

# =============================================================================
# STATUS AND FILTER TYPES (Enumerations)
# =============================================================================

ENUMERATION = SemanticType(
    name="Enumeration",
    parent="Intangible",
    category=TypeCategory.STATUS,
    description="Lists or enumerations",
    uri="http://schema.org/Enumeration",
)

TRAFFIC_CONDITION = SemanticType(
    name="traffic_condition",
    parent="Enumeration",
    category=TypeCategory.STATUS,
    description="Traffic level on a route, from its traffic-aware duration",
    examples=["NORMAL", "LIGHT", "MODERATE", "HEAVY"],
    source_domains=["route"],
)

TASK_STATUS = SemanticType(
    name="task_status",
    parent="Enumeration",
    category=TypeCategory.STATUS,
    description="Task completion status",
    examples=["needsAction", "completed"],
    source_domains=["task"],
)

ACCESS_ROLE = SemanticType(
    name="access_role",
    parent="Enumeration",
    category=TypeCategory.STATUS,
    description="The account's access role on a calendar",
    examples=["owner", "writer", "reader", "freeBusyReader"],
    source_domains=["event"],
)

SHARED_STATUS = SemanticType(
    name="shared_status",
    parent="Enumeration",
    category=TypeCategory.STATUS,
    description="Whether resource is shared",
    examples=["true", "false"],
    source_domains=["file"],
)


BUSINESS_STATUS = SemanticType(
    name="business_status",
    parent="Enumeration",
    category=TypeCategory.STATUS,
    description="A place's closure status, reported only when it is not operational",
    examples=["CLOSED_TEMPORARILY", "CLOSED_PERMANENTLY"],
    source_domains=["place"],
)


SEND_UPDATES_OPTION = SemanticType(
    name="send_updates_option",
    parent="Enumeration",
    category=TypeCategory.STATUS,
    description="Whether to send calendar update notifications",
    examples=["all", "externalOnly", "none"],
    source_domains=[],
)

OPEN_NOW_FILTER = SemanticType(
    name="open_now_filter",
    parent="Enumeration",
    category=TypeCategory.STATUS,
    description="Filter for place currently open",
    examples=["true", "false"],
    source_domains=[],
)

# =============================================================================
# CREATIVE WORK HIERARCHY (Content types)
# =============================================================================

CREATIVE_WORK = SemanticType(
    name="CreativeWork",
    parent="Thing",
    category=TypeCategory.CONTENT,
    description="The most generic kind of creative work",
    uri="http://schema.org/CreativeWork",
)


TEXT = SemanticType(
    name="Text",
    parent="CreativeWork",
    category=TypeCategory.CONTENT,
    description="Plain text content",
    uri="http://schema.org/Text",
)


EMAIL_BODY = SemanticType(
    name="email_body",
    parent="Text",
    category=TypeCategory.CONTENT,
    description="Email message body content",
    source_domains=["email"],
)

MESSAGE_SNIPPET = SemanticType(
    name="message_snippet",
    parent="Text",
    category=TypeCategory.CONTENT,
    description="Short preview snippet of message",
    source_domains=["email"],
)

FILE_CONTENT = SemanticType(
    name="file_content",
    parent="Text",
    category=TypeCategory.CONTENT,
    description="File content as text",
    source_domains=["file"],
)

BIOGRAPHY = SemanticType(
    name="biography",
    parent="Text",
    category=TypeCategory.CONTENT,
    description="Person's biography or description",
    source_domains=["contact"],
)

REVIEW = SemanticType(
    name="review",
    parent="CreativeWork",
    category=TypeCategory.CONTENT,
    description="User review or comment",
    uri="http://schema.org/Review",
    source_domains=["place"],
)

CITATION_URL = SemanticType(
    name="citation_url",
    parent="URL",
    category=TypeCategory.CONTENT,
    description="URL to source citation",
    source_domains=["perplexity"],
)


ATTACHMENT_INFO = SemanticType(
    name="attachment_info",
    parent="Text",
    category=TypeCategory.CONTENT,
    description="Email attachment metadata",
    related_types=["message_id", "file_id"],
    source_domains=["email"],
)

CONFERENCE_LINK = SemanticType(
    name="conference_link",
    parent="URL",
    category=TypeCategory.CONTENT,
    description="Video conference link (Meet, Zoom, etc.)",
    source_domains=[],
)

WEBSITE_URL = SemanticType(
    name="website_url",
    parent="URL",
    category=TypeCategory.CONTENT,
    description="Website URL",
    source_domains=["place"],
)

GOOGLE_MAPS_URL = SemanticType(
    name="google_maps_url",
    parent="URL",
    category=TypeCategory.CONTENT,
    description="Google Maps URL for location",
    source_domains=["place", "route"],
)

URL = SemanticType(
    name="URL",
    parent="Text",
    category=TypeCategory.CONTENT,
    description="Uniform Resource Locator",
    uri="http://schema.org/URL",
)

# =============================================================================
# CATEGORY AND ENUMERATION TYPES (Classifications)
# =============================================================================

TRAVEL_MODE = SemanticType(
    name="travel_mode",
    parent="Enumeration",
    category=TypeCategory.CATEGORY,
    description="Mode of transportation",
    examples=["DRIVE", "WALK", "BICYCLE", "TRANSIT", "TWO_WHEELER"],
    source_domains=["route"],
    used_in_tools=["get_route_tool", "get_route_matrix_tool"],
)

LANGUAGE_CODE = SemanticType(
    name="language_code",
    parent="Text",
    category=TypeCategory.CATEGORY,
    description="ISO 639-1 language code",
    examples=["fr", "en", "es", "de"],
    source_domains=["agents"],
)

UNIT_SYSTEM = SemanticType(
    name="unit_system",
    parent="Enumeration",
    category=TypeCategory.CATEGORY,
    description="System of units (metric/imperial)",
    examples=["metric", "imperial"],
    source_domains=[],
)


SEARCH_MODE = SemanticType(
    name="search_mode",
    parent="Enumeration",
    category=TypeCategory.CATEGORY,
    description="Whether a file search matches names only or names and content",
    examples=["name_only", "full_text"],
    source_domains=[],
)

CONTENT_TYPE_FILTER = SemanticType(
    name="content_type_filter",
    parent="Enumeration",
    category=TypeCategory.CATEGORY,
    description="Whether a file search returns files, folders or both",
    examples=["files_only", "folders_only", "all"],
    source_domains=[],
)

REPLY_ALL_FLAG = SemanticType(
    name="reply_all_flag",
    parent="Enumeration",
    category=TypeCategory.CATEGORY,
    description="Whether to reply to all recipients",
    examples=["true", "false"],
    source_domains=[],
)

ONLY_COMPLETED_FILTER = SemanticType(
    name="only_completed_filter",
    parent="Enumeration",
    category=TypeCategory.CATEGORY,
    description="Filter for completed task only",
    examples=["true", "false"],
    source_domains=[],
)

SHOW_COMPLETED_FILTER = SemanticType(
    name="show_completed_filter",
    parent="Enumeration",
    category=TypeCategory.CATEGORY,
    description="Whether to show completed items",
    examples=["true", "false"],
    source_domains=[],
)

# =============================================================================
# GEOGRAPHIC DATA TYPES (Routes specific)
# =============================================================================


NAVIGATION_STEPS = SemanticType(
    name="navigation_steps",
    parent="Text",
    category=TypeCategory.CONTENT,
    description="Turn-by-turn navigation instructions",
    source_domains=["route"],
)

ROUTE_MATRIX = SemanticType(
    name="route_matrix",
    parent="Text",
    category=TypeCategory.CONTENT,
    description="Matrix of route between multiple points",
    source_domains=["route"],
)

OPTIMAL_ORDER = SemanticType(
    name="optimal_order",
    parent="Text",
    category=TypeCategory.CONTENT,
    description="Optimal waypoint ordering for route",
    source_domains=["route"],
)

ROUTE_CONDITION = SemanticType(
    name="route_condition",
    parent="Enumeration",
    category=TypeCategory.STATUS,
    description="Whether a route exists between a matrix origin and destination",
    examples=["ROUTE_EXISTS", "ROUTE_NOT_FOUND"],
    source_domains=["route"],
)


# =============================================================================
# TYPE LOADING FUNCTION
# =============================================================================


def load_core_types(registry: TypeRegistry) -> None:
    """
    Load all core types into the registry.

    This function must be called at application startup
    to populate the global registry, including its entity and native extensions.

    Args:
        registry: TypeRegistry instance to populate

    Example:
        >>> registry = get_registry()
        >>> load_core_types(registry)
        >>> registry.get("email_address") is not None
        True
    """
    # Root types
    registry.register(THING)

    # Person hierarchy
    registry.register(PERSON)
    registry.register(CONTACT)

    # Contact points
    registry.register(CONTACT_POINT)
    registry.register(EMAIL_ADDRESS)
    registry.register(PHONE_NUMBER)
    registry.register(PERSON_NAME)

    # Place hierarchy
    registry.register(PLACE)
    registry.register(POSTAL_ADDRESS)
    registry.register(PHYSICAL_ADDRESS)
    registry.register(FORMATTED_ADDRESS)
    registry.register(GEO_COORDINATES)
    registry.register(COORDINATE)

    # Location components
    registry.register(COUNTRY_CODE)
    registry.register(POSTAL_CODE)
    registry.register(LOCALITY)
    registry.register(RADIUS_METERS)

    # Event hierarchy
    registry.register(EVENT)
    registry.register(CALENDAR_EVENT)

    # Intangibles
    registry.register(INTANGIBLE)

    # Identifiers
    registry.register(IDENTIFIER)
    registry.register(EVENT_ID)
    registry.register(CALENDAR_ID)
    registry.register(CONTACT_ID)
    registry.register(FILE_ID)
    registry.register(FOLDER_ID)
    registry.register(MESSAGE_ID)
    registry.register(THREAD_ID)
    registry.register(TASK_ID)
    registry.register(TASK_LIST_ID)
    registry.register(PLACE_ID)
    registry.register(REMINDER_ID)
    registry.register(WIKIPEDIA_PAGE_ID)
    registry.register(FILE_MIME_TYPE)
    registry.register(EMAIL_LABEL)
    registry.register(PLACE_TYPE)

    # Temporal types
    load_native_types(registry)
    registry.register(DATE_TIME)
    registry.register(DATETIME)
    registry.register(TIMEZONE)
    registry.register(MODIFICATION_TIMESTAMP)
    registry.register(BIRTHDAY)
    registry.register(RECENCY_FILTER)
    registry.register(FORMATTED_TIME)
    registry.register(TRIGGER_DATETIME)
    registry.register(EVENT_START_DATETIME)

    # Measurements
    registry.register(QUANTITATIVE_VALUE)
    registry.register(DISTANCE)
    registry.register(TEMPERATURE)
    registry.register(HUMIDITY)
    registry.register(WIND_SPEED)
    registry.register(RATING)
    registry.register(FILE_SIZE)
    registry.register(CONFIDENCE_SCORE)
    registry.register(PRICE_LEVEL)

    # Status and filters
    registry.register(ENUMERATION)
    registry.register(TRAFFIC_CONDITION)
    registry.register(TASK_STATUS)
    registry.register(ACCESS_ROLE)
    registry.register(SHARED_STATUS)
    registry.register(BUSINESS_STATUS)
    registry.register(SEND_UPDATES_OPTION)
    registry.register(OPEN_NOW_FILTER)

    # Creative works and content
    registry.register(CREATIVE_WORK)
    registry.register(EMAIL_MESSAGE)
    registry.register(SMS_MESSAGE)
    registry.register(TEXT)
    registry.register(URL)
    registry.register(EMAIL_BODY)
    registry.register(MESSAGE_SNIPPET)
    registry.register(FILE_CONTENT)
    registry.register(BIOGRAPHY)
    registry.register(REVIEW)
    registry.register(CITATION_URL)
    registry.register(ATTACHMENT_INFO)
    registry.register(CONFERENCE_LINK)
    registry.register(WEBSITE_URL)
    registry.register(GOOGLE_MAPS_URL)

    # Categories
    registry.register(TRAVEL_MODE)
    registry.register(LANGUAGE_CODE)
    registry.register(UNIT_SYSTEM)
    registry.register(SEARCH_MODE)
    registry.register(CONTENT_TYPE_FILTER)
    registry.register(REPLY_ALL_FLAG)
    registry.register(ONLY_COMPLETED_FILTER)
    registry.register(SHOW_COMPLETED_FILTER)

    # Geographic data
    registry.register(NAVIGATION_STEPS)
    registry.register(ROUTE_MATRIX)
    registry.register(OPTIMAL_ORDER)
    registry.register(ROUTE_CONDITION)

    # Resource handles (extracted module — see resource_handle_types.py)
    load_resource_handle_types(registry)

    # Log statistics
    stats = registry.get_stats()
    logger.info(
        "core_types_loaded",
        total_types=stats["total_types"],
        by_category=stats["by_category"],
        total_domains=stats["total_domains"],
        message=f"Loaded {stats['total_types']} core semantic types",
    )
