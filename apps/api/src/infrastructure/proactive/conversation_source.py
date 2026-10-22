"""Native archive adapter: visible human statements, never invented or automated source turns.

Conversation persistence is foundational (shared provenance already reads it),
so the optional discussion-port adapter belongs at the composition boundary.
Its query reuses the conversation domain's canonical visibility and search rules.
"""

from uuid import UUID

from pydantic import AwareDatetime
from sqlalchemy import func, select

from src.core.field_names import FIELD_IS_AUTOMATED_SOURCE
from src.domains.conversations.message_reads import matching_content, visible_only
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    DiscussionValue,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
    closed_source,
    semantic_version,
    source_snapshot,
)
from src.domains.shared.discussion_sql import native_discussion_page
from src.domains.users.active_reader import require_active_owner_read
from src.infrastructure.database.session import get_db_context


class HumanStatement(DiscussionValue):
    """One visible message the person wrote, as a discussion reads it."""

    id: UUID
    recorded_at: AwareDatetime
    content: str


class ConversationDiscussionSource:
    """The person's own recent words in their conversation, never LIA's or automated."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one page of the person's messages in the requested window.

        Args:
            request: The bounded read.

        Returns:
            The page; complete only when the whole window was read with no query or
            cursor. Closed when the source is not consented.

        Raises:
            ValueError: The request is for another source.
        """
        if request.request.source != SourceKey.CONVERSATIONS:
            raise ValueError("conversation source mismatch")
        if SourceKey.CONVERSATIONS not in request.allowed_sources:
            return closed_source(request, disabled=True, reason="consent")
        row = ConversationMessage
        statement = (
            select(row.id, row.created_at.label("recorded_at"), row.content)
            .join(Conversation, Conversation.id == row.conversation_id)
            .where(
                Conversation.user_id == request.owner_id,
                Conversation.deleted_at.is_(None),
                row.role == "user",
                func.coalesce(
                    row.message_metadata[FIELD_IS_AUTOMATED_SOURCE].as_boolean(), False
                ).is_(False),
                row.created_at >= request.window_start,
                row.created_at < request.window_end,
                row.created_at <= request.now,
                # A blank turn states nothing; filtered here, the page and its total agree.
                row.content.regexp_match(r"\S"),
            )
        )
        statement = matching_content(
            visible_only(statement, include_hidden=False), request.request.query
        )
        async with get_db_context() as db:
            await require_active_owner_read(db, request.owner_id)
            page = await native_discussion_page(
                db,
                request.owner_id,
                statement,
                limit=request.item_limit,
                after_id=UUID(request.cursor) if request.cursor else None,
            )
        rows = tuple(HumanStatement.model_validate(value) for value in page.rows)
        items = tuple(
            DiscussionEvidence(
                reference=f"conversations:{row.id}",
                source=SourceKey.CONVERSATIONS,
                object_id=str(row.id),
                version=semantic_version((row.content,)),
                observed_at=request.now,
                recorded_at=row.recorded_at,
                assertion="reported",
                category="human_statement",
                excerpt=row.content[: request.item_max_chars],
                excerpt_truncated=len(row.content) > request.item_max_chars,
            )
            for row in rows[: request.item_limit]
        )
        more = len(rows) > request.item_limit
        return source_snapshot(
            request,
            status="truncated" if more else "ok" if items else "empty",
            items=items,
            total=page.total,
            coverage_kind="dated_synthesis",
            complete=not (more or request.cursor or request.request.query),
            cursor=str(rows[request.item_limit - 1].id) if more else None,
        )
