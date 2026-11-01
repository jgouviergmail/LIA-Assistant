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

__all__ = [
    "CONTACT_ADDRESS_DESCRIPTION",
    "CONTACT_EMAIL_DESCRIPTION",
    "CONTACT_PHONE_DESCRIPTION",
]
