"""Cross-application selections: a proposal, never a provider or memory write."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from src.core.config import settings
from src.core.constants import TOOL_ASSIST_LANGUAGE_MAX_CHARS
from src.core.external_content import wrap_external_content
from src.core.i18n import get_language_name
from src.core.i18n_selection import quoted_selection
from src.core.time_utils import resolve_user_timezone
from src.domains.agents.prompts import load_prompt
from src.domains.feature_switches.guard import require_capability
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.memories.schemas import MemoryCreate
from src.domains.tool_assists import actions
from src.domains.tool_assists import selection_records as records
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.llm import ask_slot
from src.domains.tool_assists.passage import PassageAct, PassageOrigin, act_on_passage
from src.domains.tool_assists.selection_research import (
    ResearchProposal,
    assert_research_providers_complete,
    research_selection,
)
from src.domains.tool_assists.text import RewriteTone, rewrite_text, translate_text
from src.domains.users.models import User
from src.domains.workbench.availability import read_availability
from src.domains.workbench.errors import ASSIST_NOT_FOUND, NOT_CONNECTED, refuse


class SelectionAction(str, Enum):
    """The model-backed reading and writing acts; speech and chat keep their own doors."""

    EXPLAIN = "explain"
    SIMPLIFY = "simplify"
    TRANSLATE = "translate"
    ASK = "ask"
    TASK = "task"
    EVENT = "event"
    MEMORY = "memory"
    FIX = "fix"
    SHORTER = "shorter"
    FORMAL = "formal"
    WARM = "warm"
    FORMAT = "format"
    INTERNET = "internet"
    SUMMARIZE = "summarize"
    REMINDER = "reminder"
    TICKET = "ticket"


READ_ACTIONS = frozenset(
    {
        SelectionAction.EXPLAIN,
        SelectionAction.SIMPLIFY,
        SelectionAction.TRANSLATE,
        SelectionAction.ASK,
        SelectionAction.TASK,
        SelectionAction.EVENT,
        SelectionAction.MEMORY,
        SelectionAction.INTERNET,
        SelectionAction.SUMMARIZE,
        SelectionAction.REMINDER,
        SelectionAction.TICKET,
    }
)
EDIT_ACTIONS = frozenset(
    {
        SelectionAction.FIX,
        SelectionAction.SHORTER,
        SelectionAction.FORMAL,
        SelectionAction.WARM,
        SelectionAction.FORMAT,
        SelectionAction.TRANSLATE,
    }
)
SelectionWords = Annotated[
    str,
    StringConstraints(min_length=1, max_length=settings.tool_assist_text_max_chars),
]


def assert_selection_actions_complete() -> None:
    """Refuse a new action that neither mode offers or an unintended overlap."""
    assert READ_ACTIONS | EDIT_ACTIONS == set(SelectionAction), "Selection actions are incomplete"
    assert READ_ACTIONS & EDIT_ACTIONS == {SelectionAction.TRANSLATE}, "Selection modes disagree"
    assert_research_providers_complete()


class SelectionRequest(BaseModel):
    """A bounded snapshot supplied by the person, carrying no server authority."""

    model_config = ConfigDict(extra="forbid")
    mode: Literal["read", "edit"] = Field(description="Whether the selected surface is editable.")
    action: SelectionAction = Field(description="The one action explicitly chosen.")
    text: SelectionWords = Field(description="The complete selected text; never silently cut.")
    origin: PassageOrigin = Field(
        default="page", description="Informational source, never authorization."
    )
    question: str | None = Field(
        default=None,
        min_length=1,
        max_length=settings.tool_assist_instruction_max_chars,
        description="The person's question, for ask alone.",
    )
    target_language: str | None = Field(
        default=None,
        min_length=2,
        max_length=TOOL_ASSIST_LANGUAGE_MAX_CHARS,
        description="The language explicitly chosen by the person, for translation alone.",
    )

    @model_validator(mode="after")
    def consistent_action(self) -> Self:
        """Reject mode confusion and unused/empty questions before spending."""
        if not self.text.strip():
            raise ValueError("Selection has no text")
        allowed = READ_ACTIONS if self.mode == "read" else EDIT_ACTIONS
        if self.action not in allowed:
            raise ValueError("Action is not offered in this selection mode")
        if (self.action is SelectionAction.ASK) != bool(self.question and self.question.strip()):
            raise ValueError("Only ask requires a nonempty question")
        if self.action is not SelectionAction.ASK and self.question is not None:
            raise ValueError("Question is only valid for ask")
        if self.action is SelectionAction.TRANSLATE:
            if self.target_language is None or len(self.target_language.strip()) < 2:
                raise ValueError("Translation requires an explicit language")
            self.target_language = self.target_language.strip()
        elif self.target_language is not None:
            raise ValueError("Target language is only valid for translation")
        return self


class TextProposal(BaseModel):
    kind: Literal["text"] = Field(default="text", description="A local answer or replacement.")
    text: str = Field(description="The proposed words.")


class TaskProposal(BaseModel):
    kind: Literal["task"] = Field(default="task", description="A task creation form.")
    task: actions.ProposedTask = Field(description="Proposed task fields.")


class EventProposal(BaseModel):
    kind: Literal["event"] = Field(default="event", description="An event creation form.")
    event: actions.ProposedEvent = Field(description="Proposed event fields.")


class MemoryProposal(BaseModel):
    kind: Literal["memory"] = Field(default="memory", description="A memory creation form.")
    memory: MemoryCreate = Field(description="Quoted content, to be reviewed before saving.")


SelectionProposal = Annotated[
    TextProposal
    | TaskProposal
    | EventProposal
    | MemoryProposal
    | ResearchProposal
    | records.ReminderProposal
    | records.TicketProposal,
    Field(discriminator="kind"),
]


class MemoryProposalDraft(MemoryCreate):
    """An attributable fact, with a literal witness in the selected passage."""

    evidence: SelectionWords = Field(description="An exact nonblank quotation supporting the fact.")
    found: bool = Field(default=True, description="A meaningful fact can be proposed.")


def admitted_memory(
    draft: MemoryProposalDraft, source: str, language: str | None = None
) -> MemoryCreate:
    """Keep the third-party attribution even if the model speaks in first person."""
    if not draft.found or not draft.evidence.strip() or draft.evidence not in source:
        refuse(ASSIST_NOT_FOUND)
    data = draft.model_dump(include=set(MemoryCreate.model_fields))
    data["content"] = quoted_selection(draft.content, language)
    # A selected instruction is a quotation, never an automatically pinned mandate.
    if draft.category == "procedural":
        data["category"] = "personal"
    return MemoryCreate.model_validate(data)


SelectionDestination = Literal["task", "event", "memory", "reminder", "ticket"]


async def offered_destinations(user_id: UUID) -> list[SelectionDestination]:
    """Read connection metadata only; opening a menu reads no personal content."""
    offered: list[SelectionDestination] = []
    if await is_capability_enabled(PlatformCapability.WORKBENCH):
        availability = await read_availability(user_id)
        ready = {item.tool.value for item in availability.tools if item.state == "ready"}
        if "tasks" in ready:
            offered.append("task")
        if "calendar" in ready:
            offered.append("event")
    if await is_capability_enabled(PlatformCapability.MEMORY):
        offered.append("memory")
    offered.append("reminder")
    if await is_capability_enabled(PlatformCapability.WORKBOARD):
        offered.append("ticket")
    return offered


async def require_destination(user_id: UUID, action: SelectionAction) -> None:
    """Recheck at the request; stale UI metadata confers no authority."""
    if action is SelectionAction.MEMORY:
        await require_capability(PlatformCapability.MEMORY)()
    elif action is SelectionAction.TICKET:
        await require_capability(PlatformCapability.WORKBOARD)()
    elif action in {SelectionAction.TASK, SelectionAction.EVENT}:
        await require_capability(PlatformCapability.WORKBENCH)()
        if action.value not in await offered_destinations(user_id):
            refuse(NOT_CONNECTED)


async def propose_selection(
    run: AssistRun, request: SelectionRequest, user: User
) -> SelectionProposal:
    """Run one existing assist or read one memory proposal under the common accountant."""
    await require_destination(user.id, request.action)
    if request.action is SelectionAction.INTERNET:
        return await research_selection(run, request.text)
    external = wrap_external_content(
        request.text, source_url=f"selection:{request.origin}", source_type="selection"
    )
    if request.target_language is not None:
        return TextProposal(text=await translate_text(run, external, request.target_language))
    if request.action.value in {tone.value for tone in RewriteTone}:
        return TextProposal(
            text=await rewrite_text(run, external, RewriteTone(request.action.value))
        )
    if request.action in {
        SelectionAction.EXPLAIN,
        SelectionAction.SIMPLIFY,
        SelectionAction.ASK,
        SelectionAction.SUMMARIZE,
    }:
        return TextProposal(
            text=await act_on_passage(
                run,
                request.text,
                PassageAct(request.action.value),
                request.question,
                origin=request.origin,
            )
        )
    if request.action in {SelectionAction.REMINDER, SelectionAction.TICKET}:
        kind: Literal["reminder", "ticket"] = (
            "reminder" if request.action is SelectionAction.REMINDER else "ticket"
        )
        return await records.propose_record(run, external, user, kind)
    zone = resolve_user_timezone(user)
    clock = actions.AssistClock(today=datetime.now(zone).date(), zone=str(zone))
    if request.action is SelectionAction.TASK:
        return TaskProposal(task=await actions.task_from_sentence(run, external, clock, []))
    if request.action is SelectionAction.EVENT:
        return EventProposal(event=await actions.event_from_sentence(run, external, clock))
    prompt = load_prompt("tool_assist_memory_prompt").format(
        language=get_language_name(run.language),
        content_max_chars=settings.memory_content_max_chars
        - len(quoted_selection("", run.language)),
        source=external,
    )
    draft = await ask_slot(run, prompt, MemoryProposalDraft)
    return MemoryProposal(memory=admitted_memory(draft, request.text, run.language))
