"""What a single e-mail, phone or address means on ``update_contact_tool`` (ADR-369, D2).

The value used to REPLACE the contact's whole list: changing someone's e-mail
deleted their others. It now replaces the PRIMARY value and keeps the rest,
and the model is told so in ONE wording per parameter, read by the planner's
manifest AND the tool's own schema — the ReAct loop binds the schema and never
sees the manifest (ADR-310).
"""

from typing import Final

CONTACT_EMAIL_DESCRIPTION: Final = (
    "New e-mail address: replaces the contact's primary e-mail; its other e-mails are kept."
)
CONTACT_PHONE_DESCRIPTION: Final = (
    "New phone number: replaces the contact's primary phone; its other phones are kept."
)
CONTACT_ADDRESS_DESCRIPTION: Final = (
    "New postal address (e.g. '15 rue de la Paix, Paris 75001'): replaces the contact's "
    "primary address; its other addresses are kept."
)

CONTACT_GIVEN_NAME_DESCRIPTION: Final = "Their given name; an empty text empties it."
CONTACT_FAMILY_NAME_DESCRIPTION: Final = "Their family name; an empty text empties it."
CONTACT_JOB_TITLE_DESCRIPTION: Final = "What they do at work; an empty text empties it."
CONTACT_WEBSITE_DESCRIPTION: Final = "Their website; an empty text removes it."
CONTACT_BIRTHDAY_DESCRIPTION: Final = (
    "Their birthday, an ISO date (YYYY-MM-DD), year included. Resolve a relative expression "
    "yourself from the current date before passing it."
)
CONTACT_CLEAR_BIRTHDAY_DESCRIPTION: Final = (
    "true to REMOVE the contact's birthday. Never together with 'birthday'."
)

__all__ = [
    "CONTACT_ADDRESS_DESCRIPTION",
    "CONTACT_BIRTHDAY_DESCRIPTION",
    "CONTACT_CLEAR_BIRTHDAY_DESCRIPTION",
    "CONTACT_EMAIL_DESCRIPTION",
    "CONTACT_FAMILY_NAME_DESCRIPTION",
    "CONTACT_GIVEN_NAME_DESCRIPTION",
    "CONTACT_JOB_TITLE_DESCRIPTION",
    "CONTACT_PHONE_DESCRIPTION",
    "CONTACT_WEBSITE_DESCRIPTION",
]
