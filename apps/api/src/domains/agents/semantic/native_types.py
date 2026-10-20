"""Value types carried by current native tools and explicit MCP schemas.

Resource identifiers keep distinct names: a Gmail attachment handle, a cloud
file id and a LIA attachment UUID are different values. A label id likewise
cannot substitute for a human-readable label name. This module declares only
types with verified catalogue fields; arbitrary MCP field names do not create
types.
"""

from src.domains.agents.semantic.semantic_type import SemanticType, TypeCategory
from src.domains.agents.semantic.type_registry import TypeRegistry

DATE = SemanticType(
    name="Date",
    parent="Intangible",
    category=TypeCategory.TEMPORAL,
    uri="http://schema.org/Date",
    description="ISO 8601 calendar date without a time or timezone (YYYY-MM-DD)",
    examples=["2026-10-06"],
    source_domains=["memory", "journal", "weather"],
)

UNIX_TIMESTAMP = SemanticType(
    name="unix_timestamp",
    parent="Intangible",
    category=TypeCategory.TEMPORAL,
    description="Unix timestamp: seconds since 1970-01-01T00:00:00Z, not ISO text",
    source_domains=["weather"],
)

DURATION_MINUTES = SemanticType(
    name="duration_minutes",
    parent="Intangible",
    category=TypeCategory.TEMPORAL,
    description="Numeric elapsed duration in minutes, not an ISO 8601 duration string",
    source_domains=["route"],
)

FILE_NAME = SemanticType(
    name="file_name",
    parent="Text",
    category=TypeCategory.CONTENT,
    description="File display name including its extension; never a resource identifier",
    source_domains=["file", "document", "generated_file", "email"],
)

ORGANIZATION_NAME = SemanticType(
    name="organization_name",
    parent="Text",
    category=TypeCategory.IDENTITY,
    description="Human-readable organization name",
    source_domains=["contact"],
)

TICKET_ID = SemanticType(
    name="ticket_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="UUID of a user's workboard ticket, distinct from its title",
    source_domains=["ticket"],
)

TICKET_STATUS = SemanticType(
    name="ticket_status",
    parent="Enumeration",
    category=TypeCategory.STATUS,
    description="Workboard column, using the TicketStatus vocabulary",
    source_domains=["ticket"],
)

TICKET_PRIORITY = SemanticType(
    name="ticket_priority",
    parent="Enumeration",
    category=TypeCategory.CATEGORY,
    description="Workboard ticket priority, using the TicketPriority vocabulary",
    source_domains=["ticket"],
)

EMAIL_ATTACHMENT_ID = SemanticType(
    name="email_attachment_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Mail provider's handle for an attachment of a particular message",
    source_domains=["email"],
)

EMAIL_LABEL_ID = SemanticType(
    name="email_label_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Mail provider's label identifier, distinct from a label's display name",
    source_domains=["email"],
)

MEMORY_CATEGORY = SemanticType(
    name="memory_category",
    parent="Enumeration",
    category=TypeCategory.CATEGORY,
    description="Long-term user memory category, using MemoryCategoryType",
    source_domains=["memory"],
)

HEALTH_METRIC_KIND = SemanticType(
    name="health_metric_kind",
    parent="Enumeration",
    category=TypeCategory.CATEGORY,
    description="Health signal kind; each measured value retains its separate unit",
    source_domains=["health"],
)

JOURNAL_ENTRY_KIND = SemanticType(
    name="journal_entry_kind",
    parent="Enumeration",
    category=TypeCategory.CATEGORY,
    description="LIA journal entry kind: directive, pattern or portrait_facet",
    source_domains=["journal"],
)

IDENTITY_CONFIDENCE = SemanticType(
    name="identity_confidence",
    parent="Enumeration",
    category=TypeCategory.STATUS,
    description="CRM identity matching verdict: exact or normalized, never a numeric score",
    source_domains=["contact", "task", "peer", "telephony"],
)

EFFECT_STATUS = SemanticType(
    name="effect_status",
    parent="Enumeration",
    category=TypeCategory.STATUS,
    description="Recorded action outcome, using EffectStatus; distinct from treatment status",
    source_domains=["activity"],
)

LATITUDE = SemanticType(
    name="latitude",
    parent="QuantitativeValue",
    category=TypeCategory.LOCATION,
    description="Latitude in decimal degrees, one component of a coordinate pair",
    source_domains=["place"],
)

LONGITUDE = SemanticType(
    name="longitude",
    parent="QuantitativeValue",
    category=TypeCategory.LOCATION,
    description="Longitude in decimal degrees, one component of a coordinate pair",
    source_domains=["place"],
)

INCIDENT_ID = SemanticType(
    name="incident_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="UUID of a persisted platform diagnostic incident, not its correlation key",
    source_domains=["devops"],
)

DEVOPS_SESSION_ID = SemanticType(
    name="devops_session_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Remote Claude CLI session handle, distinct from the LIA conversation id",
    source_domains=["devops"],
)

HUE_LIGHT_ID = SemanticType(
    name="hue_light_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description="Philips Hue bridge light resource id, distinct from its human display name",
    source_domains=["hue"],
)

SMS_MESSAGE_ID = SemanticType(
    name="sms_message_id",
    parent="Identifier",
    category=TypeCategory.IDENTITY,
    description="Exact UUID of one owned archived received SMS; never a phone number, email message id or contact id.",
    source_domains=["sms"],
    used_in_tools=["get_sms_tool"],
)

ALL_NATIVE_TYPES: tuple[SemanticType, ...] = (
    SMS_MESSAGE_ID,
    DATE,
    UNIX_TIMESTAMP,
    DURATION_MINUTES,
    FILE_NAME,
    ORGANIZATION_NAME,
    TICKET_ID,
    TICKET_STATUS,
    TICKET_PRIORITY,
    EMAIL_ATTACHMENT_ID,
    EMAIL_LABEL_ID,
    MEMORY_CATEGORY,
    HEALTH_METRIC_KIND,
    JOURNAL_ENTRY_KIND,
    IDENTITY_CONFIDENCE,
    EFFECT_STATUS,
    LATITUDE,
    LONGITUDE,
    INCIDENT_ID,
    DEVOPS_SESSION_ID,
    HUE_LIGHT_ID,
)


def load_native_types(registry: TypeRegistry) -> None:
    """Complete the static ontology through its existing boot entry point."""
    for type_def in ALL_NATIVE_TYPES:
        registry.register(type_def)
