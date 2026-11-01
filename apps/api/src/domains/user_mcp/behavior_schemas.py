"""What a personal MCP server will do, as the API states it (spec 2026-10-30 D5).

Closed vocabularies only: every value is a code the page translates in six languages
(a completeness test reads the locales), never a sentence written here. A tool's name
is a third party's text: the page renders it as text, never as markup.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from src.core.constants import MCP_TOOL_CHOICE_NAME_MAX_LENGTH
from src.infrastructure.mcp.confirmation import (
    ConfirmationReason,
    ConfirmationSource,
    ToolChoice,
)


class Driver(StrEnum):
    """Who drives the server's tools in one execution mode."""

    DIRECT = "direct"
    DEDICATED_AGENT = "dedicated_agent"


class QuestionFlow(StrEnum):
    """How a call LIA uses directly is asked, in one execution mode (Task 0 facts).

    A dedicated agent has none: it is asked once before its task, and that answer
    covers its calls (owner decision 2026-10-31).
    """

    IN_LOOP = "in_loop"  # asked in the loop, which then continues
    CARD_AFTER_TASK = "card_after_task"  # a card after the task; the plan resumes


class BehaviorNote(StrEnum):
    """A fact about the server the page states beside its synthesis."""

    TOOLS_UNKNOWN = "tools_unknown"
    MCP_APP = "mcp_app"
    DEDICATED_AGENTS_OFF = "dedicated_agents_off"
    SERVER_OVERRIDES_ACCOUNT = "server_overrides_account"
    CHOICE_SUSPENDED = "choice_suspended"


class ExecutionMode(StrEnum):
    """The two execution modes a person switches between in the chat."""

    PIPELINE = "pipeline"
    REACT = "react"


class ModeBehavior(BaseModel):
    """What the server does in one execution mode."""

    driver: Driver = Field(description="Who drives the server's tools")
    before_task: bool = Field(
        description=(
            "True when the dedicated agent is asked before each task it is given (one "
            "of its tools would ask); that answer covers its calls"
        )
    )
    per_call: QuestionFlow | None = Field(
        description=(
            "How a call LIA uses directly is asked in this mode; null for a dedicated "
            "agent, whose task is asked instead"
        )
    )


class ToolBehavior(BaseModel):
    """What LIA does before one tool's call."""

    tool_name: str = Field(description="The tool's name, as the server declares it (text)")
    title: str | None = Field(description="The display name the server declares, if any")
    description: str | None = Field(description="What the server says the tool does (text)")
    asks: bool = Field(
        description=(
            "LIA asks before this call, in both modes — before the task for a dedicated "
            "agent, before the call otherwise"
        )
    )
    reason: ConfirmationReason = Field(description="Why, as a closed code")
    choice: ToolChoice | None = Field(
        description="The person's choice for this tool that applies; null: the levels below"
    )
    suspended: bool = Field(
        description="A « never » made against another declaration: it does not apply"
    )
    default_asks: bool = Field(
        description="Whether LIA would ask before this call without a choice of its own"
    )


class ServerConfirmationView(BaseModel):
    """The server's resolved confirmation and the level that decided it."""

    always: bool = Field(description="True asks before every call, reads included")
    source: ConfirmationSource = Field(description="The level whose value decided")


class ServerBehavior(BaseModel):
    """What a personal MCP server will do (spec 2026-10-30 D5)."""

    confirmation: ServerConfirmationView
    pipeline: ModeBehavior
    react: ModeBehavior
    tools: list[ToolBehavior] = Field(
        description="Tool by tool, from the last catalogue LIA read for the server"
    )
    unattended_refused: list[str] = Field(
        description=(
            "Tools a routine is refused unless it pre-approved this server — all of them "
            "when a dedicated agent's task asks; a ticket asks on the ticket instead"
        )
    )
    notes: list[BehaviorNote] = Field(description="Facts the page states beside the synthesis")


class QuestionLoss(BaseModel):
    """A tool LIA asks about now and would no longer ask about after a change."""

    server_id: UUID
    server_name: str = Field(description="The server's name (text)")
    tool_name: str = Field(description="The tool's name, as the server declares it (text)")


class BehaviorPreviewRequest(BaseModel):
    """Candidate values of the server's form; nothing is written.

    Absent means « as stored »; for the two tri-state values, an explicit null means
    « back to the default ». A tool absent from ``tool_choices`` keeps its stored
    choice; one mapped to null returns to the levels below.
    """

    hitl_required: bool | None = Field(default=None, strict=True)
    iterative_mode: bool | None = Field(default=None, strict=True)
    react_expand_iterative: bool | None = Field(default=None, strict=True)
    tool_choices: dict[str, ToolChoice | None] = Field(
        default_factory=dict,
        description="Candidate choices by tool name; null returns a tool to the levels below",
    )


class ToolConfirmationRequest(BaseModel):
    """The person's choice for one tool of a server (spec 2026-10-30 D6).

    ``choice`` is required: an explicit null returns the tool to the levels below, so
    a missing field never clears a choice by accident.
    """

    tool_name: str = Field(
        min_length=1,
        max_length=MCP_TOOL_CHOICE_NAME_MAX_LENGTH,
        description="The tool's raw name, as the server's last catalogue lists it",
    )
    choice: ToolChoice | None = Field(
        description="always or never; null returns the tool to the levels below"
    )


class BehaviorPreview(BaseModel):
    """The synthesis under candidate values, and what LIA would stop asking about."""

    behavior: ServerBehavior
    questions_lost: list[QuestionLoss]


class StrategyPreviewRequest(BaseModel):
    """A candidate account strategy; null returns the account to the instance default."""

    mcp_hitl_required: bool | None = Field(strict=True)


class StrategyPreview(BaseModel):
    """What LIA would stop asking about across the person's servers."""

    questions_lost: list[QuestionLoss]
