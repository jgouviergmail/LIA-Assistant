"""What the Gmail mailbox settings routes take and answer (ADR-369, Task 4.6).

The vacation responder in the person's own days — the last one INCLUDED —;
a filter as what it matches and what it does, in the words the assistant's
filter tool uses (a label added, archived, marked read). Nothing deletes a
filter: the client has no such act.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Final, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from src.domains.workbench.ids import OptionalProviderId
from src.domains.workbench.schemas.mail_compose import Body, Subject

#: How long a filter criterion may be (Gmail's own search box takes this much).
FILTER_CRITERION_MAX_CHARS: Final = 500

_CRITERION: Final = StringConstraints(
    min_length=1, max_length=FILTER_CRITERION_MAX_CHARS, pattern=r"^[^\x00-\x1f\x7f]+$"
)
OptionalCriterion = Annotated[str | None, _CRITERION]


class Vacation(BaseModel):
    """The vacation responder as it stands."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = Field(description="Whether it answers.")
    subject: str = Field(description="Its subject.")
    body: str = Field(description="Its text.")
    start_date: date | None = Field(description="The first day it answers (the person's).")
    end_date: date | None = Field(description="The last day it answers, included.")


class VacationChange(BaseModel):
    """The vacation responder set: on with its words and days, or off."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(description="Turn it on or off.")
    subject: Subject = Field(default="", description="Its subject (when on).")
    body: Body = Field(default="", description="Its text (when on).")
    start_date: date | None = Field(default=None, description="The first day (when on).")
    end_date: date | None = Field(default=None, description="The last day, included.")

    @model_validator(mode="after")
    def _a_period_ends_after_it_starts(self) -> Self:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("a period ends on or after the day it starts")
        return self


class MailFilter(BaseModel):
    """One Gmail filter: what it matches, what it does."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Gmail's filter id.")
    sender: str | None = Field(description="Messages from this.")
    recipient: str | None = Field(description="Messages to this.")
    subject: str | None = Field(description="Messages whose subject holds this.")
    query: str | None = Field(description="Messages a Gmail search matches.")
    has_attachment: bool = Field(description="Messages with an attachment only.")
    add_label_ids: list[str] = Field(description="Labels it adds.")
    archive: bool = Field(description="Whether it skips the inbox.")
    mark_read: bool = Field(description="Whether it marks them read.")
    forward: str | None = Field(description="Where it forwards them (set in Gmail).")


class MailFilters(BaseModel):
    """The mailbox's filters."""

    filters: list[MailFilter] = Field(description="As Gmail lists them.")


class NewFilter(BaseModel):
    """A filter created: one criterion at least, one action at least."""

    model_config = ConfigDict(extra="forbid")

    sender: OptionalCriterion = Field(default=None, description="Messages from this.")
    recipient: OptionalCriterion = Field(default=None, description="Messages to this.")
    subject: OptionalCriterion = Field(default=None, description="Subject holds this.")
    query: OptionalCriterion = Field(default=None, description="A Gmail search.")
    has_attachment: bool = Field(default=False, description="With an attachment only.")
    add_label_id: OptionalProviderId = Field(default=None, description="A label to add.")
    archive: bool = Field(default=False, description="Skip the inbox.")
    mark_read: bool = Field(default=False, description="Mark them read.")
    idempotency_key: UUID = Field(description="The page's key for this submission.")

    @model_validator(mode="after")
    def _matches_and_acts(self) -> Self:
        if not (self.sender or self.recipient or self.subject or self.query or self.has_attachment):
            raise ValueError("a filter matches something")
        if not (self.add_label_id or self.archive or self.mark_read):
            raise ValueError("a filter does something")
        return self
