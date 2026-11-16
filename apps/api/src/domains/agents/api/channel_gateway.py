"""Assistant-owned implementation injected into the channel boundary at startup."""

import asyncio
import re
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextlib import aclosing, asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis

from src.core.config import settings
from src.core.constants import CHANNEL_VOICE_REPLY_MAX_CHARS, CHANNEL_VOICE_REPLY_RUN_PREFIX
from src.core.conversation_execution import RunAdmission, RunEnd
from src.core.conversation_selection import ConversationSelection
from src.core.field_names import FIELD_ERROR_CODE
from src.core.i18n import resolve_language
from src.core.run_authority import current_run_authority
from src.core.stream_codes import RUN_STOPPED_ERROR_CODE
from src.domains.agents.api.hitl_pending import forget_question_of_run, hitl_stale_chunks
from src.domains.agents.api.internal_admission import internal_turn
from src.domains.agents.api.schemas import BrowserContext, BrowserGeolocation, ChatStreamChunk
from src.infrastructure.async_utils import cancel_and_join
from src.infrastructure.channels.assistant_gateway import (
    ChannelAgentRequest,
    ChannelAssistantGateway,
    ChannelStop,
    ChannelStreamChunk,
    GeoPoint,
)
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.streaming.run_stream_broker import clear_cancel, is_cancel_requested

logger = get_logger(__name__)

#: A link's address, which a voice would spell out: « (https://…) » after its
#: label, or bare. Linear by construction: a literal head, then one class run.
_URL_SPOKEN = re.compile(r" ?\(https?://[^\s)]*\)|https?://\S+")


async def _stream(request: ChannelAgentRequest) -> AsyncGenerator[ChannelStreamChunk]:
    from src.domains.agents.api.run_origin import plain_surface_ctx
    from src.domains.agents.api.service import AgentService
    from src.infrastructure.cache.redis import get_redis_cache

    token = plain_surface_ctx.set(True)
    try:
        async with internal_turn(
            request.user_id,
            selection=ConversationSelection(),
            language=request.user_language,
            run_id=None,
            answer_pending=True,
            cancellable=True,
        ) as prepared:
            if (
                request.original_run_id is not None
                and request.original_run_id != prepared.original_run_id
            ):
                _declare_end(RunEnd.UNSTARTED)
                for chunk in hitl_stale_chunks(request.user_language):
                    yield chunk
                return
            redis = await get_redis_cache()
            watch = _StopWatch(redis, prepared.admission.stream_id)
            failed = False
            try:
                async with (
                    watch.armed(),
                    aclosing(
                        AgentService().stream_chat_response(
                            user_message=request.user_message,
                            user_id=request.user_id,
                            session_id=request.session_id,
                            user_timezone=request.user_timezone,
                            user_language=request.user_language,
                            user_display_name=request.user_display_name,
                            original_run_id=prepared.original_run_id,
                            run_id=prepared.admission.run_id,
                            target=prepared.admission.target,
                            admission=prepared.admission,
                            user_memory_enabled=request.user_memory_enabled,
                            user_journals_enabled=request.user_journals_enabled,
                            user_psyche_enabled=request.user_psyche_enabled,
                            user_execution_mode=request.user_execution_mode,
                            hitl_decision=(
                                dict(request.hitl_decision)
                                if request.hitl_decision is not None
                                else None
                            ),
                            browser_context=_shared_position(request.position),
                            attachment_ids=list(request.attachment_ids) or None,
                        )
                    ) as stream,
                ):
                    async for chunk in stream:
                        failed |= chunk.type == "error"
                        yield chunk
            except asyncio.CancelledError:
                if not watch.honoured():
                    raise
                await _settle_stop(redis, prepared.admission)
                yield ChatStreamChunk(
                    type="error", content="", metadata={FIELD_ERROR_CODE: RUN_STOPPED_ERROR_CODE}
                )
                return
            _declare_end(RunEnd.INTERRUPTED if failed else RunEnd.NORMAL)
    finally:
        plain_surface_ctx.reset(token)


async def _speak(owner_id: UUID, language: str, answer: str) -> bytes | None:
    """An answer heard on a channel: its first sentences, as the chat's voice says them (lot 25).

    The words are the answer's plain text — no mark, and a link's label without
    its address — bounded, then read like the chat's voice comments (the same
    sentence cap) by the voice domain, under a run of its own: billed to the
    person, both ceilings asked before a paid engine speaks (ADR-272).

    Args:
        owner_id: The person.
        language: The person's language (the voice's).
        answer: The answer as Markdown, its cards already left out.

    Returns:
        The MP3, or None when the answer holds no words or a ceiling refused.

    Raises:
        Exception: A synthesis failure (the channel logs it: the text already left).
    """
    from src.core._exceptions_base import BaseAPIException
    from src.domains.agents.display.plain_text import markdown_to_plain_text
    from src.domains.voice.text_readout import synthesize_user_text

    words = _URL_SPOKEN.sub("", markdown_to_plain_text(answer))[:CHANNEL_VOICE_REPLY_MAX_CHARS]
    words = words.strip()
    if not words:
        return None
    try:
        readout = await synthesize_user_text(
            user_id=owner_id,
            user_language=language,
            text=words,
            max_sentences=settings.voice_chat_mode_max_sentences,
            run_prefix=CHANNEL_VOICE_REPLY_RUN_PREFIX,
        )
    except BaseAPIException as refused:
        logger.info(
            "channel_voice_reply_refused", user_id=str(owner_id), status=refused.status_code
        )
        return None
    return readout.audio


def _shared_position(position: GeoPoint | None) -> BrowserContext | None:
    """A position shared on a channel, as the turn's consented geolocation (lot 8).

    The person shared it for this message, as a browser shares its position
    with the chat: the location tools read it the same way, and it is
    remembered only under the person's own opt-in (``capture_location_fire_and_forget``).

    Args:
        position: The shared position, or None.

    Returns:
        The browser context carrying it, or None when nothing was shared.
    """
    if position is None:
        return None
    return BrowserContext(
        geolocation=BrowserGeolocation(
            lat=position.latitude, lon=position.longitude, accuracy=position.accuracy_m
        )
    )


@dataclass(slots=True)
class _StopWatch:
    """The stop signal the chat's Stop writes for ONE invocation, watched for its turn.

    The turn runs in the task that reads the channel's stream, so the watch
    cancels THAT task when the signal appears — once, and only for the
    invocation it names (``request_cancel`` keys on the stream, so a later
    turn is never stopped by an earlier signal).

    Attributes:
        redis: The cache client the signal is written to.
        stream_id: The invocation watched.
        fired: Whether this watch cancelled the turn.
    """

    redis: Redis
    stream_id: str
    fired: bool = False

    @asynccontextmanager
    async def armed(self) -> AsyncIterator[None]:
        """Watch while the turn runs; the poller is stopped and joined on every exit."""
        turn = asyncio.current_task()
        assert turn is not None
        poller = asyncio.create_task(self._poll(turn))
        try:
            yield
        finally:
            await cancel_and_join(poller)

    async def _poll(self, turn: asyncio.Task[object]) -> None:
        while True:
            await asyncio.sleep(settings.background_runs_cancel_poll_seconds)
            try:
                requested = await is_cancel_requested(self.redis, self.stream_id)
            except Exception as exc:  # noqa: BLE001 — an unreadable signal stops nothing
                logger.warning(
                    "channel_turn_stop_poll_failed",
                    stream_id=self.stream_id,
                    error_type=type(exc).__name__,
                )
                continue
            if requested:
                self.fired = True
                turn.cancel()
                return

    def honoured(self) -> bool:
        """Whether the cancellation being handled is this watch's, and the only one.

        Takes back this watch's cancellation request: a cancellation that is not
        a stop — a shutdown, a lost supervision — still propagates.
        """
        turn = asyncio.current_task()
        return self.fired and turn is not None and turn.uncancel() == 0


async def _settle_stop(redis: Redis, admission: RunAdmission) -> None:
    """Close a stopped turn: interrupted (ADR-384), its question and its signal forgotten.

    Best-effort for the two cleanups — a cache that fails leaves the question to
    expire and the signal to its TTL; the end is declared whatever happens.

    Args:
        redis: The cache client.
        admission: The stopped invocation.
    """
    _declare_end(RunEnd.INTERRUPTED)
    logger.info("channel_turn_stopped", stream_id=admission.stream_id)
    cleanups: tuple[tuple[Callable[[], Awaitable[object]], str], ...] = (
        (
            lambda: forget_question_of_run(admission, redis=redis),
            "channel_turn_question_cleanup_failed",
        ),
        (lambda: clear_cancel(redis, admission.stream_id), "channel_turn_stop_cleanup_failed"),
    )
    for cleanup, event in cleanups:
        try:
            await cleanup()
        except Exception as exc:  # noqa: BLE001 — a cleanup never re-opens the turn
            logger.warning(event, stream_id=admission.stream_id, error_type=type(exc).__name__)


def _declare_end(end: RunEnd) -> None:
    """Tell the admission this turn owns how it ended, before its close reads it (ADR-384)."""
    authority = current_run_authority()
    if authority is not None:
        authority.end = end


async def _pending(owner_id: UUID, conversation_id: str) -> dict[str, object] | None:
    """Read only the owner's current Main, after releasing the SQL session."""
    from src.domains.agents.utils.hitl_store import HITLStore
    from src.domains.conversations.repository import ConversationRepository
    from src.infrastructure.cache.redis import get_redis_cache
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        conversation = await ConversationRepository(db).get_active_for_user(owner_id)
        if conversation is None or str(conversation.id) != conversation_id:
            return None
        runtime_id = str(conversation.runtime_id)
    store = HITLStore(await get_redis_cache(), ttl_seconds=settings.hitl_pending_data_ttl_seconds)
    return await store.get_pending(runtime_id)


def _confirmation_text(language: str) -> str:
    from src.domains.agents.api.error_messages import SSEErrorMessages

    return SSEErrorMessages.confirmation_required(language=resolve_language(language))


async def _stop(owner_id: UUID) -> ChannelStop:
    """Stop the answer running in the person's Main, as the chat's Stop does.

    A channel speaks in Main: like an old tab, it never stops another
    discussion's work (ADR-378), nor a run reserved unstoppable (a routine).

    Args:
        owner_id: The person.

    Returns:
        Whether a stop was asked, nothing ran, or what runs cannot be stopped here.
    """
    from src.domains.agents.api.run_controls import cancel_selected
    from src.domains.conversations.execution_repository import ConversationExecutionRepository
    from src.infrastructure.database.session import get_db_context

    if (await cancel_selected(owner_id, ConversationSelection())).cancelled:
        return ChannelStop.STOPPING
    async with get_db_context() as db:
        active = await ConversationExecutionRepository(db).snapshot_for_owner(owner_id)
    return ChannelStop.NOTHING if active is None else ChannelStop.ELSEWHERE


def build_channel_gateway() -> ChannelAssistantGateway:
    from src.domains.agents.api.waiting_channel import act_on_waiting, keep_from_channel

    return ChannelAssistantGateway(
        stream=_stream,
        pending=_pending,
        confirmation_text=_confirmation_text,
        stop=_stop,
        keep=keep_from_channel,
        act_on_waiting=act_on_waiting,
        speak=_speak,
    )
