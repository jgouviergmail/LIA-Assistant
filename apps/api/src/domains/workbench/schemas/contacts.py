"""What the contacts routes take and answer (ADR-369, D4).

A contact's e-mails, phones and addresses are TYPED LISTS on the wire, the
write contract the three clients share (``normalizers/contact_values``): a list
sent REPLACES that list, a list left out is KEPT — so a change naming only a
phone never rewrites the e-mails. A list the provider cannot hold is refused
whole, with its bound. Reading is forgiving and writing strict: a contact is
shown as its provider wrote it (an address on several lines, a kind the person
typed), and only what is written is checked. A page says what comes next — a
cursor for the account's contacts, a cut for a search or a group the provider
answers in one go — never presenting a part as the whole (ADR-185).
"""

from __future__ import annotations

from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from src.core.constants import (
    WORKBENCH_CONTACT_ADDRESS_MAX_CHARS,
    WORKBENCH_CONTACT_NAME_MAX_CHARS,
    WORKBENCH_CONTACT_NOTES_MAX_CHARS,
    WORKBENCH_CONTACT_VALUE_MAX_CHARS,
    WORKBENCH_CONTACT_VALUES_MAX,
    WORKBENCH_MAIL_QUERY_MAX_CHARS,
)
from src.domains.shared.text_normalization import fold_name
from src.domains.workbench.ids import OptionalPageToken, OptionalProviderId, ProviderId

_ONE_LINE = r"^[^\x00-\x1f\x7f]+$"
_NAME = StringConstraints(
    strip_whitespace=True,
    min_length=1,
    max_length=WORKBENCH_CONTACT_NAME_MAX_CHARS,
    pattern=_ONE_LINE,
)
Name = Annotated[str, _NAME]
# The optional ones carry the constraint on ``str | None`` (``test_annotated_metadata_guard``).
OptionalName = Annotated[str | None, _NAME]
OptionalOrganization = Annotated[
    str | None,
    StringConstraints(max_length=WORKBENCH_CONTACT_NAME_MAX_CHARS, pattern=r"^[^\x00-\x1f\x7f]*$"),
]
OptionalNotes = Annotated[
    str | None, StringConstraints(max_length=WORKBENCH_CONTACT_NOTES_MAX_CHARS)
]
_Value = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=WORKBENCH_CONTACT_VALUE_MAX_CHARS,
        pattern=_ONE_LINE,
    ),
]
#: A postal address keeps its LINE BREAKS (Google writes its own lines, and a
#: Google client keeps an address unchanged only when its text comes back
#: identical); every other control character is refused.
_Address = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=WORKBENCH_CONTACT_ADDRESS_MAX_CHARS,
        pattern=r"^[^\x00-\x09\x0b\x0c\x0e-\x1f\x7f]+$",
    ),
]
#: A kind is a provider word (``home``) or a label the person typed, in any script.
_Kind = Annotated[str | None, StringConstraints(max_length=64, pattern=r"^[^\x00-\x1f\x7f]*$")]


class ContactValue(BaseModel):
    """An e-mail address or a phone number as the provider holds it, and its kind.

    A READ shape: whatever the provider wrote is shown, never refused — the
    rules a value must follow on the way in are ``ContactValueInput``'s.
    """

    model_config = ConfigDict(frozen=True)

    value: str = Field(description="The address or the number, as written.")
    type: str | None = Field(default=None, description="Its kind; null when unsaid.")


class ContactAddress(BaseModel):
    """A postal address as the provider holds it (its lines kept), and its kind.

    A READ shape, like ``ContactValue``; ``ContactAddressInput`` checks the way in.
    """

    model_config = ConfigDict(frozen=True)

    formatted: str = Field(description="The address, its lines kept.")
    type: str | None = Field(default=None, description="Its kind; null when unsaid.")


class ContactValueInput(BaseModel):
    """An e-mail address or a phone number to write: one line, and its kind."""

    model_config = ConfigDict(extra="forbid")

    value: _Value = Field(description="The address or the number, on one line.")
    type: _Kind = Field(default=None, description="Its kind; null when unsaid.")


class ContactAddressInput(BaseModel):
    """A postal address to write, its lines kept, and its kind."""

    model_config = ConfigDict(extra="forbid")

    formatted: _Address = Field(description="The address, its lines kept.")
    type: _Kind = Field(default=None, description="Its kind; null when unsaid.")


_Values = Annotated[list[ContactValueInput], Field(max_length=WORKBENCH_CONTACT_VALUES_MAX)]
OptionalValues = Annotated[
    list[ContactValueInput] | None, Field(max_length=WORKBENCH_CONTACT_VALUES_MAX)
]
_Addresses = Annotated[list[ContactAddressInput], Field(max_length=WORKBENCH_CONTACT_VALUES_MAX)]
OptionalAddresses = Annotated[
    list[ContactAddressInput] | None, Field(max_length=WORKBENCH_CONTACT_VALUES_MAX)
]


class ContactsQuery(BaseModel):
    """Which contacts a page lists: the account's, a search, or a group (Google)."""

    model_config = ConfigDict(extra="forbid")

    q: Annotated[
        str | None,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=WORKBENCH_MAIL_QUERY_MAX_CHARS
        ),
    ] = Field(default=None, description="The words searched (a name, an address, a number).")
    group: OptionalProviderId = Field(default=None, description="A contact group (Google).")
    page_token: OptionalPageToken = Field(default=None, description="The next page's token.")

    @model_validator(mode="after")
    def _one_listing(self) -> Self:
        if self.q is not None and self.group is not None:
            raise ValueError("a group is listed whole, never searched")
        return self


class ContactSummary(BaseModel):
    """One contact as the list draws it."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The provider's id of the contact.")
    name: str = Field(description="Its name (may be empty at the provider).")
    given_name: str | None = Field(
        default=None, description="Its given name, when the provider holds the part."
    )
    family_name: str | None = Field(
        default=None, description="Its family name, when the provider holds the part."
    )
    email: str | None = Field(description="Its first e-mail address.")
    phone: str | None = Field(description="Its first phone number.")
    organization: str | None = Field(description="Where they work.")
    name_key: str = Field(
        default="",
        description="The name folded once (`fold_name`): what « see the relationship » matches.",
    )

    @model_validator(mode="before")
    @classmethod
    def _fold_the_name(cls, data: object) -> object:
        if isinstance(data, dict) and "name" in data:
            return {**data, "name_key": fold_name(str(data["name"]))}
        return data


class Contact(ContactSummary):
    """One contact, whole."""

    emails: list[ContactValue] = Field(description="Every e-mail address, typed.")
    phones: list[ContactValue] = Field(description="Every phone number, typed.")
    addresses: list[ContactAddress] = Field(description="Every postal address, typed.")
    notes: str | None = Field(description="Its notes.")


class ContactsPage(BaseModel):
    """A page of contacts: the next one's token, or the cut of a page answered in one go."""

    items: list[ContactSummary] = Field(description="The contacts of this page.")
    next_page_token: str | None = Field(description="The next page's token; None on the last.")
    truncated: bool = Field(
        description="A search or a group answered as many as a page holds: there may be more."
    )


class ContactGroup(BaseModel):
    """One group of contacts (Google)."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The group's resource name.")
    name: str = Field(description="Its name.")
    count: int | None = Field(description="How many contacts it holds, when Google says.")


class ContactGroups(BaseModel):
    """The account's contact groups (Google)."""

    groups: list[ContactGroup] = Field(description="Its groups, the person's own first.")


class NewContact(BaseModel):
    """A contact to create, once per submission."""

    model_config = ConfigDict(extra="forbid")

    name: Name = Field(description="Their name.")
    emails: _Values = Field(default_factory=list, description="Their e-mail addresses.")
    phones: _Values = Field(default_factory=list, description="Their phone numbers.")
    addresses: _Addresses = Field(default_factory=list, description="Their postal addresses.")
    organization: OptionalOrganization = Field(default=None, description="Where they work.")
    notes: OptionalNotes = Field(default=None, description="Notes about them.")
    idempotency_key: UUID = Field(description="One key per submission (a replay creates nothing).")


class ContactChange(BaseModel):
    """What changes on one contact: a list sent replaces that list, one left out is kept."""

    model_config = ConfigDict(extra="forbid")

    id: ProviderId = Field(description="The contact.")
    name: OptionalName = Field(default=None, description="A new name.")
    organization: OptionalOrganization = Field(default=None, description="A new organization.")
    notes: OptionalNotes = Field(default=None, description="New notes ('' empties them).")
    emails: OptionalValues = Field(default=None, description="The e-mails, replaced whole.")
    phones: OptionalValues = Field(default=None, description="The phones, replaced whole.")
    addresses: OptionalAddresses = Field(default=None, description="The addresses, replaced whole.")

    @model_validator(mode="after")
    def _changes_something(self) -> Self:
        named = (self.name, self.organization, self.notes, self.emails, self.phones, self.addresses)
        if all(value is None for value in named):
            raise ValueError("a change names at least one field")
        return self
