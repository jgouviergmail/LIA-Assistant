"""What the tasks routes take and answer (ADR-369).

A task's due date is a DAY on the wire, whatever the provider keeps
(``task_dates``); completion is a boolean. A change names what it changes: a
field left out is kept, ``due: null`` removes the date, as ``reminder`` and
``repeat`` remove theirs, and a change naming nothing is refused rather than
sent. Every listing answers one page and the token of the next (``None`` on
the last): a page cut at its ceiling is never shown as the whole list
(ADR-185).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from src.core.config import settings
from src.core.constants import (
    WORKBENCH_TASK_NOTES_MAX_CHARS,
    WORKBENCH_TASK_STEPS_MAX,
    WORKBENCH_TASK_TITLE_MAX_CHARS,
)
from src.domains.workbench.ids import OptionalProviderId, ProviderId
from src.domains.workbench.schemas.acts import ActOutcome
from src.domains.workbench.schemas.calendar import DayWindow

_TITLE = StringConstraints(
    strip_whitespace=True, min_length=1, max_length=WORKBENCH_TASK_TITLE_MAX_CHARS
)
_NOTES = StringConstraints(max_length=WORKBENCH_TASK_NOTES_MAX_CHARS)
Title = Annotated[str, _TITLE]
# The optional ones carry the constraint on ``str | None``: an Annotated wrapped
# in a union loses it (``test_annotated_metadata_guard``).
OptionalTitle = Annotated[str | None, _TITLE]
OptionalNotes = Annotated[str | None, _NOTES]

#: How much a task matters, To Do's three words.
TaskImportance = Literal["low", "normal", "high"]
#: The repetitions the screen writes.
TaskRepeat = Literal["daily", "weekly", "monthly", "yearly"]
#: What the screen reads: a pattern it has no word for stays ``custom``, and untouched.
TaskRepeatRead = Literal["daily", "weekly", "monthly", "yearly", "custom"]
#: A view across the lists, decided in the account's day.
TaskView = Literal["today", "overdue", "upcoming"]


class TaskList(BaseModel):
    """One list of tasks."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The provider's id of the list.")
    title: str = Field(description="Its name.")
    default: bool = Field(
        default=False, description="Whether it is the default chosen in the settings."
    )


class TaskListsPage(BaseModel):
    """One page of the account's task lists."""

    items: list[TaskList] = Field(description="The lists of this page.")
    next_page_token: str | None = Field(description="The next page's token; None on the last.")


class TaskStep(BaseModel):
    """One step of a task (To Do only)."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The provider's id of the step.")
    title: str = Field(description="What it says.")
    checked: bool = Field(description="Whether it is done.")


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
    steps: list[TaskStep] = Field(default_factory=list, description="Its steps (To Do only).")
    importance: TaskImportance | None = Field(
        default=None, description="How much it matters (To Do only)."
    )
    reminder: datetime | None = Field(default=None, description="When it reminds (To Do only).")
    repeat: TaskRepeatRead | None = Field(default=None, description="How it repeats (To Do only).")


class TasksPage(BaseModel):
    """One page of a list's tasks."""

    items: list[Task] = Field(description="The tasks of this page.")
    next_page_token: str | None = Field(description="The next page's token; None on the last.")


class DueTasksQuery(DayWindow):
    """The days a calendar shows: its dated tasks are asked over them."""


class TaskViewQuery(BaseModel):
    """A view across the lists."""

    model_config = ConfigDict(extra="forbid")

    view: TaskView = Field(description="What it gathers, in the account's day.")


class DueTask(BaseModel):
    """One open task with a date, as a calendar draws it."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The provider's id of the task.")
    list_id: str = Field(description="Its list.")
    title: str = Field(description="Its title (may be empty at the provider).")
    due: date = Field(description="The day it is due, in the account's calendar.")


class DueTasks(BaseModel):
    """The open tasks due over some days, from every list."""

    tasks: list[DueTask] = Field(description="Those read, the earliest first.")
    truncated: bool = Field(description="Whether a list, or lists, were read in part.")
    failed: list[str] = Field(description="The lists that could not be read.")


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
    steps: list[Title] = Field(
        default_factory=list,
        max_length=WORKBENCH_TASK_STEPS_MAX,
        description="The steps it starts with (To Do only, else refused).",
    )
    importance: TaskImportance | None = Field(
        default=None, description="How much it matters (To Do only, else refused)."
    )
    reminder: AwareDatetime | None = Field(
        default=None, description="When it reminds (To Do only, else refused)."
    )
    repeat: TaskRepeat | None = Field(
        default=None, description="How it repeats, from its due day (To Do only, else refused)."
    )
    idempotency_key: UUID = Field(description="One key per submission (a replay creates nothing).")

    @model_validator(mode="after")
    def _a_repetition_starts_on_a_day(self) -> Self:
        if self.repeat is not None and self.due is None:
            raise ValueError("a repetition starts on the task's due day")
        return self


class TaskChange(BaseModel):
    """What changes on one task: a field left out is kept."""

    model_config = ConfigDict(extra="forbid")

    list_id: ProviderId = Field(description="The task's list.")
    task_id: ProviderId = Field(description="The task.")
    title: OptionalTitle = Field(default=None, description="A new title.")
    notes: OptionalNotes = Field(default=None, description="New notes ('' empties them).")
    due: date | None = Field(default=None, description="A new day; null REMOVES the due date.")
    completed: bool | None = Field(default=None, description="Done, or not done.")
    importance: TaskImportance | None = Field(default=None, description="How much it matters.")
    reminder: AwareDatetime | None = Field(
        default=None, description="When it reminds; null REMOVES the reminder."
    )
    repeat: TaskRepeat | None = Field(
        default=None, description="How it repeats; null REMOVES the repetition."
    )

    @model_validator(mode="after")
    def _changes_something(self) -> Self:
        # A null title, notes, completion or importance keeps them; the others remove.
        kept = all(
            value is None for value in (self.title, self.notes, self.completed, self.importance)
        )
        if kept and not self.model_fields_set & {"due", "reminder", "repeat"}:
            raise ValueError("a change names at least one field")
        return self

    @property
    def removes_due(self) -> bool:
        """Whether ``due`` was sent as null — the date goes, rather than stays."""
        return "due" in self.model_fields_set and self.due is None

    @property
    def removes_reminder(self) -> bool:
        """Whether ``reminder`` was sent as null."""
        return "reminder" in self.model_fields_set and self.reminder is None

    @property
    def removes_repeat(self) -> bool:
        """Whether ``repeat`` was sent as null."""
        return "repeat" in self.model_fields_set and self.repeat is None

    @property
    def changes_details(self) -> bool:
        """Whether it touches what To Do alone keeps."""
        return self.importance is not None or bool(self.model_fields_set & {"reminder", "repeat"})


class TaskListRename(BaseModel):
    """A list's new name."""

    model_config = ConfigDict(extra="forbid")

    list_id: ProviderId = Field(description="The list.")
    title: Title = Field(description="Its new name.")


class TaskSelection(BaseModel):
    """The tasks of one list an act is about: one at least, the published bound at most."""

    model_config = ConfigDict(extra="forbid")

    list_id: ProviderId = Field(description="Their list.")
    task_ids: list[ProviderId] = Field(
        min_length=1,
        max_length=settings.workbench_bulk_max_items,
        description="The selection (at most the published bulk bound).",
    )


class TaskSelectionCompletion(TaskSelection):
    """A selection marked done or not done."""

    completed: bool = Field(description="True marks them done, False not done.")


class TaskSelectionMove(TaskSelection):
    """A selection sent to another list."""

    destination_list_id: ProviderId = Field(description="The list they go to.")

    @model_validator(mode="after")
    def _goes_somewhere(self) -> Self:
        if self.destination_list_id == self.list_id:
            raise ValueError("a move goes to another list")
        return self


class MovedTask(BaseModel):
    """What a task is called after a move."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Its id before the move.")
    new_id: str = Field(description="Its id now: To Do gives a copy another one.")


class TaskMoveOutcome(ActOutcome):
    """What a move did, and what each task moved is called from now on."""

    moved: list[MovedTask] = Field(description="The tasks moved, with their new ids.")


class TaskListClear(BaseModel):
    """The list whose done tasks go."""

    model_config = ConfigDict(extra="forbid")

    list_id: ProviderId = Field(description="The list.")


class TasksCleared(BaseModel):
    """What clearing a list's done tasks did."""

    deleted: int = Field(ge=0, description="The tasks deleted.")
    remaining: bool = Field(description="Whether the list still holds done tasks.")


class TaskPlacement(BaseModel):
    """Where a task goes among its siblings (Google only)."""

    model_config = ConfigDict(extra="forbid")

    list_id: ProviderId = Field(description="Its list.")
    task_id: ProviderId = Field(description="The task.")
    after: OptionalProviderId = Field(description="The sibling it follows; null puts it first.")


class NewTaskStep(BaseModel):
    """A step to add, once per submission (To Do only)."""

    model_config = ConfigDict(extra="forbid")

    list_id: ProviderId = Field(description="The task's list.")
    task_id: ProviderId = Field(description="The task.")
    title: Title = Field(description="What it says.")
    idempotency_key: UUID = Field(description="One key per submission (a replay creates nothing).")


class TaskStepChange(BaseModel):
    """What changes on one step: a field left out is kept."""

    model_config = ConfigDict(extra="forbid")

    list_id: ProviderId = Field(description="The task's list.")
    task_id: ProviderId = Field(description="The task.")
    step_id: ProviderId = Field(description="The step.")
    title: OptionalTitle = Field(default=None, description="What it says now.")
    checked: bool | None = Field(default=None, description="Done, or not done.")

    @model_validator(mode="after")
    def _changes_something(self) -> Self:
        if self.title is None and self.checked is None:
            raise ValueError("a change names at least one field")
        return self
