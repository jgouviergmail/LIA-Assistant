"""Archive-first persistence of the user turn (ADR-117).

The user message is persisted BEFORE graph execution so the turn survives
client disconnects, cancellations and crashes. Its current execution fence
serializes retries of the same invocation; a later HITL invocation owns a new
row. Finalization patches end-of-run HITL flags onto the original request row.

Habits program Lot 0 addition: when the run is automated (scheduled action
executor), the archived row now carries ``is_automated_source: true`` in its
metadata. Without the marker, a synthetic user message is indistinguishable
from a human one at the message level, and
the rhythm profile would learn from LIA's own automations — a feedback loop.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import structlog

from src.core.card_composition import CardCompositionRequest

if TYPE_CHECKING:
    from src.domains.conversations.service import ConversationService

logger = structlog.get_logger(__name__)


def turn_attachment_meta(
    state: Mapping[str, Any], attachment_ids: list[uuid.UUID] | None
) -> dict[str, Any]:
    """The attachment block of the user row: what this turn attached, projected.

    Extracted from ``AgentService.stream_chat_response`` verbatim (file-size
    ratchet). Empty when nothing was attached or uploads are off.

    Args:
        state: The graph state, whose ``metadata.current_turn_attachments`` the
            attachments step filled.
        attachment_ids: The ids the request named.

    Returns:
        ``{"attachments": [...]}`` or ``{}``.
    """
    from src.core.config import settings

    if not attachment_ids or not getattr(settings, "attachments_enabled", False):
        return {}
    turn_attachments = state.get("metadata", {}).get("current_turn_attachments", [])
    if not turn_attachments:
        return {}
    return {
        "attachments": [
            {
                "id": a["id"],
                "filename": a["original_filename"],
                "mime_type": a["mime_type"],
                "size": a.get("file_size", 0),
                "content_type": a["content_type"],
            }
            for a in turn_attachments
        ]
    }


async def archive_user_message_first(
    *,
    conv_service: ConversationService,
    conversation_id: uuid.UUID,
    user_message: str,
    run_id: str,
    is_hitl_resumption: bool,
    attachment_meta: dict[str, Any],
    stt_kwargs: dict[str, Any],
    is_automated_source: bool = False,
    live_session_id: str | None = None,
    spoken_text: str | None = None,
    card_composition: CardCompositionRequest | None = None,
) -> uuid.UUID | None:
    """Persist the user message BEFORE graph execution (archive-first).

    ADR-117 (Lot 1): the user turn must survive client disconnects,
    cancellations and crashes. End-of-run HITL flags (decision_type,
    hitl_interrupted) are patched onto this row during finalization.

    Args:
        conv_service: Conversation service used for archiving.
        conversation_id: Target conversation UUID.
        user_message: Raw user message content.
        run_id: Run identifier stored in the row metadata.
        is_hitl_resumption: True when this message answers a pending
            HITL interrupt (sets ``hitl_response`` immediately).
        attachment_meta: Attachment metadata block ({} when none).
        stt_kwargs: Per-message STT cost attribution kwargs.
        is_automated_source: True when the run is automated (e.g. scheduled
            action) — stamps ``is_automated_source: true`` into the row
            metadata so batch consumers (habit rhythm profile) can exclude
            synthetic user messages. Never written when False: absence is
            the human default, mirroring the source-policy NULL semantics.
        live_session_id: Live mode (ADR-299): the session the turn was spoken
            in, stamped on the row so the session's end can add up its turns.
        spoken_text: The person's transcribed words, kept beside the request.

    Returns:
        The archived row id, or None when archiving failed (best-effort:
        an archiving hiccup must never block the generation itself).
    """
    from src.core.conversation_execution import ExecutionRevoked
    from src.core.field_names import FIELD_IS_AUTOMATED_SOURCE, FIELD_RUN_ID
    from src.core.run_authority import current_run_authority
    from src.domains.agents.api.run_origin import with_origin_stamp
    from src.domains.conversations.publication_repository import ConversationPublicationRepository
    from src.domains.conversations.waiting_repository import WaitingMessageRepository
    from src.infrastructure.database import get_db_context

    metadata: dict[str, Any] = {FIELD_RUN_ID: run_id, **attachment_meta}
    if card_composition is not None:
        metadata["card_composition"] = card_composition.model_dump(mode="json")
    if is_hitl_resumption:
        metadata["hitl_response"] = True
    if is_automated_source:
        metadata[FIELD_IS_AUTOMATED_SOURCE] = True
    # ADR-276: the SECOND row of an out-of-turn run. Stamping only the answer
    # would leave the synthetic question in the chat, which is the half a
    # reader would find hardest to explain.
    metadata = with_origin_stamp(metadata)
    from src.domains.agents.api.archive_metadata import with_live_stamp

    metadata = with_live_stamp(metadata, live_session_id, spoken_text)
    try:
        async with get_db_context() as archive_db:
            authority = current_run_authority()
            if authority is not None:
                authority.require_current()
                if (
                    conversation_id != authority.admission.target.id
                    or run_id != authority.admission.run_id
                ):
                    raise ExecutionRevoked()
                existing = await ConversationPublicationRepository(archive_db).request_message_id(
                    authority.admission, user_message
                )
                if existing is not None:
                    return existing
            row = await conv_service.archive_message(
                conversation_id,
                "user",
                user_message,
                metadata,
                archive_db,
                **stt_kwargs,
            )
            if authority is not None:
                # A message that waited for its turn enters the discussion in
                # this same transaction, or stays where it was (ADR-384).
                await WaitingMessageRepository(archive_db).consume(
                    authority.admission.target.owner_id, authority.admission.stream_id
                )
            return row.id
    except ExecutionRevoked:
        raise
    except Exception as archive_err:  # noqa: BLE001 — must not kill the run
        logger.error(
            "archive_first_user_message_failed",
            run_id=run_id,
            conversation_id=str(conversation_id),
            error_type=type(archive_err).__name__,
        )
        return None
