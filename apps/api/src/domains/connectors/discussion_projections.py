"""Typed, readable provider projections: dates and record states retain their native meaning."""

from datetime import UTC, datetime
from datetime import date as CivilDate
from typing import Annotated
from urllib.parse import quote, unquote

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from src.domains.shared.discussion_lines import evidence_lines
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    GraphRecurrence,
    SourceKey,
    semantic_version,
)


class ProviderValue(BaseModel):
    """The base of a provider projection: frozen, unknown provider fields ignored."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class EventMoment(ProviderValue):
    """A calendar instant or civil date, with its time zone, as the provider sent it."""

    dateTime: AwareDatetime | None = None
    date: CivilDate | None = None
    timeZone: str | None = None

    @field_validator("date", mode="before")
    @classmethod
    def civil_date(cls, value: object) -> object:
        """Refuse an all-day date that arrives as a datetime or a timestamp string."""
        if isinstance(value, datetime) or (isinstance(value, str) and len(value) != 10):
            raise ValueError("calendar civil date must remain a date")
        return value


class EventPerson(ProviderValue):
    """An attendee: address, name, response, and whether it is the account itself."""

    email: str = ""
    displayName: str = ""
    responseStatus: str = ""
    self: bool = False


class CalendarRecord(ProviderValue):
    """A calendar event in the providers' normalised shape."""

    id: Annotated[str, Field(min_length=1, max_length=256)]
    summary: str = ""
    description: str = ""
    start: EventMoment
    end: EventMoment
    originalStartTime: EventMoment | None = None
    recurringEventId: str | None = None
    recurrence: tuple[str, ...] = ()
    recurrence_pattern: GraphRecurrence | None = None
    status: str = "confirmed"
    attendees: tuple[EventPerson, ...] = ()
    created: AwareDatetime | None = None


def provider_reference(
    source: SourceKey, account: str, identifier: str, *, occurrence: str = ""
) -> str:
    """Build a reference to a provider object, scoped to its source account.

    The account is hashed, the identifier percent-encoded, and an occurrence (a
    moved recurring instance) suffixed by its hash, so two accounts or two
    occurrences never share a reference.

    Args:
        source: The source.
        account: The source account.
        identifier: The provider's identifier.
        occurrence: The occurrence's original start, for a recurring instance.

    Returns:
        The reference.
    """
    scope = semantic_version((account,))[:16]
    suffix = f"#{semantic_version((occurrence,))[:16]}" if occurrence else ""
    return f"{source.value}:{scope}:{quote(identifier, safe='')}{suffix}"


def provider_identifier(reference: str, source: SourceKey, account: str) -> str:
    """Recover the provider identifier a reference names, for this source account only.

    Args:
        reference: The reference.
        source: The source it must belong to.
        account: The source account it must belong to.

    Returns:
        The provider's identifier.

    Raises:
        ValueError: The reference belongs to another source or account.
    """
    prefix, scope, identifier = reference.split(":", 2)
    if prefix != source.value or scope != semantic_version((account,))[:16]:
        raise ValueError("provider reference belongs to another source account")
    return unquote(identifier.split("#", 1)[0])


def calendar_evidence(
    raw: object, *, account: str, now: datetime, chars: int
) -> DiscussionEvidence:
    """Project a calendar event into planned evidence, keeping native dates and recurrence.

    Args:
        raw: The provider record.
        account: The source account it came from.
        now: The read's clock.
        chars: The excerpt's length bound.

    Returns:
        The evidence; a cancelled event is a cancelled occurrence.
    """
    record = CalendarRecord.model_validate(raw)
    original = record.originalStartTime
    origin = original.model_dump_json() if original else ""
    text = record.model_dump_json()
    return DiscussionEvidence(
        reference=provider_reference(SourceKey.CALENDAR, account, record.id, occurrence=origin),
        source=SourceKey.CALENDAR,
        source_account=account,
        object_id=record.id,
        version=semantic_version((text,)),
        observed_at=now,
        recorded_at=record.created,
        occurred_at=record.start.dateTime,
        planned_date=record.start.date,
        interval_start=record.start.dateTime if record.end.dateTime is not None else None,
        interval_end=record.end.dateTime if record.start.dateTime is not None else None,
        original_start=original.dateTime if original else None,
        original_date=original.date if original else None,
        series_id=record.recurringEventId,
        native_recurrence=record.recurrence_pattern,
        recurrence_rule=next(
            (rule for rule in record.recurrence if rule.startswith("RRULE:")), None
        ),
        assertion="planned",
        occurrence_state="cancelled" if record.status == "cancelled" else "scheduled",
        category="calendar_schedule",
        excerpt=text[:chars],
        excerpt_truncated=len(text) > chars,
    )


class EmailRecord(ProviderValue):
    """An e-mail in the providers' normalised shape."""

    id: Annotated[str, Field(min_length=1, max_length=256)]
    subject: str = ""
    from_: str = Field(default="", alias="from")
    to: str = ""
    date: str = ""
    internalDate: str | None = None
    body: str = ""
    snippet: str = ""


def email_evidence(raw: object, *, account: str, now: datetime, chars: int) -> DiscussionEvidence:
    """Project an e-mail into reported evidence, dated by its internal timestamp.

    Args:
        raw: The provider record.
        account: The source account it came from.
        now: The read's clock.
        chars: The excerpt's length bound.

    Returns:
        The evidence.
    """
    record = EmailRecord.model_validate(raw)
    text = record.model_dump_json(by_alias=True)
    recorded = (
        datetime.fromtimestamp(int(record.internalDate) / 1000, UTC)
        if record.internalDate and record.internalDate.isdigit()
        else None
    )
    return DiscussionEvidence(
        reference=provider_reference(SourceKey.EMAILS, account, record.id),
        source=SourceKey.EMAILS,
        source_account=account,
        object_id=record.id,
        version=semantic_version((text,)),
        observed_at=now,
        recorded_at=recorded,
        assertion="reported",
        category="email_message",
        excerpt=text[:chars],
        excerpt_truncated=len(text) > chars,
    )


class ContactName(ProviderValue):
    """A contact's name parts."""

    displayName: str = ""
    givenName: str = ""
    familyName: str = ""


class ContactValue(ProviderValue):
    """A contact's address or number, with its label."""

    value: str = ""
    type: str = ""


class ContactOrganization(ProviderValue):
    """A contact's organisation, title and department."""

    name: str = ""
    title: str = ""
    department: str = ""


class BirthdayDate(ProviderValue):
    """A birthday's month and day, and its year when known."""

    year: int | None = None
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)


class ContactBirthday(ProviderValue):
    """A contact's birthday."""

    date: BirthdayDate


class ContactRecord(ProviderValue):
    """A contact in the providers' normalised shape."""

    resourceName: Annotated[str, Field(min_length=1, max_length=256)]
    names: tuple[ContactName, ...] = ()
    emailAddresses: tuple[ContactValue, ...] = ()
    phoneNumbers: tuple[ContactValue, ...] = ()
    organizations: tuple[ContactOrganization, ...] = ()
    birthdays: tuple[ContactBirthday, ...] = ()
    biographies: tuple[ContactValue, ...] = ()


def contact_evidence(raw: object, *, account: str, now: datetime, chars: int) -> DiscussionEvidence:
    """Project a contact into reported evidence about one subject: the contact.

    Args:
        raw: The provider record.
        account: The source account it came from.
        now: The read's clock.
        chars: The excerpt's length bound.

    Returns:
        The evidence.
    """
    record = ContactRecord.model_validate(raw)
    text = record.model_dump_json()
    return DiscussionEvidence(
        reference=provider_reference(SourceKey.CONTACTS, account, record.resourceName),
        source=SourceKey.CONTACTS,
        source_account=account,
        object_id=record.resourceName,
        subject_id=f"contact:{semantic_version((account,record.resourceName))}",
        version=semantic_version((text,)),
        observed_at=now,
        assertion="reported",
        category="contact_record",
        excerpt=text[:chars],
        excerpt_truncated=len(text) > chars,
    )


class TaskRecord(ProviderValue):
    """A task in the providers' normalised shape."""

    id: Annotated[str, Field(min_length=1, max_length=256)]
    title: str = ""
    notes: str = ""
    status: str = "needsAction"
    due: str | None = None
    completed: str | None = None
    deleted: bool = False
    hidden: bool = False
    recurrence_pattern: GraphRecurrence | None = None


def task_evidence(raw: object, *, account: str, now: datetime, chars: int) -> DiscussionEvidence:
    """Project a task into planned evidence, or reported once its status says completed.

    A completed status is the provider's record, never proof the person did it.

    Args:
        raw: The provider record.
        account: The source account it came from.
        now: The read's clock.
        chars: The excerpt's length bound.

    Returns:
        The evidence.
    """
    record = TaskRecord.model_validate(raw)
    text = record.model_dump_json()
    due = CivilDate.fromisoformat(record.due[:10]) if record.due else None
    complete = record.status == "completed"
    return DiscussionEvidence(
        reference=provider_reference(SourceKey.TASKS, account, record.id),
        source=SourceKey.TASKS,
        source_account=account,
        object_id=record.id,
        version=semantic_version((text,)),
        observed_at=now,
        planned_date=due,
        assertion="reported" if complete else "planned",
        occurrence_state="reported_complete" if complete else "scheduled",
        category="task_record",
        native_recurrence=record.recurrence_pattern,
        usage_nuance=evidence_lines()["task_nuance"],
        excerpt=text[:chars],
        excerpt_truncated=len(text) > chars,
    )
