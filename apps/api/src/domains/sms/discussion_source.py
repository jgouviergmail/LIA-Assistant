"""Native SMS pages without implicit contact reads or alert bookkeeping.

The assistant read service owns consent, decryption, blind search and cursor
integrity. Identity remains a literal sender until an independently authorized
contact/relation source resolves it; SmsFacade's broad directory is unsuitable
for a source allowlist.
"""

from uuid import UUID

from src.core.read_budget import mark_read_opened
from src.domains.shared.discussion_lines import evidence_lines
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
    closed_source,
    semantic_version,
    source_snapshot,
)
from src.domains.sms.read_schemas import SmsQuery, SmsView
from src.domains.sms.reads import SmsReadService, require_read
from src.domains.sms.relation_reader import source_stamp
from src.domains.sms.sender_policy import normalize_sender
from src.infrastructure.database.session import get_db_context


def sms_evidence(row: SmsView, request: SourceReadRequest) -> DiscussionEvidence:
    """Project a received SMS into reported evidence about its sender.

    The sender stays unresolved, and a captured or unknown date proves no receipt
    time.

    Args:
        row: The SMS.
        request: The read.

    Returns:
        The evidence.
    """
    lines = evidence_lines()
    frame = (
        lines["sms_sender"].format(sender=row.sender)
        + "\n"
        + lines["sms_content"].format(body=row.body)
    )
    return DiscussionEvidence(
        reference=f"sms:{row.id}",
        source=SourceKey.SMS,
        object_id=str(row.id),
        version=semantic_version(
            (row.sender, row.body, row.received_at.isoformat(), row.date_kind, row.origin)
        ),
        observed_at=request.now,
        occurred_at=row.received_at if row.date_kind == "received" else None,
        recorded_at=row.received_at if row.date_kind == "captured" else None,
        category=row.date_kind,
        subject_id=semantic_version(("sms_sender", normalize_sender(row.sender))),
        usage_nuance=lines["sms_nuance"],
        excerpt=frame[: request.item_max_chars],
        excerpt_truncated=len(frame) > request.item_max_chars,
        assertion="reported",
    )


def _detail_id(reference: str | None) -> UUID:
    if reference is None:
        raise ValueError("SMS detail reference is required")
    prefix, identifier = reference.split(":", 1)
    if prefix != SourceKey.SMS.value:
        raise ValueError("SMS reference source mismatch")
    return UUID(identifier)


class SmsDiscussionSource:
    """The SMS the person's phone relayed, read as the assistant may read them."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one page of SMS in the window (at most fifty), or one by reference.

        Args:
            request: The bounded read.

        Returns:
            The page; closed when SMS are not consented.

        Raises:
            ValueError: The request or its reference is for another source.
            AuthorizationError: SMS are switched off, or the person does not let the assistant read
                them (SMS_CONSENT_REQUIRED).
        """
        if request.request.source != SourceKey.SMS:
            raise ValueError("SMS source mismatch")
        if SourceKey.SMS not in request.allowed_sources:
            return closed_source(request, disabled=True, reason="consent")
        async with get_db_context() as db:
            reader = SmsReadService(db)
            if request.request.operation == "detail":
                item = await reader.get(
                    request.owner_id,
                    _detail_id(request.request.reference),
                    assistant=True,
                    on_read=lambda: mark_read_opened(request.owner_id),
                )
                actor = await require_read(db, request.owner_id, assistant=True)
                return source_snapshot(
                    request,
                    status="ok",
                    items=(sms_evidence(item, request),),
                    total=1,
                    revision=f"{actor.extraction_revision or 0}:{await source_stamp(db, request.owner_id)}",
                )
            query = SmsQuery(
                query=request.request.query,
                from_ts=request.window_start,
                to_ts=request.window_end,
                limit=min(request.item_limit, 50),
                cursor=request.cursor,
            )
            page = await reader.list(
                request.owner_id,
                query,
                assistant=True,
                on_read=lambda: mark_read_opened(request.owner_id),
            )
            items = tuple(sms_evidence(row, request) for row in page.items)
            return source_snapshot(
                request,
                status="truncated" if page.next_cursor else ("ok" if items else "empty"),
                complete=not (request.cursor or page.next_cursor or request.request.query),
                total=page.total,
                items=items,
                cursor=page.next_cursor,
                revision=f"{page.revision}:{await source_stamp(db, request.owner_id)}",
            )
