"""A chat turn's state, attachments and archived request — prepared before any network wait.

The turn used to prepare the person's MCP servers inside its setup
transaction and before archiving their request. The preparation can wait on a
remote server for seconds (p95 19 s in production, spec 2026-10-21 §0ter), so
the pooled connection sat ``idle in transaction`` for the whole wait (ADR-304)
— and a deployment bounding that state failed the turn on its first statement
after it — while the person's own message reached their other tabs only once
the slowest server had answered.

This module holds everything the turn needs from the database before that
wait: the restored state, the attachments injected into it and the archived
request. The caller commits right after, THEN prepares the servers. Extracted
from ``AgentService._stream_with_new_services``, whose file is frozen.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextlib import aclosing, suppress
from contextvars import Token
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.core.card_composition import CardCompositionRequest
from src.core.config import settings
from src.domains.agents.api.archive_first import archive_user_message_first, turn_attachment_meta
from src.domains.agents.api.attachments_injection import inject_attachments_into_state
from src.domains.agents.api.run_origin import current_origin, plain_surface_ctx
from src.domains.agents.api.schemas import (
    ChatStreamChunk,
    MCPPreparationKey,
    MCPPreparationNotice,
)
from src.domains.agents.effects.decisions import note_request_message
from src.domains.agents.services.streaming.latency_sli import (
    a_person_is_waiting,
    observe_pre_graph_phase,
)
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.core.context import SkillContextTokens, UserMCPToolsContext
    from src.domains.agents.models import MessagesState
    from src.domains.agents.services.orchestration.service import OrchestrationService
    from src.domains.conversations.service import ConversationService
    from src.infrastructure.mcp.user_preparation import PreparationEvent

logger = get_logger(__name__)


@dataclass(frozen=True)
class TurnStateRequest:
    """What one turn asks of its state load, its attachments and its archived request.

    Attributes:
        conversation_id: The conversation (and checkpoint thread) of the turn.
        user_message: The person's request as they sent it.
        user_id: The account the turn runs for.
        session_id: The request's session identifier.
        run_id: The turn's run identifier, stamped on the archived row.
        user_timezone: The person's IANA timezone.
        user_language: The person's language code.
        oauth_scopes: The scopes of the account's active connectors.
        personality_instruction: The personality prompt instruction, if any.
        is_hitl_resumption: True when the request answers a pending interrupt.
        user_display_name: The person's display name, if known.
        hitl_decision: A structured one-click decision, if the request is one.
        attachment_ids: The attachments the request named.
        auto_approve_plan: Inert flag kept until a policy for unattended runs
            exists (ADR-323): the router resets it before any reader.
        archive_user_message: False when an earlier attempt already archived
            the request (scheduled-action retries).
        stt_kwargs: The dictation cost attribution of the archived row.
        is_automated_source: True for a run nobody typed (a routine).
        live_session_id: The live session the request was spoken in, if any.
        spoken_text: The person's transcribed words, kept beside the request.
        card_composition: The card composition the client requested.
    """

    conversation_id: uuid.UUID
    user_message: str
    user_id: uuid.UUID
    session_id: str
    run_id: str
    user_timezone: str
    user_language: str
    oauth_scopes: list[str]
    personality_instruction: str | None
    is_hitl_resumption: bool
    user_display_name: str | None
    hitl_decision: dict[str, Any] | None
    attachment_ids: list[uuid.UUID] | None
    auto_approve_plan: bool
    archive_user_message: bool
    stt_kwargs: Mapping[str, Any] = field(default_factory=dict)
    is_automated_source: bool = False
    live_session_id: str | None = None
    spoken_text: str | None = None
    card_composition: CardCompositionRequest | None = None


@dataclass(frozen=True)
class PreparedTurnState:
    """The turn's state, ready for the graph, and the id of its archived request.

    Attributes:
        state: The restored (or new) graph state, with the request and the
            attachments injected.
        archived_user_msg_id: The archived request's row id; None when the
            archive was skipped or failed (best-effort, ADR-117).
    """

    state: MessagesState
    archived_user_msg_id: uuid.UUID | None


async def prepare_turn_state(
    request: TurnStateRequest,
    *,
    graph: Any,
    db: AsyncSession,
    orchestration_service: OrchestrationService,
    conv_service: ConversationService,
) -> PreparedTurnState:
    """Load the turn's state, inject its attachments and archive its request.

    Args:
        request: What the turn asks for.
        graph: The compiled graph whose checkpoints hold the conversation.
        db: The turn's setup session (read by the attachments step); the
            caller commits it once this returns.
        orchestration_service: Loads or creates the state.
        conv_service: Archives the request.

    Returns:
        The prepared state and the archived request's id.

    Raises:
        HitlDecisionStaleError: A one-click decision no longer matches the
            pending interrupt; nothing was archived (fail-closed).
    """
    started = time.perf_counter()
    state = await orchestration_service.load_or_create_state(
        graph=graph,
        conversation_id=request.conversation_id,
        user_message=request.user_message,
        user_id=request.user_id,
        session_id=request.session_id,
        run_id=request.run_id,
        user_timezone=request.user_timezone,
        user_language=request.user_language,
        oauth_scopes=request.oauth_scopes,
        personality_instruction=request.personality_instruction,
        is_hitl_resumption=request.is_hitl_resumption,
        user_display_name=request.user_display_name,
        hitl_decision=request.hitl_decision,
    )
    # Attachments go into the loaded state, before the graph reads it (evolution F4).
    if request.attachment_ids and getattr(settings, "attachments_enabled", False):
        await inject_attachments_into_state(
            state=state,
            attachment_ids=request.attachment_ids,
            user_id=request.user_id,
            user_language=request.user_language,
            run_id=request.run_id,
            db=db,
        )
    if request.auto_approve_plan:
        state["plan_approved"] = True
        logger.info(
            "auto_approve_plan_injected", run_id=request.run_id, user_id=str(request.user_id)
        )
    archive_started = time.perf_counter()
    observe_pre_graph_phase("state", archive_started - started)

    archived_user_msg_id = await _archive_request(request, state, conv_service)
    observe_pre_graph_phase("archive", time.perf_counter() - archive_started)
    return PreparedTurnState(state=state, archived_user_msg_id=archived_user_msg_id)


async def _archive_request(
    request: TurnStateRequest, state: MessagesState, conv_service: ConversationService
) -> uuid.UUID | None:
    """Persist the request NOW, so it survives a disconnect or a crash (ADR-117).

    End-of-run HITL flags (``decision_type``, ``hitl_interrupted``) are patched
    onto this row during the turn's finalization.

    Args:
        request: What the turn asks for.
        state: The prepared state, whose attachments the row lists.
        conv_service: Archives the request.

    Returns:
        The archived row id, or None when skipped or failed.
    """
    if not request.archive_user_message:
        return None
    archived_user_msg_id = await archive_user_message_first(
        conv_service=conv_service,
        conversation_id=request.conversation_id,
        user_message=request.user_message,
        run_id=request.run_id,
        is_hitl_resumption=request.is_hitl_resumption,
        attachment_meta=turn_attachment_meta(state, request.attachment_ids),
        stt_kwargs=dict(request.stt_kwargs),
        is_automated_source=request.is_automated_source,
        live_session_id=request.live_session_id,
        spoken_text=request.spoken_text,
        card_composition=request.card_composition,
    )
    # POINT at what was asked; never copy it (ADR-263, lot 6).
    note_request_message(archived_user_msg_id)
    return archived_user_msg_id


#: The progress step's glyph, as the other execution steps carry theirs.
_PROGRESS_EMOJI = "🧩"

#: The phase that closes a slow server's notice, and the label it reads.
_TERMINAL_KEYS: dict[str, MCPPreparationKey] = {
    "ready": "chat.mcp_preparation.ready",
    "failed": "chat.mcp_preparation.failed",
    "timed_out": "chat.mcp_preparation.failed",
    "deferred": "chat.mcp_preparation.deferred",
}


@dataclass(frozen=True)
class PreparedUserMCP:
    """The personal servers' context, prepared — installed by the turn, in its own context."""

    context: UserMCPToolsContext | None

    def install(self) -> Token[UserMCPToolsContext | None] | None:
        """Install the context for the rest of the turn.

        Returns:
            The token ``cleanup_user_mcp_tools`` resets, or None when there is none.
        """
        from src.core.context import user_mcp_tools_ctx

        return None if self.context is None else user_mcp_tools_ctx.set(self.context)


def notices_reach_the_person(live_session_id: str | None) -> bool:
    """Whether a person watches this turn in the web chat (spec 2026-10-21 §5.6).

    No notice for a run nobody waits for, an out-of-turn run (a routine, a
    ticket, the phone), a channel rendering plain text, or the live voice.

    Args:
        live_session_id: The live session a voice-delegated turn belongs to.

    Returns:
        True when preparation notices may be streamed.
    """
    return (
        a_person_is_waiting()
        and current_origin() is None
        and not plain_surface_ctx.get()
        and live_session_id is None
    )


class _Notices:
    """One turn's notices: the generic step once, then each slow server and its outcome."""

    def __init__(self) -> None:
        self.announced = False
        self.slow: set[uuid.UUID] = set()

    def chunks_for(self, event: PreparationEvent) -> list[ChatStreamChunk]:
        if event.phase == "discovering" and not self.announced:
            self.announced = True
            return [_chunk(event, "mcp_preparation", generic=True)]
        if event.phase == "slow":
            self.slow.add(event.server_id)
            return [_chunk(event, "chat.mcp_preparation.slow")]
        key = _TERMINAL_KEYS.get(event.phase)
        if key is not None and event.server_id in self.slow:
            self.slow.discard(event.server_id)
            return [_chunk(event, key)]
        return []


def _chunk(
    event: PreparationEvent, key: MCPPreparationKey, *, generic: bool = False
) -> ChatStreamChunk:
    notice = MCPPreparationNotice(
        i18n_key=key,
        emoji=_PROGRESS_EMOJI if generic else None,
        server_key=None if generic else str(event.server_id),
        server_name=None if generic else event.server_name,
        phase=event.phase,
        elapsed_ms=round(event.elapsed_s * 1000),
    )
    return ChatStreamChunk(type="execution_step", content="", metadata=notice.model_dump())


async def iter_mcp_preparation(
    user_id: uuid.UUID, *, run_id: str, interactive: bool
) -> AsyncGenerator[ChatStreamChunk | PreparedUserMCP]:
    """Prepare the person's servers; stream what they wait for, then hand the context over.

    The preparation runs as a task of its own; this generator drains its events
    and yields them as notices, then yields the prepared context LAST, for the
    turn to install in its own context before the graph starts. Leaving early
    (the person went away) stops the wait; each server's own preparation keeps
    running and serves the next turn (spec 2026-10-21 §5.3).

    Args:
        user_id: The account.
        run_id: The turn's run, for the log.
        interactive: Whether notices reach a person (``notices_reach_the_person``).

    Yields:
        Notice chunks (only when interactive), then one ``PreparedUserMCP``.
    """
    from src.infrastructure.mcp import user_context

    if not interactive:
        yield PreparedUserMCP(await user_context.prepare_user_mcp_context(user_id))
        return
    events: asyncio.Queue[PreparationEvent] = asyncio.Queue()
    notices = _Notices()
    preparing = asyncio.create_task(
        user_context.prepare_user_mcp_context(user_id, on_event=events.put_nowait)
    )
    waiting: asyncio.Future[PreparationEvent] | None = None
    try:
        while not preparing.done():
            waiting = asyncio.ensure_future(events.get())
            await asyncio.wait({preparing, waiting}, return_when=asyncio.FIRST_COMPLETED)
            if waiting.done():
                for chunk in notices.chunks_for(waiting.result()):
                    yield chunk
        # The last read stops before the drain, so no event is taken twice or lost.
        await _stop(waiting)
        while not events.empty():
            for chunk in notices.chunks_for(events.get_nowait()):
                yield chunk
    finally:
        # Nothing this turn started may outlive it: the read of the next event,
        # and the build of a context nobody will install — both cancelled before
        # either is awaited, so a second cancellation leaves neither running.
        await _stop(waiting, preparing)
        if preparing.cancelled():
            logger.info("user_mcp_preparation_abandoned", run_id=run_id)
    yield PreparedUserMCP(preparing.result())


async def release_each(*closers: Callable[[], Awaitable[object]]) -> None:
    """Run every closer of a turn that ended early; one failing never skips the next.

    A turn the person left and a turn that failed both owe the same releases.

    Args:
        closers: The releases the turn owes (the voice coordinator, the pooled clients).
    """
    for close in closers:
        # best-effort: a failed close must not mask how the turn ended, nor skip the next one
        with suppress(Exception):
            await close()


async def _stop(*pending: asyncio.Future[Any] | None) -> None:
    """Cancel futures of this turn's and wait for them to settle.

    ``asyncio.wait`` never raises what the futures raise, so a cancellation of the
    TURN itself — the person left meanwhile — propagates instead of being swallowed.
    """
    running = {future for future in pending if future is not None and not future.done()}
    for future in running:
        future.cancel()
    if running:
        await asyncio.wait(running)


class MCPPreparation:
    """``iter_mcp_preparation`` as the turn consumes it: notices first, the context after.

    Args:
        user_id: The account.
        run_id: The turn's run.
        live_session_id: The live session a voice-delegated turn belongs to.
    """

    def __init__(self, user_id: uuid.UUID, *, run_id: str, live_session_id: str | None) -> None:
        self._items = iter_mcp_preparation(
            user_id, run_id=run_id, interactive=notices_reach_the_person(live_session_id)
        )
        self._prepared: PreparedUserMCP | None = None

    async def notices(self) -> AsyncGenerator[ChatStreamChunk]:
        """The notices to stream; the prepared context is kept for ``install``.

        Closed with its reader, in the reader's task: left to the loop's finalizer,
        the preparation's cleanup ran later, in another task (fresh review m2).
        """
        async with aclosing(self._items) as items:
            async for item in items:
                if isinstance(item, PreparedUserMCP):
                    self._prepared = item
                else:
                    yield item

    def install(self) -> Token[UserMCPToolsContext | None] | None:
        """Install the prepared context in the caller's context (after ``notices``)."""
        return None if self._prepared is None else self._prepared.install()


def reset_turn_scopes(
    *,
    user_mcp: Token[Any] | None,
    admin_mcp: Token[Any] | None,
    skills: SkillContextTokens | None,
    manifests: Token[Any] | None,
    directive: Token[Any],
    connectors: Token[Any],
) -> None:
    """Undo every request scope a turn installed, on each of its exits.

    The turn's end and its error path undid the same six scopes, each written
    out twice; one function keeps the two exits from drifting apart.

    Args:
        user_mcp: The personal MCP tools context.
        admin_mcp: The account's disabled administrator servers.
        skills: The active and third-party skill names.
        manifests: The turn's tool catalogue.
        directive: The capability directive.
        connectors: The account's active connector types.
    """
    from src.core.context import (
        active_connector_types_ctx,
        admin_mcp_disabled_ctx,
        capability_directive_ctx,
        request_tool_manifests_ctx,
        reset_skill_context,
    )
    from src.infrastructure.mcp.user_context import cleanup_user_mcp_tools

    cleanup_user_mcp_tools(user_mcp)
    if admin_mcp is not None:
        admin_mcp_disabled_ctx.reset(admin_mcp)
    if skills is not None:
        reset_skill_context(skills)
    if manifests is not None:
        request_tool_manifests_ctx.reset(manifests)
    capability_directive_ctx.reset(directive)
    active_connector_types_ctx.reset(connectors)
