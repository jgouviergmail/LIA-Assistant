"""What the tasks routes take and answer (ADR-369).

A task's due date is a DAY on the wire, whatever the provider keeps
(``task_dates``); completion is a boolean. A change names what it changes: a
field left out is kept, ``due: null`` removes the date, and a change naming
nothing is refused rather than sent. Every listing answers one page and the
token of the next (``None`` on the last): a page cut at its ceiling is never
shown as the whole list (ADR-185).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from src.core.constants import WORKBENCH_TASK_NOTES_MAX_CHARS, WORKBENCH_TASK_TITLE_MAX_CHARS
from src.domains.workbench.ids import OptionalProviderId, ProviderId

_TITLE = StringConstraints(
    strip_whitespace=True, min_length=1, max_length=WORKBENCH_TASK_TITLE_MAX_CHARS
)
_NOTES = StringConstraints(max_length=WORKBENCH_TASK_NOTES_MAX_CHARS)
Title = Annotated[str, _TITLE]
# The optional ones carry the constraint on ``str | None``: an Annotated wrapped
# in a union loses it (``test_annotated_metadata_guard``).
OptionalTitle = Annotated[str | None, _TITLE]
OptionalNotes = Annotated[str | None, _NOTES]


class TaskList(BaseModel):
    """One list of tasks."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The provider's id of the list.")
    title: str = Field(description="Its name.")


class TaskListsPage(BaseModel):
    """One page of the account's task lists."""

    items: list[TaskList] = Field(description="The lists of this page.")
    next_page_token: str | None = Field(description="The next page's token; None on the last.")


class Task(BaseModel):
    """One task, in the section's vocabulary."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The provider's id of the task.")
    title: str = Field(description="Its title (may be empty at the provider).")
    notes: str | None = Field(description="Its notes, as plain text.")
    completed: bool = Field(description="Whether it is done.")
    due: date | None = Field(description="The day it is due, in the account's calendar.")
    parent: str | None = Field(description="The task it is a subtask of (Google only).")
    position: str | None = Field(description="Its order among its siblings (Google only).")


class TasksPage(BaseModel):
    """One page of a list's tasks."""

    items: list[Task] = Field(description="The tasks of this page.")
    next_page_token: str | None = Field(description="The next page's token; None on the last.")


class NewTaskList(BaseModel):
    """A list to create, once per submission."""

    model_config = ConfigDict(extra="forbid")

    title: Title = Field(description="Its name.")
    idempotency_key: UUID = Field(description="One key per submission (a replay creates nothing).")


class NewTask(BaseModel):
    """A task to create, once per submission."""

    model_config = ConfigDict(extra="forbid")

    list_id: ProviderId = Field(description="The list it goes in.")
    title: Title = Field(description="Its title.")
    notes: OptionalNotes = Field(default=None, description="Its notes.")
    due: date | None = Field(default=None, description="The day it is due.")
    parent: OptionalProviderId = Field(
        default=None, description="The task it is a subtask of (Google only, else refused)."
    )
    idempotency_key: UUID = Field(description="One key per submission (a replay creates nothing).")


class TaskChange(BaseModel):
    """What changes on one task: a field left out is kept."""

    model_config = ConfigDict(extra="forbid")

    list_id: ProviderId = Field(description="The task's list.")
    task_id: ProviderId = Field(description="The task.")
    title: OptionalTitle = Field(default=None, description="A new title.")
    notes: OptionalNotes = Field(default=None, description="New notes ('' empties them).")
    due: date | None = Field(default=None, description="A new day; null REMOVES the due date.")
    completed: bool | None = Field(default=None, description="Done, or not done.")

    @model_validator(mode="after")
    def _changes_something(self) -> Self:
        # A null title, notes or completion keeps them; only a null due removes.
        kept = all(value is None for value in (self.title, self.notes, self.completed))
        if kept and "due" not in self.model_fields_set:
            raise ValueError("a change names at least one field")
        return self

    @property
    def removes_due(self) -> bool:
        """Whether ``due`` was sent as null — the date goes, rather than stays."""
        return "due" in self.model_fields_set and self.due is None
