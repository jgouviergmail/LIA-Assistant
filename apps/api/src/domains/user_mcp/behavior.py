"""What a personal MCP server will do — computed by the rules a run applies (spec 2026-10-30 D5).

The page never describes a server in prose of its own: this module runs the same
resolution (``infrastructure/mcp/confirmation.py``), the same manifest builder
(``build_mcp_tool_manifest``) and the same predicates (``requires_confirmation``,
``react_drives_tools_directly``) a run uses, so what the page says and what a turn
does cannot drift apart.

The flows per execution mode are the facts the 2026-10-30 proof measured on full
turns (ledger, Task 0): directly driven tools ask in the ReAct loop, which continues,
and as a card after a Pipeline task, which the plan resumes from. A dedicated agent is
asked once before each task it is given, whenever one of its tools would ask, and that
answer covers the task's calls in both modes (owner decision 2026-10-31; the same
predicate as the run, ``task_requires_confirmation``). Whether a tool is asked about no
longer depends on the mode — only when: before the task, or before the call.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID

import structlog

from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.registry.confirmation_rule import (
    requires_confirmation,
    task_requires_confirmation,
)
from src.domains.user_mcp.behavior_schemas import (
    BehaviorNote,
    BehaviorPreview,
    BehaviorPreviewRequest,
    Driver,
    ExecutionMode,
    ModeBehavior,
    QuestionFlow,
    QuestionLoss,
    ServerBehavior,
    ServerConfirmationView,
    StrategyPreview,
    ToolBehavior,
)
from src.domains.user_mcp.models import UserMCPServer
from src.infrastructure.mcp.catalogue_snapshot import parse_catalogue_snapshot
from src.infrastructure.mcp.confirmation import (
    ConfirmationSource,
    ServerConfirmation,
    ServerToolConfirmations,
    StoredToolChoice,
    ToolChoice,
    ToolConfirmation,
    confirmation_reason,
    declaration_fingerprint,
    dedicated_agents_available,
    effective_react_expand,
    react_drives_tools_directly,
    resolve_server_confirmation,
)
from src.infrastructure.mcp.registration import build_mcp_tool_manifest
from src.infrastructure.mcp.utils import is_app_only

logger = structlog.get_logger(__name__)

#: The manifest's name decides nothing about confirmation; a constant keeps a name a
#: third party chose out of the builder (a run uses its own sanitised alias).
_SYNTHESIS_ADAPTER = "mcp_user_synthesis_tool"

__all__ = [
    "BehaviorInputs",
    "behavior_inputs",
    "catalogue_tool",
    "describe_server_behavior",
    "questions_lost",
    "server_preview",
    "strategy_preview",
    "with_candidates",
]


@dataclass(frozen=True)
class BehaviorInputs:
    """What the synthesis of one server reads: its choices and its last catalogue."""

    server_id: UUID
    server_name: str
    hitl_required: bool | None
    iterative_mode: bool
    react_expand_iterative: bool | None
    tools: tuple[Mapping[str, Any], ...]
    tool_choices: Mapping[str, StoredToolChoice] = field(default_factory=dict)


def behavior_inputs(
    server: UserMCPServer, tool_choices: Mapping[str, StoredToolChoice] | None = None
) -> BehaviorInputs:
    """The stored choices of a server and the tools a run would register.

    Args:
        server: The person's server row.
        tool_choices: The tools' own choices, as stored.

    Returns:
        The inputs; an app-only tool is left out, as a run leaves it out.
    """
    tools = tuple(
        tool
        for tool in parse_catalogue_snapshot(server.discovered_tools_cache).tools
        if not is_app_only(tool.get("app_visibility"))
    )
    return BehaviorInputs(
        server_id=server.id,
        server_name=server.name,
        hitl_required=server.hitl_required,
        iterative_mode=server.iterative_mode,
        react_expand_iterative=server.react_expand_iterative,
        tools=tools,
        tool_choices=tool_choices or {},
    )


def catalogue_tool(inputs: BehaviorInputs, tool_name: str) -> Mapping[str, Any] | None:
    """The tool of the server's last catalogue with this exact name, if it lists one."""
    return next((tool for tool in inputs.tools if tool.get("name") == tool_name), None)


def _candidate_choices(
    inputs: BehaviorInputs, candidates: Mapping[str, ToolChoice | None]
) -> dict[str, StoredToolChoice]:
    """The stored choices with the form's candidates applied to the tools it lists.

    A candidate binds to the declaration the catalogue lists now, as a save would; a
    tool the catalogue does not list is ignored, as a save would refuse it.
    """
    choices = dict(inputs.tool_choices)
    for name, choice in candidates.items():
        tool = catalogue_tool(inputs, name)
        if tool is None:
            continue
        if choice is None:
            choices.pop(name, None)
        else:
            choices[name] = StoredToolChoice(choice, declaration_fingerprint(tool))
    return choices


def with_candidates(inputs: BehaviorInputs, request: BehaviorPreviewRequest) -> BehaviorInputs:
    """The inputs as the form would leave them; absent fields keep their stored value.

    Args:
        inputs: The stored inputs.
        request: The form's candidate values (an explicit null is « back to default »).

    Returns:
        The candidate inputs.
    """
    sent = request.model_fields_set
    return replace(
        inputs,
        hitl_required=request.hitl_required if "hitl_required" in sent else inputs.hitl_required,
        iterative_mode=(
            request.iterative_mode if request.iterative_mode is not None else inputs.iterative_mode
        ),
        react_expand_iterative=(
            request.react_expand_iterative
            if "react_expand_iterative" in sent
            else inputs.react_expand_iterative
        ),
        tool_choices=_candidate_choices(inputs, request.tool_choices),
    )


def _mode(mode: ExecutionMode, *, dedicated: bool, task_asks: bool) -> ModeBehavior:
    """How a question comes in one mode, for one driver.

    A tool used directly is asked in the loop (ReAct) or on a card after the task
    (Pipeline, which then resumes) — Task 0 facts. A dedicated agent is asked once
    before each task it is given, whenever one of its tools would ask, and that answer
    covers its calls (owner decision 2026-10-31).
    """
    if dedicated:
        return ModeBehavior(driver=Driver.DEDICATED_AGENT, before_task=task_asks, per_call=None)
    direct_flow = (
        QuestionFlow.IN_LOOP if mode is ExecutionMode.REACT else QuestionFlow.CARD_AFTER_TASK
    )
    return ModeBehavior(driver=Driver.DIRECT, before_task=False, per_call=direct_flow)


def _manifest(tool: Mapping[str, Any], confirmation: ToolConfirmation) -> ToolManifest:
    """The manifest a run builds for this tool, under this confirmation."""
    name = str(tool.get("name", ""))
    return build_mcp_tool_manifest(
        adapter_name=_SYNTHESIS_ADAPTER,
        agent_name="mcp_synthesis_agent",
        tool_name=name,
        description=str(tool.get("description") or name),
        input_schema=tool.get("input_schema") or {},
        semantic_keywords=[],
        hitl_required=confirmation.hitl_required,
        annotations=tool.get("annotations"),
        output_schema=tool.get("output_schema"),
        mcp_origin="user",
        standing_approval=confirmation.standing_approval,
    )


def _notes(
    inputs: BehaviorInputs,
    confirmation: ServerConfirmation,
    account_value: bool | None,
    *,
    is_app: bool,
    suspended: bool,
) -> list[BehaviorNote]:
    notes: list[BehaviorNote] = []
    if not inputs.tools:
        notes.append(BehaviorNote.TOOLS_UNKNOWN)
    if is_app:
        notes.append(BehaviorNote.MCP_APP)
    if inputs.iterative_mode and not dedicated_agents_available():
        notes.append(BehaviorNote.DEDICATED_AGENTS_OFF)
    if (
        confirmation.source is ConfirmationSource.SERVER
        and isinstance(account_value, bool)
        and account_value != confirmation.always
    ):
        notes.append(BehaviorNote.SERVER_OVERRIDES_ACCOUNT)
    if suspended:
        notes.append(BehaviorNote.CHOICE_SUSPENDED)
    return notes


def describe_server_behavior(inputs: BehaviorInputs, account_value: bool | None) -> ServerBehavior:
    """What the server will do, mode by mode and tool by tool.

    Args:
        inputs: The server's choices and catalogue (stored or candidate).
        account_value: ``users.mcp_hitl_required`` (stored or candidate).

    Returns:
        The synthesis.
    """
    confirmation = resolve_server_confirmation(inputs.hitl_required, account_value)
    dedicated = inputs.iterative_mode and dedicated_agents_available()
    is_app = any(tool.get("app_resource_uri") for tool in inputs.tools)
    react_dedicated = dedicated and not react_drives_tools_directly(
        react_expand=effective_react_expand(inputs.react_expand_iterative),
        has_individuals=bool(inputs.tools),
        is_mcp_app=is_app,
    )
    choices = ServerToolConfirmations(confirmation.always, inputs.tool_choices)
    by_default = ServerToolConfirmations(confirmation.always, {})
    individuals: list[ToolManifest] = []
    tools: list[ToolBehavior] = []
    for tool in inputs.tools:
        own = choices.for_tool(tool)
        try:
            manifest = _manifest(tool, own)
            default_asks = requires_confirmation(_manifest(tool, by_default.for_tool(tool)))
        except Exception:
            # A tool a run cannot register is absent from the run: absent here too.
            logger.debug("mcp_behavior_tool_skipped", server_id=str(inputs.server_id))
            continue
        individuals.append(manifest)
        tools.append(
            _tool_behavior(tool, own, requires_confirmation(manifest), default_asks, confirmation)
        )
    # The run's own predicate decides whether a dedicated agent's task is asked.
    task_asks = task_requires_confirmation(individuals)
    pipeline = _mode(ExecutionMode.PIPELINE, dedicated=dedicated, task_asks=task_asks)
    react = _mode(ExecutionMode.REACT, dedicated=react_dedicated, task_asks=task_asks)
    return ServerBehavior(
        confirmation=ServerConfirmationView(always=confirmation.always, source=confirmation.source),
        pipeline=pipeline,
        react=react,
        tools=tools,
        unattended_refused=[
            # A routine cannot answer: a dedicated agent's task that asks is refused
            # whole unless it pre-approved the server; a direct tool, where it asks.
            t.tool_name
            for t in tools
            if t.asks or pipeline.before_task or react.before_task
        ],
        notes=_notes(
            inputs,
            confirmation,
            account_value,
            is_app=is_app,
            suspended=any(t.suspended for t in tools),
        ),
    )


def _tool_behavior(
    tool: Mapping[str, Any],
    own: ToolConfirmation,
    asks: bool,
    default_asks: bool,
    confirmation: ServerConfirmation,
) -> ToolBehavior:
    """One tool's line of the synthesis; its texts are a third party's, kept as text."""
    title, description = tool.get("title"), tool.get("description")
    return ToolBehavior(
        tool_name=str(tool.get("name", "")),
        title=title if isinstance(title, str) else None,
        description=description if isinstance(description, str) else None,
        asks=asks,
        reason=confirmation_reason(confirmation, tool.get("annotations"), own.choice),
        choice=own.choice,
        suspended=own.suspended,
        default_asks=default_asks,
    )


def questions_lost(
    inputs: BehaviorInputs, before: ServerBehavior, after: ServerBehavior
) -> list[QuestionLoss]:
    """The tools asked about under ``before`` and no longer under ``after``.

    Counted per tool — the person's oversight of each act. A question before a
    dedicated agent's task counts as asked: it covers the calls (owner decision
    2026-10-31), so whether a tool is asked no longer depends on the mode.

    Args:
        inputs: The server (its identity names the losses).
        before: The synthesis as things stand.
        after: The synthesis under the candidate change.

    Returns:
        One entry per tool that stops being asked about.
    """
    still = {tool.tool_name for tool in after.tools if tool.asks}
    return [
        QuestionLoss(
            server_id=inputs.server_id,
            server_name=inputs.server_name,
            tool_name=tool.tool_name,
        )
        for tool in before.tools
        if tool.asks and tool.tool_name not in still
    ]


def server_preview(
    stored: BehaviorInputs, account_value: bool | None, request: BehaviorPreviewRequest
) -> BehaviorPreview:
    """The synthesis under the form's candidate values, and the questions it loses.

    Args:
        stored: The server as stored, its tools' choices included.
        account_value: ``users.mcp_hitl_required`` as stored.
        request: The candidate values; nothing is written.

    Returns:
        The candidate synthesis and what LIA would stop asking about.
    """
    before = describe_server_behavior(stored, account_value)
    after = describe_server_behavior(with_candidates(stored, request), account_value)
    return BehaviorPreview(behavior=after, questions_lost=questions_lost(stored, before, after))


def strategy_preview(
    servers: Sequence[BehaviorInputs], stored: bool | None, candidate: bool | None
) -> StrategyPreview:
    """What a change of the account's strategy would stop LIA asking, server by server.

    Args:
        servers: Every server of the account as stored, its tools' choices included
            (a disabled one may be enabled later).
        stored: The account's strategy as stored.
        candidate: The candidate strategy (None: back to the instance default).

    Returns:
        Every (server, tool, mode) asked now and no longer under the candidate.
    """
    losses: list[QuestionLoss] = []
    for inputs in servers:
        losses.extend(
            questions_lost(
                inputs,
                describe_server_behavior(inputs, stored),
                describe_server_behavior(inputs, candidate),
            )
        )
    return StrategyPreview(questions_lost=losses)
