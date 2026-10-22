"""Evidence entities and the concrete semantic values their payloads provide.

Properties describe available data, including optional fields, rather than
Jinja paths or permission to exchange values. Verified against tool builders
and the provider-neutral EmailMessage contract. Keeping entities together
allows their evidence surface to evolve without growing the core catalogue.
"""

from src.domains.agents.semantic.semantic_type import SemanticType, TypeCategory

CONTACT = SemanticType(
    name="Contact",
    parent="Person",
    category=TypeCategory.IDENTITY,
    description="A person in the address book with contact information",
    properties={
        "identifier": "contact_id",
        "name": "person_name",
        "email": "email_address",
        "phone": "phone_number",
        "address": "physical_address",
        "organization": "organization_name",
        "birthday": "birthday",
        "biography": "biography",
        "website": "website_url",
    },
    source_domains=["contact"],
    used_in_tools=["get_contacts_tool", "create_contact_tool", "update_contact_tool"],
)

PLACE = SemanticType(
    name="Place",
    parent="Thing",
    category=TypeCategory.LOCATION,
    description="A place with a fixed physical location",
    uri="http://schema.org/Place",
    properties={
        "identifier": "place_id",
        "address": "physical_address",
        "locality": "locality",
        "phone": "phone_number",
        "coordinates": "coordinate",
        "website": "website_url",
        "maps_url": "google_maps_url",
        "rating": "rating",
        "review": "review",
        "business_status": "business_status",
        "price_level": "price_level",
    },
    source_domains=["place"],
    used_in_tools=["get_places_tool"],
)

CALENDAR_EVENT = SemanticType(
    name="CalendarEvent",
    parent="Event",
    category=TypeCategory.TEMPORAL,
    description="An event in a calendar (meeting, appointment, etc.)",
    properties={
        "identifier": "event_id",
        "calendar": "calendar_id",
        "location": "physical_address",
        "start_datetime": "event_start_datetime",
        "end_datetime": "datetime",
        "timezone": "timezone",
        "attendees": "email_address",
        "conference": "conference_link",
    },
    source_domains=["event"],
    used_in_tools=["create_event_tool", "update_event_tool", "get_events_tool"],
)

EMAIL_MESSAGE = SemanticType(
    name="EmailMessage",
    parent="CreativeWork",
    category=TypeCategory.CONTENT,
    description="An email message in the user's mailbox",
    uri="http://schema.org/EmailMessage",
    properties={
        "sender": "email_address",
        "recipients": "email_address",
        "thread": "thread_id",
        "identifier": "message_id",
        "body": "email_body",
        "snippet": "message_snippet",
        "labels": "email_label_id",
        "attachments": "attachment_info",
    },
    source_domains=["email"],
    used_in_tools=["get_emails_tool", "reply_email_tool", "forward_email_tool"],
)


SMS_MESSAGE = SemanticType(
    name="SmsMessage",
    parent="CreativeWork",
    category=TypeCategory.CONTENT,
    description="A received SMS retained in LIA, with exact identity/date provenance and paginated literal body.",
    properties={
        "identifier": "sms_message_id",
        "sender": "Text",
        "body": "Text",
        "received_at": "datetime",
    },
    source_domains=["sms"],
    used_in_tools=["list_sms_tool", "search_sms_tool", "get_sms_tool"],
)
