"""What the contacts routes take and answer (ADR-369, D4).

A contact's e-mails, phones and addresses are TYPED LISTS on the wire, the
write contract the three clients share (``normalizers/contact_values``): a list
sent REPLACES that list, a list left out is KEPT — so a change naming only a
phone never rewrites the e-mails. A list the provider cannot hold is refused
whole, with its bound. Reading is forgiving and writing strict: a contact is
shown as its provider wrote it (an address on several lines, a kind the person
typed), and only what is written is checked. A page says what comes next — a
cursor for the account's contacts, a cut for a search or a group the provider
answers in one go — never presenting a part as the whole (ADR-185). What a contact
holds beyond its lists goes by the clients' contract (``clients/contact_details``):
left out it is kept, an empty text empties it, a birthday goes by a flag. A birthday
reads as an ISO day, or ``--MM-DD`` when the provider holds no year; none is written
without one.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from src.core.constants import (
    WORKBENCH_CONTACT_ADDRESS_MAX_CHARS,
    WORKBENCH_CONTACT_HISTORY_MAX_ADDRESSES,
    WORKBENCH_CONTACT_HISTORY_MAX_PHONES,
    WORKBENCH_CONTACT_NAME_MAX_CHARS,
    WORKBENCH_CONTACT_NOTES_MAX_CHARS,
    WORKBENCH_CONTACT_VALUE_MAX_CHARS,
    WORKBENCH_CONTACT_VALUES_MAX,
    WORKBENCH_MAIL_QUERY_MAX_CHARS,
)
from src.domains.shared.text_normalization import fold_name
from src.domains.sms.constants import SMS_CARD_EXCERPT_CHARS
from src.domains.telephony.models import PhoneCallOutcome, PhoneCallStatus
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
OptionalWebsite = Annotated[
    str | None,
    StringConstraints(max_length=WORKBENCH_CONTACT_VALUE_MAX_CHARS, pattern=r"^[^\x00-\x1f\x7f]*$"),
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


#: Why a source has what it has: ``used`` (it was read, maybe finding nothing), ``disabled`` (no
#: connector, a capability switched off, or LIA holds no record of that kind at all),
#: ``unavailable`` (the read failed) and ``not_requested`` (the contact gives it nothing to look
#: under: no address for mail and meetings, no number for calls and texts).
HistorySource = Literal["used", "disabled", "unavailable", "not_requested"]


class ContactHistoryQuery(BaseModel):
    """Whose exchanges are asked: an address never carries a search operator, a number is a value."""

    model_config = ConfigDict(extra="forbid")

    address: list[EmailStr] = Field(
        default_factory=list,
        max_length=WORKBENCH_CONTACT_HISTORY_MAX_ADDRESSES,
        description="The contact's addresses.",
    )
    phone: list[_Value] = Field(
        default_factory=list,
        max_length=WORKBENCH_CONTACT_HISTORY_MAX_PHONES,
        description="The contact's numbers, written as they were saved.",
    )

    @model_validator(mode="after")
    def _something_to_look_under(self) -> Self:
        if not self.address and not self.phone:
            raise ValueError("a contact's history is asked by an address or a number")
        return self


class HistoryMail(BaseModel):
    """One message exchanged with a contact."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The message.")
    subject: str = Field(description="Its subject; empty for none, the page says so.")
    at: datetime | None = Field(description="When it was exchanged.")


class HistoryMeeting(BaseModel):
    """One meeting with a contact."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The event.")
    title: str = Field(description="Its title; empty for none, the page says so.")
    at: datetime | None = Field(description="When it began.")
    day: str | None = Field(description="Its day, on the person's clock.")
    all_day: bool = Field(description="It takes whole days.")
    calendar_id: str = Field(description="The calendar it was read on.")


class HistoryCall(BaseModel):
    """One call LIA placed to a contact: never the number it dialled."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(description="The call, as the calls list opens it.")
    at: datetime = Field(description="When it was placed.")
    status: PhoneCallStatus = Field(description="Where the call stands, or how it ended.")
    outcome: PhoneCallOutcome | None = Field(description="What it achieved, once known.")
    seconds: float | None = Field(description="How long it lasted, once known.")
    purpose: str = Field(description="What LIA was asked to accomplish.")


class HistoryText(BaseModel):
    """One text a contact's number sent: never the number it came from."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(description="The text, as the SMS page opens it.")
    at: datetime = Field(description="When it was received.")
    excerpt: str = Field(
        max_length=SMS_CARD_EXCERPT_CHARS, description="Its beginning, shown literally."
    )
    truncated: bool = Field(description="More of it remains beyond the excerpt.")


class ContactHistory(BaseModel):
    """The latest exchanges with a contact, each source saying why it has nothing."""

    model_config = ConfigDict(frozen=True)

    mail: HistorySource = Field(description="What became of the mailbox's read.")
    received: list[HistoryMail] = Field(description="The latest mail they sent the person.")
    sent: list[HistoryMail] = Field(description="The latest mail the person sent them.")
    calendar: HistorySource = Field(description="What became of the calendar's read.")
    organized_by_them: list[HistoryMeeting] = Field(
        description="The latest meetings they organised, the person invited."
    )
    organized_by_you: list[HistoryMeeting] = Field(
        description="The latest meetings the person organised, they invited."
    )
    shared: list[HistoryMeeting] = Field(
        description="The latest meetings with them whose organiser nobody named."
    )
    meetings_window_days: int = Field(description="How far back the calendar was read.")
    meetings_cut: bool = Field(description="A window held more events than were read.")
    telephony: HistorySource = Field(description="What became of the calls' read.")
    calls: list[HistoryCall] = Field(description="The latest calls LIA placed to their numbers.")
    calls_window: int = Field(description="How many of LIA's latest calls were read.")
    calls_cut: bool = Field(
        description="LIA placed more calls than were read, and the list is not full."
    )
    sms: HistorySource = Field(description="What became of the texts' read.")
    texts: list[HistoryText] = Field(description="The latest texts their numbers sent.")
    texts_window: int = Field(description="How many of the archive's latest senders were read.")
    texts_cut: bool = Field(description="The archive holds more senders than were read.")


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
    job_title: str | None = Field(default=None, description="What they do.")
    website: str | None = Field(default=None, description="Its first website, as written.")
    birthday: str | None = Field(
        default=None, description="An ISO day, or --MM-DD when the provider holds no year."
    )


class ContactsPage(BaseModel):
    """A page of contacts: the next one's token, or the cut of a page answered in one go."""

    items: list[ContactSummary] = Field(description="The contacts of this page.")
    next_page_token: str | None = Field(description="The next page's token; None on the last.")
    truncated: bool = Field(
        description="A search or a group answered as many as a page holds: there may be more."
    )


class ContactGroup(BaseModel):
    """One group of contacts."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The group's id.")
    name: str = Field(description="Its name.")
    count: int | None = Field(description="How many contacts it holds, when that is exact.")
    own: bool = Field(default=True, description="The person's: it can be renamed and deleted.")


class ContactGroups(BaseModel):
    """Contact groups."""

    groups: list[ContactGroup] = Field(description="Its groups, the person's own first.")


class _ContactDetailFields(BaseModel):
    """What a write carries beyond a name, a company and notes: left out, it is kept."""

    given_name: OptionalOrganization = Field(default=None, description="Their given name.")
    family_name: OptionalOrganization = Field(default=None, description="Their family name.")
    job_title: OptionalOrganization = Field(default=None, description="What they do.")
    website: OptionalWebsite = Field(default=None, description="Their website.")
    birthday: date | None = Field(default=None, description="Their birthday.")


class NewContact(_ContactDetailFields):
    """A contact to create, once per submission."""

    model_config = ConfigDict(extra="forbid")

    name: Name = Field(description="Their name.")
    emails: _Values = Field(default_factory=list, description="Their e-mail addresses.")
    phones: _Values = Field(default_factory=list, description="Their phone numbers.")
    addresses: _Addresses = Field(default_factory=list, description="Their postal addresses.")
    organization: OptionalOrganization = Field(default=None, description="Where they work.")
    notes: OptionalNotes = Field(default=None, description="Notes about them.")
    idempotency_key: UUID = Field(description="One key per submission (a replay creates nothing).")


class OtherContactSave(BaseModel):
    """A contact met in mail, to keep among the person's own (Google)."""

    model_config = ConfigDict(extra="forbid")

    id: ProviderId = Field(description="The contact, as « other contacts » names it.")
    idempotency_key: UUID = Field(description="One key per submission (a replay saves nothing).")


class GroupJoin(BaseModel):
    """A contact joining a group by its name: a name nobody holds makes the group."""

    model_config = ConfigDict(extra="forbid")

    contact_id: ProviderId = Field(description="The contact.")
    name: Name = Field(description="The group's name.")


class GroupLeave(BaseModel):
    """A contact leaving a group."""

    model_config = ConfigDict(extra="forbid")

    contact_id: ProviderId = Field(description="The contact.")
    group_id: ProviderId = Field(description="The group.")


class GroupRename(BaseModel):
    """A group's new name."""

    model_config = ConfigDict(extra="forbid")

    id: ProviderId = Field(description="The group.")
    name: Name = Field(description="Its new name.")


class ImportFailure(BaseModel):
    """One card an import could not make a contact of."""

    model_config = ConfigDict(frozen=True)

    position: int = Field(description="Its place in the file, from 1.")
    name: str = Field(description="The name it carries; empty when it carries none.")


class ContactsImported(BaseModel):
    """What an import did: never all-or-nothing."""

    done: int = Field(description="How many cards became contacts.")
    failed: list[ImportFailure] = Field(description="The others, in the file's order.")


class ContactChange(_ContactDetailFields):
    """What changes on one contact: a list sent replaces that list, one left out is kept."""

    model_config = ConfigDict(extra="forbid")

    id: ProviderId = Field(description="The contact.")
    name: OptionalName = Field(default=None, description="A new name.")
    organization: OptionalOrganization = Field(default=None, description="A new organization.")
    notes: OptionalNotes = Field(default=None, description="New notes ('' empties them).")
    emails: OptionalValues = Field(default=None, description="The e-mails, replaced whole.")
    phones: OptionalValues = Field(default=None, description="The phones, replaced whole.")
    addresses: OptionalAddresses = Field(default=None, description="The addresses, replaced whole.")
    clear_birthday: bool = Field(default=False, description="Take the birthday off.")

    @model_validator(mode="after")
    def _changes_something(self) -> Self:
        if self.birthday is not None and self.clear_birthday:
            raise ValueError("a birthday is written or taken off, never both")
        named = self.model_dump(exclude={"id", "clear_birthday"}, exclude_none=True)
        if not named and not self.clear_birthday:
            raise ValueError("a change names at least one field")
        return self
