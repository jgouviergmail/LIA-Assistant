"""
Conversations API router.
REST endpoints for conversation management and message history.
"""

from contextlib import suppress
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    CONVERSATION_HISTORY_CURSOR_MAX_LENGTH,
    CONVERSATION_SEARCH_MAX_LENGTH,
    CONVERSATION_SEARCH_MIN_LENGTH,
    RATE_LIMIT_CONVERSATION_EXPORT_PER_MINUTE,
)
from src.core.conversation_selection import ConversationSelection
from src.core.conversation_target import ConversationKind
from src.core.dependencies import get_db
from src.core.exceptions import raise_message_not_found, raise_no_active_conversation
from src.core.field_names import (
    FIELD_CONTENT,
    FIELD_CREATED_AT,
    FIELD_RESPONSE_FEEDBACK,
)
from src.core.i18n_account_export import render_discussion_label
from src.core.i18n_api_messages import APIMessages
from src.core.session_dependencies import (
    get_current_active_session,
    get_current_active_session_for_stream,
)
from src.core.streaming_download import attachment_stream
from src.core.time_utils import resolve_user_timezone
from src.domains.attachments.card_lifetimes import (
    card_attachment_ids,
    current_lifetimes,
    with_current_lifetimes,
)
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.dependencies import selected_conversation
from src.domains.conversations.discussion_export import stream_discussion_markdown
from src.domains.conversations.discussion_search import search_discussions
from src.domains.conversations.history_cursor import (
    encode_history_cursor,
    encode_search_cursor,
    history_position,
    search_position,
)
from src.domains.conversations.lifecycle_schemas import ConversationOperationRequest
from src.domains.conversations.schemas import (
    ConversationMessageResponse,
    ConversationMessagesResponse,
    ConversationResetResponse,
    ConversationResponse,
    ConversationStatsResponse,
    ConversationTotalsResponse,
    DiscussionSearchResponse,
    DiscussionSearchResult,
    ResponseFeedbackRequest,
)
from src.domains.conversations.service import ConversationService
from src.domains.conversations.usage import read_conversation_usage
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])

rate_limit_export = create_user_rate_limiter(
    action="conversation_export",
    max_calls=RATE_LIMIT_CONVERSATION_EXPORT_PER_MINUTE,
    # The export streams: its limiter reads the account through the same door,
    # or it would pin the request session the route itself avoids (ADR-304).
    authenticate=get_current_active_session_for_stream,
)


@router.get(
    "/me",
    response_model=ConversationResponse | None,
    summary="Get my conversation",
    description="Get current user's active conversation. Returns null if no conversation exists yet (lazy creation).",
)
async def get_my_conversation(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse | None:
    """
    Get current user's active conversation.

    Conversation is created lazily on first message, so this endpoint may return null
    for new users who haven't started chatting yet.

    Returns:
        ConversationResponse if conversation exists, None otherwise
    """
    service = ConversationService()
    conversation = await service.get_active_conversation(current_user.id, db)

    if not conversation:
        logger.debug("conversation_not_found", user_id=str(current_user.id))
        return None

    logger.debug(
        "conversation_retrieved",
        user_id=str(current_user.id),
        conversation_id=str(conversation.id),
        message_count=conversation.message_count,
    )

    return ConversationResponse.model_validate(conversation)


@router.get(
    "/me/messages",
    response_model=ConversationMessagesResponse,
    summary="Get conversation messages",
    description="Get the selected owned discussion's history, or Main when selection is omitted. Messages are returned newest first.",
)
async def get_conversation_messages(
    selection: Annotated[ConversationSelection, Depends(selected_conversation)],
    limit: int = Query(
        settings.conversation_history_default_limit,
        ge=1,
        le=settings.conversation_history_max_limit,
        description="Maximum number of messages to return",
    ),
    before: AwareDatetime | None = Query(
        None,
        description=(
            "Keyset pagination cursor. When provided, returns messages strictly "
            "older than this timestamp (scroll-up). Pass the ``next_cursor`` "
            "from the previous response."
        ),
    ),
    cursor: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=CONVERSATION_HISTORY_CURSOR_MAX_LENGTH,
            description="Opaque next_page_cursor from the preceding page; excludes before.",
        ),
    ] = None,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationMessagesResponse:
    """
    Get conversation message history for UI display.

    Messages are paginated and returned in descending order (newest first).
    Useful for displaying chat history without deserializing LangGraph checkpoints.

    The composite cursor orders by (created_at, id) and binds the public
    discussion revision. The legacy timestamp-only before cut remains strict.
    Both modes omit hidden and blank progress rows before applying the limit.

    Args:
        selection: Explicit owned discussion/revision, or the legacy Main alias.
        limit: Maximum number of messages. Bounds and default come from
            ``settings.conversation_history_default_limit`` and
            ``settings.conversation_history_max_limit`` (env-configurable).
        before: Keyset cursor for scroll-up pagination (created_at).
        cursor: Opaque composite position, mutually exclusive with before.
        current_user: Authenticated user from session dependency.
        db: Database session from FastAPI dependency injection.

    Returns:
        List of messages with conversation metadata, ``has_more`` flag and
        ``next_page_cursor`` for the following page, plus the legacy next_cursor.

    Raises:
        ResourceNotFoundError: No owned active discussion exists.
        ResourceConflictError: The requested generation was reset.
        ValidationError: A cursor is damaged or belongs to another generation.
    """
    service = ConversationService()

    # The shared lock lasts only for this SQL history read, never an external call.
    conversation = await ConversationCatalogueService(db).resolve_target(
        current_user.id, selection, lock=True
    )

    if not conversation:
        raise_no_active_conversation(APIMessages.no_active_conversation_start_chatting())
    position = history_position(conversation, cursor=cursor, before=before)

    # Fetch limit+1 messages to detect ``has_more`` without an extra COUNT query.
    # If we get back limit+1 rows, older messages exist beyond the current page.
    messages = await service.get_messages_with_tokens_auto(
        user_id=current_user.id,
        limit=limit + 1,
        db=db,
        before_created_at=position.at if position else None,
        before_message_id=position.id if position else None,
        target=conversation,
    )

    has_more = len(messages) > limit
    if has_more:
        messages = messages[:limit]
    # next_cursor is the oldest message in the returned page (DESC order → last item).
    # Clients pass it back as ``before`` on the next request.
    next_cursor = messages[-1][FIELD_CREATED_AT] if (has_more and messages) else None
    next_page_cursor = (
        encode_history_cursor(conversation, messages[-1][FIELD_CREATED_AT], messages[-1]["id"])
        if has_more and messages
        else None
    )

    # Count user messages in the returned page (semantics preserved for backwards
    # compatibility; not a global total — see schema description).
    total_user_messages = sum(1 for msg in messages if msg["role"] == "user")

    logger.debug(
        "messages_retrieved",
        user_id=str(current_user.id),
        conversation_id=str(conversation.id),
        total_messages=len(messages),
        user_messages=total_user_messages,
        limit=limit,
        has_more=has_more,
        before=before.isoformat() if before else None,
    )

    # Interactive widgets persisted on the message are rehydrated here so a
    # conversation reopened from history renders its skill/MCP frames instead
    # of an "unavailable" box. `is_system_skill` is deliberately RECOMPUTED
    # rather than trusted: it grants the iframe `allow-same-origin` and the
    # `credentialless` attribute, and a skill demoted from system to user since
    # the message was written must not keep those privileges (ADR-137).
    from src.domains.agents.data_registry.message_widgets import with_rehydrated_widgets
    from src.domains.skills.cache import SkillsCache

    system_skill_names = SkillsCache.get_system_skill_names(str(current_user.id))
    # A file card states the lifetime its file has NOW, not the one written when
    # it was produced: the person may have kept it or deleted it since
    # (ADR-319). One read for the whole page.
    lifetimes = await current_lifetimes(
        db, current_user.id, card_attachment_ids(msg["message_metadata"] for msg in messages)
    )

    return ConversationMessagesResponse(
        messages=[
            ConversationMessageResponse(
                id=msg["id"],
                role=msg["role"],
                content=msg[FIELD_CONTENT],
                message_metadata=with_current_lifetimes(
                    with_rehydrated_widgets(
                        msg["message_metadata"], system_skill_names=system_skill_names
                    ),
                    lifetimes,
                ),
                created_at=msg[FIELD_CREATED_AT],
                tokens_in=msg["tokens_in"],
                tokens_out=msg["tokens_out"],
                tokens_cache=msg["tokens_cache"],
                cost_eur=msg["cost_eur"],
                google_api_requests=msg["google_api_requests"],
                stt_provider=msg.get("stt_provider"),
                stt_audio_duration_seconds=msg.get("stt_audio_duration_seconds"),
                stt_cost_eur=msg.get("stt_cost_eur"),
                tts_provider=msg.get("tts_provider"),
                tts_model=msg.get("tts_model"),
                tts_characters=msg.get("tts_characters"),
                tts_cost_eur=msg.get("tts_cost_eur"),
            )
            for msg in messages
        ],
        conversation_id=conversation.id,
        conversation_revision=conversation.revision,
        next_page_cursor=next_page_cursor,
        total_count=total_user_messages,
        has_more=has_more,
        next_cursor=next_cursor,
    )


@router.get(
    "/me/search",
    response_model=DiscussionSearchResponse,
    summary="Search every discussion",
    description=(
        "Find the words in every discussion of the account, Main and secondary ones, "
        "newest first. Same matching as the history search; only what the chat shows."
    ),
)
async def search_discussion_messages(
    q: str = Query(
        ...,
        min_length=CONVERSATION_SEARCH_MIN_LENGTH,
        max_length=CONVERSATION_SEARCH_MAX_LENGTH,
        description="Words to find (case- and accent-insensitive; wildcards are literals)",
    ),
    limit: int = Query(
        settings.conversation_history_default_limit,
        ge=1,
        le=settings.conversation_history_max_limit,
        description="Maximum number of results to return",
    ),
    cursor: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=CONVERSATION_HISTORY_CURSOR_MAX_LENGTH,
            description="Opaque next_cursor of the preceding page.",
        ),
    ] = None,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> DiscussionSearchResponse:
    """Search the account's discussions: one statement, through the door the assistant uses too."""
    page = await search_discussions(
        db, current_user.id, q, limit=limit, before=search_position(cursor)
    )
    last = page.hits[-1] if page.has_more and page.hits else None
    return DiscussionSearchResponse(
        results=[DiscussionSearchResult.model_validate(hit) for hit in page.hits],
        has_more=page.has_more,
        next_cursor=encode_search_cursor(last.created_at, last.message_id) if last else None,
    )


@router.post(
    "/me/messages/{message_id}/feedback",
    summary="Submit response feedback",
    description="Submit a thumbs verdict (and optional comment) on an assistant response.",
)
async def submit_response_feedback(
    message_id: UUID,
    data: ResponseFeedbackRequest,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Persist a 👍/👎 verdict on an ordinary assistant response (QW-5, ADR-138).

    The verdict lands in ``message_metadata`` (atomic owner-scoped
    ``jsonb_set``); on the FIRST verdict only, the journal entries injected
    into that turn get their evidence/contradiction counters incremented; a
    👎 comment additionally lands as an L0 ``user_correction`` entry (no
    consolidation). Never triggers a regeneration.

    Raises:
        HTTPException 404: Unknown message, foreign owner, or non-assistant
            row (existence hidden).
    """
    from src.domains.conversations.response_feedback import (
        apply_verdict_to_journals,
        get_assistant_message_for_user,
        lock_feedback_owner,
        persist_verdict,
        record_comment_as_correction,
    )

    await lock_feedback_owner(db, current_user.id)
    row = await get_assistant_message_for_user(db, current_user.id, message_id)
    if row is None:
        raise_message_not_found(message_id)

    metadata = dict(row.message_metadata or {})
    first_verdict = not isinstance(metadata.get(FIELD_RESPONSE_FEEDBACK), dict)
    comment = (data.comment or "").strip() or None

    await persist_verdict(db, current_user.id, message_id, data.verdict, comment)
    entries_updated = 0
    if first_verdict:
        # Counters have no decrement path — a verdict CHANGE must never
        # re-feed them (double count), only update the stored verdict.
        entries_updated = await apply_verdict_to_journals(
            db,
            current_user.id,
            metadata,
            data.verdict,
            message_id=message_id,
            conversation_id=row.conversation_id,
        )
    if comment and data.verdict == "thumbs_down":
        await record_comment_as_correction(db, current_user.id, comment)
    from src.domains.conversations.efficacy_feedback import apply_efficacy_feedback

    await apply_efficacy_feedback(db, current_user.id, message_id, data.verdict)
    await db.commit()

    # Best-effort metric emission — never fails the request.
    with suppress(Exception):
        from src.infrastructure.observability.metrics_registry import track_response_feedback

        track_response_feedback(data.verdict)

    # Product analytics E1 path (ADR-178): upgrade/reject the run's outcome.
    # Flag-guarded and best-effort inside the service; run_id comes from the
    # judged assistant message's own metadata (absent on legacy rows).
    with suppress(Exception):
        from src.domains.product.service import record_response_feedback

        await record_response_feedback(
            user_id=current_user.id,
            run_id=(metadata.get("run_id") if isinstance(metadata, dict) else None),
            verdict=data.verdict,
        )

    # Counters and flags only at INFO — the comment is content (PII rule).
    logger.info(
        "response_feedback_submitted",
        user_id=str(current_user.id),
        message_id=str(message_id),
        verdict=data.verdict,
        first_verdict=first_verdict,
        journal_entries_updated=entries_updated,
        has_comment=bool(comment),
    )

    return {"message": APIMessages.feedback_submitted_successfully()}


@router.post(
    "/me/reset",
    response_model=ConversationResetResponse,
    summary="Reset conversation",
    description=(
        "Reset the conversation IN PLACE: the row is kept, its content is purged. "
        "Irreversible — requires explicit user confirmation on the frontend."
    ),
)
async def reset_my_conversation(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
    payload: ConversationOperationRequest | None = None,
) -> ConversationResetResponse:
    """Compatibility alias for Main; success means its durable cleanup completed.

    New clients supply the reviewed revision and a stable operation identity.
    A still-pending cleanup returns its reconciliation identity through a typed
    conflict, never a misleading success or a second unidentifiable reset.
    """
    result = await ConversationService().reset_conversation(
        current_user.id,
        db,
        language=current_user.language,
        operation_id=payload.operation_id if payload else None,
        expected_revision=payload.expected_revision if payload else None,
    )
    if result is None:
        raise_no_active_conversation(APIMessages.no_active_conversation_to_reset())
    return ConversationResetResponse(
        status="success",
        message=APIMessages.conversation_reset_successful(),
        previous_message_count=result.previous_message_count,
    )


@router.get(
    "/me/stats",
    response_model=ConversationStatsResponse,
    summary="Get conversation statistics",
    description="Get statistics for current user's conversation (message count, tokens, etc.).",
)
async def get_conversation_stats(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationStatsResponse:
    """
    Get conversation statistics.

    Returns summary metrics for the user's active conversation:
    - Total message count
    - Total tokens consumed
    - Creation date
    - Last message timestamp

    Returns:
        Conversation statistics

    Raises:
        HTTPException 404: If user has no active conversation
    """
    service = ConversationService()
    conversation = await service.get_active_conversation(current_user.id, db)

    if not conversation:
        raise_no_active_conversation(APIMessages.no_active_conversation())

    # Get last message timestamp
    messages = await service.get_messages(current_user.id, limit=1, db=db)
    last_message_at = messages[0].created_at if messages else None

    return ConversationStatsResponse(
        conversation_id=conversation.id,
        message_count=conversation.message_count,
        total_tokens=conversation.total_tokens,
        created_at=conversation.created_at,
        last_message_at=last_message_at,
    )


@router.get(
    "/me/totals",
    response_model=ConversationTotalsResponse,
    summary="Get conversation totals",
    description="Read the selected discussion's historical token usage, billed cost and context footprint.",
)
async def get_conversation_totals(
    selection: Annotated[ConversationSelection, Depends(selected_conversation)],
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationTotalsResponse:
    """Return cumulative usage for the exact owned generation, defaulting to Main."""
    return await read_conversation_usage(db, current_user.id, selection)


@router.get(
    "/me/export",
    dependencies=[Depends(rate_limit_export)],
    summary="Download one discussion as a Markdown document",
    description=(
        "The selected owned discussion, or Main when the selection is omitted, as the chat "
        "shows it: every visible message, oldest first, in the reader's language and clock."
    ),
)
async def export_conversation(
    selection: Annotated[ConversationSelection, Depends(selected_conversation)],
    accept_encoding: Annotated[str | None, Header()] = None,
    current_user: User = Depends(get_current_active_session_for_stream),
) -> Response:
    """Render the caller's own discussion as a downloadable Markdown document.

    Nothing is truncated (ADR-273): the messages are streamed through a
    server-side cursor on a session of their own, and the read is closed at the
    instant the export was asked. The language and the clock are the account's,
    never a query string's.

    The route holds NOTHING while the document streams (ADR-304): a ``yield``
    dependency lives as long as the response, so it authenticates through the
    stream door and reads ownership on a short session of its own, closed
    before the first byte leaves. No lock is taken — the history is read later,
    on the cursor's own snapshot.

    Args:
        selection: Explicit owned discussion/revision, or the legacy Main alias.
        accept_encoding: What the client can decompress.
        current_user: Authenticated user; the discussion exported is always theirs.

    Returns:
        The document, as an attachment named for the reader's day.

    Raises:
        ResourceNotFoundError: No owned active discussion exists.
        ResourceConflictError: The requested generation was reset.
    """
    language = current_user.language
    title = render_discussion_label("main", language)
    async with get_db_context() as db:
        catalogue = ConversationCatalogueService(db)
        target = await catalogue.resolve_target(current_user.id, selection)
        if target is None:
            raise_no_active_conversation(APIMessages.no_active_conversation_start_chatting())
        if target.kind == ConversationKind.SECONDARY:
            # An annex always holds a title (the catalogue's CHECK).
            title = (await catalogue.require_owned(current_user.id, target.id)).title or title
    generated_at = datetime.now(UTC)
    zone = resolve_user_timezone(current_user)
    logger.info(
        "conversation_exported",
        user_id=str(current_user.id),
        conversation_id=str(target.id),
        conversation_kind=target.kind.value,
    )
    return attachment_stream(
        stream_discussion_markdown(
            target,
            title=title,
            language=language,
            timezone=zone.key,
            generated_at=generated_at,
            batch=settings.conversation_history_max_limit,
        ),
        filename=f"lia-discussion-{generated_at.astimezone(zone).strftime('%Y%m%d')}.md",
        media_type="text/markdown; charset=utf-8",
        accept_encoding=accept_encoding,
        # Complete, and it says so rather than leaving a reader to assume it.
        extra_headers={"X-Discussion-Truncated": "false"},
    )
