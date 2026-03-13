"""
Core Semantic Types - Catalogue Complet des 96+ Types

Définit tous les types sémantiques identifiés dans le codebase LIA,
organisés hiérarchiquement et inspirés de schema.org.

Types découverts:
- 5 types explicites existants
- 91+ types implicites identifiés dans les manifests, tools, et schemas

Organisation hiérarchique:
- Thing (racine)
  - Person → Contact
  - Place → PostalAddress, GeoCoordinates
  - Event → CalendarEvent
  - Intangible → Identifier, QuantitativeValue, DateTime, etc.
  - CreativeWork → DigitalDocument, Message, etc.
  - Action → SearchAction, NavigateAction, etc.
"""

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
    labels={"en": "Thing", "fr": "Chose"},
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
    labels={"en": "Person", "fr": "Personne"},
)

CONTACT = SemanticType(
    name="Contact",
    parent="Person",
    category=TypeCategory.IDENTITY,
    description="A person in address book with contact information",
    labels={"en": "Contact", "fr": "Contact"},
    properties={
        "name": "person_name",
        "email": "email_address",
        "phone": "phone_number",
        "address": "physical_address",
    },
    source_domains=["contact"],
    used_in_tools=["get_contact_tool", "create_contact_tool", "update_contact_tool"],
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
    labels={"en": "Contact Point", "fr": "Point de contact"},
)

EMAIL_ADDRESS = SemanticType(
    name="email_address",
    parent="ContactPoint",
    category=TypeCategory.IDENTITY,
    description="Email address (RFC 5322 compliant)",
    labels={"en": "Email address", "fr": "Adresse email"},
    format_pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
    examples=["john@example.com", "user+tag@domain.co.uk"],
    related_types=["contact_id", "person_name", "message_id"],
    source_domains=["contact", "email", "event"],
    used_in_tools=[
        "get_contact_tool",
        "send_email_tool",
        "create_event_tool",
        "search_email_tool",
    ],
)

PHONE_NUMBER = SemanticType(
    name="phone_number",
    parent="ContactPoint",
    category=TypeCategory.IDENTITY,
    description="Phone number (international or local format)",
    labels={"en": "Phone number", "fr": "Numéro de téléphone"},
    examples=["+33612345678", "06 12 34 56 78"],
    related_types=["contact_id", "person_name"],
    source_domains=["contact", "place"],
    used_in_tools=["get_contact_tool", "search_place_tool"],
)

PERSON_NAME = SemanticType(
    name="person_name",
    parent="Text",
    category=TypeCategory.IDENTITY,
    description="Person's name (first, last, or full name)",
    labels={"en": "Person name", "fr": "Nom de personne"},
    examples=["Jean Dupont", "Marie", "Dupont"],
    related_types=["contact_id", "email_address", "phone_number"],
    source_domains=["contact"],
    used_in_tools=["get_contact_tool", "create_contact_tool"],
)

# =============================================================================
# PLACE HIERARCHY (Location types)
# =============================================================================

PLACE = SemanticType(
    name="Place",
    parent="Thing",
    category=TypeCategory.LOCATION,
    description="Entities that have a somewhat fixed, physical extension",
    uri="http://schema.org/Place",
    labels={"en": "Place", "fr": "Lieu"},
)

POSTAL_ADDRESS = SemanticType(
    name="PostalAddress",
    parent="Place",
    category=TypeCategory.LOCATION,
    description="The mailing address",
    uri="http://schema.org/PostalAddress",
    labels={"en": "Postal address", "fr": "Adresse postale"},
    properties={
        "streetAddress": "str",
        "addressLocality": "locality",
        "addressCountry": "country_code",
        "postalCode": "postal_code",
    },
    related_types=["coordinate", "place_id"],
)

PHYSICAL_ADDRESS = SemanticType(
    name="physical_address",
    parent="PostalAddress",
    category=TypeCategory.LOCATION,
    description="Physical postal address or location description",
    labels={"en": "Physical address", "fr": "Adresse physique"},
    examples=["10 Rue de la Paix, Paris", "Eiffel Tower", "home"],
    related_types=["coordinate", "place_id", "formatted_address"],
    broader_types=["PostalAddress", "Place"],
    source_domains=["contact", "place", "event", "route"],
    used_in_tools=[
        "get_route_tool",
        "search_place_tool",
        "get_contact_tool",
        "create_event_tool",
        "get_weather_forecast_tool",  # Weather needs location from events
    ],
)

FORMATTED_ADDRESS = SemanticType(
    name="formatted_address",
    parent="PostalAddress",
    category=TypeCategory.LOCATION,
    description="Fully formatted address string",
    labels={"en": "Formatted address", "fr": "Adresse formatée"},
    examples=["10 Rue de la Paix, 75002 Paris, France"],
    source_domains=["place", "route"],
)

GEO_COORDINATES = SemanticType(
    name="GeoCoordinates",
    parent="Place",
    category=TypeCategory.LOCATION,
    description="Geographic coordinates (latitude/longitude pair)",
    uri="http://schema.org/GeoCoordinates",
    labels={"en": "Geo Coordinates", "fr": "Coordonnées géographiques"},
    properties={"latitude": "float", "longitude": "float"},
)

COORDINATE = SemanticType(
    name="coordinate",
    parent="GeoCoordinates",
    category=TypeCategory.LOCATION,
    description="Geographic coordinates (latitude/longitude)",
    labels={"en": "GPS coordinates", "fr": "Coordonnées GPS"},
    examples=["48.8566, 2.3522", "(48.8566, 2.3522)"],
    properties={"latitude": "float", "longitude": "float"},
    related_types=["physical_address", "place_id"],
    source_domains=["place", "route"],
    used_in_tools=["search_place_tool", "get_route_tool"],
)

# Location components
COUNTRY_CODE = SemanticType(
    name="country_code",
    parent="Text",
    category=TypeCategory.LOCATION,
    description="ISO 3166-1 alpha-2 country code",
    examples=["FR", "US", "DE"],
    source_domains=["place", "contact"],
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

AREA_NAME = SemanticType(
    name="area_name",
    parent="Text",
    category=TypeCategory.LOCATION,
    description="Area or region name",
    source_domains=["place"],
)

WAYPOINT = SemanticType(
    name="waypoint",
    parent="GeoCoordinates",
    category=TypeCategory.LOCATION,
    description="Intermediate point on a route",
    source_domains=["route"],
)

RADIUS_METERS = SemanticType(
    name="radius_meters",
    parent="QuantitativeValue",
    category=TypeCategory.MEASUREMENT,
    description="Search radius in meters",
    source_domains=["place"],
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
    labels={"en": "Event", "fr": "Événement"},
)

CALENDAR_EVENT = SemanticType(
    name="CalendarEvent",
    parent="Event",
    category=TypeCategory.TEMPORAL,
    description="Event in a calendar (meeting, appointment, etc.)",
    source_domains=["event"],
    used_in_tools=["create_event_tool", "update_event_tool", "search_event_tool"],
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
    used_in_tools=["get_event_details_tool", "update_event_tool", "delete_event_tool"],
)

CALENDAR_ID = SemanticType(
    name="calendar_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Unique identifier for calendar",
    source_domains=["event"],
    used_in_tools=["list_calendars_tool", "search_event_tool"],
)

CONTACT_ID = SemanticType(
    name="contact_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Unique identifier for contact",
    related_types=["person_name", "email_address", "phone_number"],
    source_domains=["contact"],
    used_in_tools=["get_contact_details_tool", "update_contact_tool"],
)

FILE_ID = SemanticType(
    name="file_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Unique identifier for file (Google Drive)",
    source_domains=["file"],
    used_in_tools=["get_file_details_tool", "download_file_tool"],
)

FOLDER_ID = SemanticType(
    name="folder_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Unique identifier for folder (Google Drive)",
    source_domains=["file"],
)

MESSAGE_ID = SemanticType(
    name="message_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Unique identifier for email message",
    related_types=["thread_id", "email_address"],
    source_domains=["email"],
    used_in_tools=["get_email_details_tool", "send_reply_tool"],
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
    used_in_tools=["get_task_details_tool", "update_task_tool"],
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
    related_types=["physical_address", "coordinate"],
    source_domains=["place", "route"],
    used_in_tools=["get_place_details_tool", "search_place_tool"],
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
    description="Gmail label or category",
    examples=["INBOX", "SENT", "STARRED", "UNREAD"],
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
    source_domains=["event", "task", "email", "file"],
)

TIMEZONE = SemanticType(
    name="timezone",
    parent="Text",
    category=TypeCategory.TEMPORAL,
    description="IANA timezone identifier",
    examples=["Europe/Paris", "America/New_York", "UTC"],
    validation_rules=["Must be valid IANA timezone"],
    source_domains=["event"],
)

DURATION = SemanticType(
    name="duration",
    parent="Intangible",
    category=TypeCategory.TEMPORAL,
    description="ISO 8601 duration",
    examples=["PT1H", "PT30M", "P1D"],
    validation_rules=["Must be valid ISO 8601 duration"],
    source_domains=["event", "route"],
)

MODIFICATION_TIMESTAMP = SemanticType(
    name="modification_timestamp",
    parent="DateTime",
    category=TypeCategory.TEMPORAL,
    description="Last modification timestamp",
    source_domains=["file", "email", "event"],
)

BIRTHDAY = SemanticType(
    name="birthday",
    parent="DateTime",
    category=TypeCategory.TEMPORAL,
    description="Person's birthday date",
    source_domains=["contact"],
)

RECENCY_FILTER = SemanticType(
    name="recency_filter",
    parent="Text",
    category=TypeCategory.TEMPORAL,
    description="Filter for recent items (e.g., 'last_week', 'last_month')",
    examples=["today", "this_week", "last_month"],
    source_domains=["email", "file", "event"],
)

FORMATTED_TIME = SemanticType(
    name="formatted_time",
    parent="Text",
    category=TypeCategory.TEMPORAL,
    description="Human-readable formatted time string",
    examples=["14:30", "2:30 PM", "14h30"],
    source_domains=["event"],
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

PRECIPITATION_PROBABILITY = SemanticType(
    name="precipitation_probability",
    parent="QuantitativeValue",
    category=TypeCategory.MEASUREMENT,
    description="Probability of precipitation (percentage)",
    examples=["30%", "80%"],
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
    parent="QuantitativeValue",
    category=TypeCategory.MEASUREMENT,
    description="Price level indicator (1-4 scale)",
    examples=["1", "3"],
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
    description="Current traffic condition",
    examples=["TRAFFIC_UNSPECIFIED", "TRAFFIC_SMOOTH", "TRAFFIC_SLOW", "TRAFFIC_JAM"],
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
    description="User's access role",
    examples=["owner", "writer", "reader"],
    source_domains=["event", "file"],
)

SHARED_STATUS = SemanticType(
    name="shared_status",
    parent="Enumeration",
    category=TypeCategory.STATUS,
    description="Whether resource is shared",
    examples=["true", "false"],
    source_domains=["file", "event"],
)

LOCATION_SOURCE = SemanticType(
    name="location_source",
    parent="Enumeration",
    category=TypeCategory.STATUS,
    description="Source of location data",
    examples=["user_input", "gps", "address_lookup"],
    source_domains=["place"],
)

BUSINESS_STATUS = SemanticType(
    name="business_status",
    parent="Enumeration",
    category=TypeCategory.STATUS,
    description="Business operational status",
    examples=["OPERATIONAL", "CLOSED_TEMPORARILY", "CLOSED_PERMANENTLY"],
    source_domains=["place"],
)

OPERATION_STATUS = SemanticType(
    name="operation_status",
    parent="Enumeration",
    category=TypeCategory.STATUS,
    description="Current operational status",
    examples=["open", "closed"],
    source_domains=["place"],
)

SEND_UPDATES_OPTION = SemanticType(
    name="send_updates_option",
    parent="Enumeration",
    category=TypeCategory.STATUS,
    description="Whether to send calendar update notifications",
    examples=["all", "externalOnly", "none"],
    source_domains=["event"],
)

OPEN_NOW_FILTER = SemanticType(
    name="open_now_filter",
    parent="Enumeration",
    category=TypeCategory.STATUS,
    description="Filter for place currently open",
    examples=["true", "false"],
    source_domains=["place"],
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

MARKDOWN_TEXT = SemanticType(
    name="markdown_text",
    parent="Text",
    category=TypeCategory.CONTENT,
    description="Markdown formatted text",
    source_domains=["agents", "file"],
)

HTML_CONTENT = SemanticType(
    name="html_content",
    parent="Text",
    category=TypeCategory.CONTENT,
    description="HTML formatted content",
    source_domains=["email", "file"],
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
    source_domains=["perplexity", "wikipedia"],
)

MESSAGE_HEADERS = SemanticType(
    name="message_headers",
    parent="Text",
    category=TypeCategory.CONTENT,
    description="Email message headers (From, To, Subject, etc.)",
    source_domains=["email"],
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
    source_domains=["event"],
)

WEBSITE_URL = SemanticType(
    name="website_url",
    parent="URL",
    category=TypeCategory.CONTENT,
    description="Website URL",
    source_domains=["place", "contact"],
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
    used_in_tools=["get_route_tool"],
)

LANGUAGE_CODE = SemanticType(
    name="language_code",
    parent="Text",
    category=TypeCategory.CATEGORY,
    description="ISO 639-1 language code",
    examples=["fr", "en", "es", "de"],
    source_domains=["agents", "wikipedia"],
)

UNIT_SYSTEM = SemanticType(
    name="unit_system",
    parent="Enumeration",
    category=TypeCategory.CATEGORY,
    description="System of units (metric/imperial)",
    examples=["METRIC", "IMPERIAL"],
    source_domains=["route", "weather"],
)

ROUTE_MODE_MODIFIER = SemanticType(
    name="route_mode_modifier",
    parent="Enumeration",
    category=TypeCategory.CATEGORY,
    description="Route calculation modifier",
    examples=["AVOID_TOLLS", "AVOID_HIGHWAYS", "AVOID_FERRIES"],
    source_domains=["route"],
)

SEARCH_MODE = SemanticType(
    name="search_mode",
    parent="Enumeration",
    category=TypeCategory.CATEGORY,
    description="Search mode type",
    examples=["text", "nearby", "details"],
    source_domains=["place"],
)

CONTENT_TYPE_FILTER = SemanticType(
    name="content_type_filter",
    parent="Enumeration",
    category=TypeCategory.CATEGORY,
    description="Filter by content type",
    examples=["document", "spreadsheet", "presentation", "folder"],
    source_domains=["file"],
)

REPLY_ALL_FLAG = SemanticType(
    name="reply_all_flag",
    parent="Enumeration",
    category=TypeCategory.CATEGORY,
    description="Whether to reply to all recipients",
    examples=["true", "false"],
    source_domains=["email"],
)

ONLY_COMPLETED_FILTER = SemanticType(
    name="only_completed_filter",
    parent="Enumeration",
    category=TypeCategory.CATEGORY,
    description="Filter for completed task only",
    examples=["true", "false"],
    source_domains=["task"],
)

SHOW_COMPLETED_FILTER = SemanticType(
    name="show_completed_filter",
    parent="Enumeration",
    category=TypeCategory.CATEGORY,
    description="Whether to show completed items",
    examples=["true", "false"],
    source_domains=["task"],
)

# =============================================================================
# GEOGRAPHIC DATA TYPES (Routes specific)
# =============================================================================

POLYLINE = SemanticType(
    name="polyline",
    parent="Text",
    category=TypeCategory.LOCATION,
    description="Encoded polyline for route path",
    source_domains=["route"],
)

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
    description="Current route condition",
    examples=["CONDITION_UNSPECIFIED", "ROUTE_PREFERRED", "ROUTE_TOLLS"],
    source_domains=["route"],
)

DEGREE_OF_OPENNESS = SemanticType(
    name="degree_of_openness",
    parent="Enumeration",
    category=TypeCategory.STATUS,
    description="How open or accessible a route/place is",
    source_domains=["place"],
)


# =============================================================================
# TYPE LOADING FUNCTION
# =============================================================================


def load_core_types(registry: TypeRegistry) -> None:
    """
    Load all core types into the registry.

    This function must be called at application startup
    to populate the global registry with the 96+ defined types.

    Args:
        registry: TypeRegistry instance to populate

    Example:
        >>> registry = get_registry()
        >>> load_core_types(registry)
        >>> len(registry)
        96+
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
    registry.register(AREA_NAME)
    registry.register(WAYPOINT)
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
    registry.register(DATE_TIME)
    registry.register(DATETIME)
    registry.register(TIMEZONE)
    registry.register(DURATION)
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
    registry.register(PRECIPITATION_PROBABILITY)
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
    registry.register(LOCATION_SOURCE)
    registry.register(BUSINESS_STATUS)
    registry.register(OPERATION_STATUS)
    registry.register(SEND_UPDATES_OPTION)
    registry.register(OPEN_NOW_FILTER)

    # Creative works and content
    registry.register(CREATIVE_WORK)
    registry.register(TEXT)
    registry.register(URL)
    registry.register(MARKDOWN_TEXT)
    registry.register(HTML_CONTENT)
    registry.register(EMAIL_BODY)
    registry.register(MESSAGE_SNIPPET)
    registry.register(FILE_CONTENT)
    registry.register(BIOGRAPHY)
    registry.register(REVIEW)
    registry.register(CITATION_URL)
    registry.register(MESSAGE_HEADERS)
    registry.register(ATTACHMENT_INFO)
    registry.register(CONFERENCE_LINK)
    registry.register(WEBSITE_URL)
    registry.register(GOOGLE_MAPS_URL)

    # Categories
    registry.register(TRAVEL_MODE)
    registry.register(LANGUAGE_CODE)
    registry.register(UNIT_SYSTEM)
    registry.register(ROUTE_MODE_MODIFIER)
    registry.register(SEARCH_MODE)
    registry.register(CONTENT_TYPE_FILTER)
    registry.register(REPLY_ALL_FLAG)
    registry.register(ONLY_COMPLETED_FILTER)
    registry.register(SHOW_COMPLETED_FILTER)

    # Geographic data
    registry.register(POLYLINE)
    registry.register(NAVIGATION_STEPS)
    registry.register(ROUTE_MATRIX)
    registry.register(OPTIMAL_ORDER)
    registry.register(ROUTE_CONDITION)
    registry.register(DEGREE_OF_OPENNESS)

    # Log statistics
    stats = registry.get_stats()
    logger.info(
        "core_types_loaded",
        total_types=stats["total_types"],
        by_category=stats["by_category"],
        total_domains=stats["total_domains"],
        message=f"Loaded {stats['total_types']} core semantic types",
    )
