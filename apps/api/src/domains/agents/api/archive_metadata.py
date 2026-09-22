"""What an archived message carries beyond its text.

Four enrichers used to be applied inline in ``api/service.py``: widgets, the
execution trace, the follow-up chips and the initiative motivation. ADR-263
adds a fifth — the effects the turn actually performed — and that file sits
three logical lines under its frozen size cap, so the chain moved here instead
of growing it. The extraction is characterised by
``tests/unit/domains/agents/api/test_archive_metadata.py``, written against the
inline version before the move.

Two properties every enricher already had, and this chain keeps:

- **branch-free**: each one decides for itself whether it has anything to
  attach, so the archive path holds no conditionals;
- **new dict**: none of them mutates its input, so one turn's metadata can
  never leak into another's.

**Every row a TURN archives is built here**, and that is the point rather than
tidiness: a turn archives up to three rows — the question, the answer, and, when
it stops on a HITL interrupt, the question LIA asked instead of answering — and
the out-of-turn stamp (ADR-276) must reach ALL of them or the chat shows half a
run. Measured 2026-09-09 on the dev account: the HITL question was assembled as
a dict literal at its call site, so a workboard run that stopped on a
confirmation put its full draft preview in the person's chat as an ordinary
assistant message, AND left a row the retention sweep can never purge (it
matches on ``hidden`` AND the stamp). That path had been unreachable until lot 7
let a ticket run ask a question at all. ``build_*_metadata`` is therefore the
one door, and ``test_archive_rows_are_stamped_guard.py`` refuses an inline dict
at any archive call site of this package.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import structlog

from src.core.config import settings
from src.core.constants import LIVE_SESSION_SUMMARY_MESSAGE_TYPE, LIVE_TURN_MESSAGE_TYPE
from src.core.field_names import (
    FIELD_LIVE_SESSION_ID,
    FIELD_LIVE_SUMMARY,
    FIELD_RUN_ID,
    FIELD_SPOKEN_TEXT,
)
from src.domains.agents.api.run_origin import with_origin_stamp
from src.domains.agents.data_registry.message_widgets import with_persisted_widgets
from src.domains.agents.expressivity.activity_summary import ActivitySnapshot
from src.domains.agents.services.streaming.followup_metadata import (
    with_followup_suggestions,
    with_initiative_motivation,
)
from src.domains.agents.services.streaming.trace_capture import with_persisted_trace
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

#: Message-metadata key carrying what the turn actually did (ADR-263). Absent
#: when nothing was performed — the pure-conversation common case.
FIELD_PERFORMED_EFFECTS = "performed_effects"


def with_live_stamp(
    message_metadata: dict[str, Any], live_session_id: str | None, spoken_text: str | None
) -> dict[str, Any]:
    """Attach the live session a delegated turn was spoken in (ADR-299).

    Args:
        message_metadata: Metadata being assembled for the user message.
        live_session_id: The session, or None outside the live mode.
        spoken_text: The person's transcribed words, kept beside the request
            the voice model wrote from them.

    Returns:
        The input unchanged (same object) outside a live session, otherwise a
        NEW dict carrying the session and, when there is one, the transcription.
    """
    if not live_session_id:
        return message_metadata
    stamped = {**message_metadata, FIELD_LIVE_SESSION_ID: live_session_id}
    if spoken_text:
        stamped[FIELD_SPOKEN_TEXT] = spoken_text
    return stamped


def with_performed_effects(
    message_metadata: dict[str, Any], effects: list[dict[str, Any]] | None
) -> dict[str, Any]:
    """Attach what the turn performed, as keys and values (ADR-263).

    The entries carry a ``label_key`` and its ``values``, never a sentence:
    the frontend resolves them in the reader's current language, so a message
    archived in French still reads in English after the user switches. That is
    the same contract the execution trace already follows.

    Args:
        message_metadata: Metadata being assembled for the assistant message.
        effects: Effects of this run, already shaped for display. Empty or
            ``None`` attaches nothing.

    Returns:
        The input unchanged (same object) when there is nothing to attach,
        otherwise a NEW dict carrying the effects.
    """
    if not effects:
        return message_metadata
    return {**message_metadata, FIELD_PERFORMED_EFFECTS: effects}


def with_companion_metadata(
    metadata: dict[str, Any], expressivity: object, activity: ActivitySnapshot | None
) -> dict[str, Any]:
    """Archive passive evidence; loading it never replays a performance."""
    return {
        **metadata,
        **({"expressivity": expressivity} if expressivity is not None else {}),
        **({"companion_activity": activity} if activity is not None else {}),
    }


def build_assistant_metadata(
    message_metadata: dict[str, Any],
    *,
    widgets: Any,
    trace_capture: Any,
    duration_ms: int,
    run_id: str,
    followup_suggestions: Any,
    initiative_motivation: Any,
    effects: list[dict[str, Any]] | None,
    expressivity: object = None,
    activity: ActivitySnapshot | None = None,
) -> dict[str, Any]:
    """Apply every metadata enricher, in the order the archive path used.

    Args:
        message_metadata: The metadata assembled so far.
        widgets: Persistable widgets captured by the streaming service.
        trace_capture: The turn's ``TraceCapture`` (only ``snapshot()`` is read).
        duration_ms: Wall-clock duration of the turn.
        run_id: Correlates the emitted logs with the rest of the turn.
        followup_suggestions: Tappable follow-up chips, when any.
        initiative_motivation: Provenance line of a proactive turn, when any.
        effects: What the turn performed (ADR-263), when anything.

    Returns:
        The metadata to archive with the assistant message.
    """
    metadata = with_persisted_widgets(message_metadata, widgets, run_id=run_id)
    metadata = with_persisted_trace(
        metadata, trace_capture.snapshot(), duration_ms=duration_ms, run_id=run_id
    )
    metadata = with_followup_suggestions(metadata, followup_suggestions)
    metadata = with_initiative_motivation(metadata, initiative_motivation)
    metadata = with_performed_effects(metadata, effects)
    metadata = with_companion_metadata(metadata, expressivity, activity)
    # ADR-276: an out-of-turn run archives its rows exactly like any turn — the
    # decision register points at them — and it is the READ that keeps them out
    # of the chat. Branch-free like every enricher beside it: the stamp decides
    # for itself whether a run is driving.
    return with_origin_stamp(metadata)


def build_hitl_question_metadata(*, run_id: str, intention: str | None) -> dict[str, Any]:
    """What the question a turn asked instead of answering carries.

    A turn that stops on a HITL interrupt archives the QUESTION as its
    assistant row, so the conversation reads correctly on reload. It is a row
    of the turn like the other two, so it carries the run's stamp — and an
    out-of-turn run's question therefore stays out of the chat, where nobody
    could answer it anyway: the person answers on the ticket (ADR-276 lot 7).

    Args:
        run_id: The turn, shared with the three ADR-263 registers.
        intention: The turn's classified intention, when one was resolved.

    Returns:
        The metadata to archive with the question.
    """
    return with_origin_stamp({FIELD_RUN_ID: run_id, "hitl_question": True, "intention": intention})


def build_live_turn_metadata(
    *, run_id: str, live_session_id: str, started_at: datetime, ended_at: datetime
) -> dict[str, Any]:
    """What a voice-only exchange row carries, either role (ADR-299).

    Args:
        run_id: The session's run id.
        live_session_id: The session.
        started_at: When the exchange started, as the client measured it.
        ended_at: When it ended.

    Returns:
        A NEW dict, stamped when a run is driving — never, for a live session
        (the person is present), but the doctrine holds for every builder.
    """
    return with_origin_stamp(
        {
            FIELD_RUN_ID: run_id,
            "type": LIVE_TURN_MESSAGE_TYPE,
            FIELD_LIVE_SESSION_ID: live_session_id,
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
        }
    )


def build_live_session_summary_metadata(
    *,
    run_id: str,
    live_session_id: str,
    outcome: str,
    duration_seconds: int,
    delegations: int,
    voice_turns: int,
    usage: dict[str, Any] | None,
    extensions: int = 0,
    mode: str = "delegated",
    relay: str | None = None,
    relay_summary: str | None = None,
) -> dict[str, Any]:
    """What the end-of-session card carries (ADR-299).

    The usage keys are the chat meter's (``tokens_in`` …), so the bubble reads
    them exactly as it reads a proactive notification's; they are LIA's own
    spend over the session's delegated turns and nothing of the provider's.

    Args:
        run_id: The session's run id.
        live_session_id: The session.
        outcome: How it ended (a ``LiveOutcome``).
        duration_seconds: From the first credential to the end.
        delegations: Requests handed to LIA.
        voice_turns: Exchanges the voice held alone.
        usage: The aggregated meter figures, or None when nothing was spent.
        extensions: How many times the person prolonged the session.
        mode: ``delegated`` or ``direct`` (ADR-300 wave 4) — a DIRECT session
            archives no exchange, so the card draws no exchange count.
        relay: A DIRECT session's relay fate (ADR-301): ``scheduled`` at the
            closing, then the ``RelayOutcome`` the settle patches in; None
            for a delegated session.
        relay_summary: The neutral recap of the words when the relay did not
            run (the phone's fallback push carries the same); None otherwise.

    Returns:
        A NEW dict.
    """
    metadata: dict[str, Any] = {
        FIELD_RUN_ID: run_id,
        "type": LIVE_SESSION_SUMMARY_MESSAGE_TYPE,
        FIELD_LIVE_SESSION_ID: live_session_id,
        # Under its OWN key: the origin stamp writes under the origin KIND, and
        # a relayed turn's kind is `live_session` (review 2026-09-20).
        FIELD_LIVE_SUMMARY: {
            "outcome": outcome,
            "duration_seconds": duration_seconds,
            "delegations": delegations,
            "voice_turns": voice_turns,
            "extensions": extensions,
            "mode": mode,
            **({"relay": relay} if relay is not None else {}),
            **({"relay_summary": relay_summary} if relay_summary else {}),
        },
    }
    if usage:
        metadata.update(
            {
                "tokens_in": usage["tokens_in"],
                "tokens_out": usage["tokens_out"],
                "tokens_cache": usage["tokens_cache"],
                "cost_eur": usage["cost_eur"],
                "google_api_requests": usage["google_api_requests"],
            }
        )
    return with_origin_stamp(metadata)


def build_interrupted_stream_metadata(*, run_id: str, reason: str) -> dict[str, Any]:
    """What a partial answer carries when the stream died under it.

    Args:
        run_id: The turn, shared with the three ADR-263 registers.
        reason: Why the stream ended early.

    Returns:
        The metadata to archive with what was produced before the break.
    """
    return with_origin_stamp(
        {FIELD_RUN_ID: run_id, "interrupted": True, "interrupt_reason": reason}
    )


async def persist_psyche_snapshot(
    conv_service: Any,
    *,
    message_id: uuid.UUID | None,
    run_id: str,
    user_enabled: bool,
) -> None:
    """Patch the turn's psyche snapshot onto its archived assistant message.

    Extracted from the streaming entry point, which is the codebase's largest
    function: this is a self-contained best-effort concern — peek a summary the
    background task has finished producing, patch it, never let a failure reach
    the stream — and it belongs beside the other message-metadata builders.

    Without it, a reloaded page falls back to the CURRENT store state, so every
    past message would display the assistant's mood as it is now rather than as
    it was.

    Args:
        conv_service: The conversation service that owns message metadata.
        message_id: The archived assistant message, or None when nothing was
            archived — there is then nothing to patch.
        run_id: The turn whose summary to peek.
        user_enabled: Whether this user has the psyche display on; the instance
            flag is read here.
    """
    if not message_id or not getattr(settings, "psyche_enabled", False) or not user_enabled:
        return

    try:
        from src.domains.psyche.service import peek_psyche_summary

        summary = peek_psyche_summary(run_id)
        if not summary:
            return
        async with get_db_context() as db:
            await conv_service.patch_message_metadata(message_id, {"psyche_state": summary}, db)
            await db.commit()
        logger.debug(
            "psyche_state_persisted_to_message",
            run_id=run_id,
            message_id=str(message_id),
        )
    except Exception as exc:
        logger.warning(
            "psyche_state_persist_failed",
            run_id=run_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
