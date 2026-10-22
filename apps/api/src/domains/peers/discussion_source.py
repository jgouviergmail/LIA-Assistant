"""Read the permitted side of accepted peer relationships and delivered exchanges."""

from uuid import UUID

from pydantic import AwareDatetime
from sqlalchemy import Select, case, select

from src.core.exceptions import ResourceNotFoundError
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.peers.discussion_queries import counterpart, readable_connection
from src.domains.peers.models import PeerConnection, PeerMessage, PeerMessageStatus
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    DiscussionValue,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
    closed_source,
    semantic_version,
)
from src.domains.shared.discussion_sql import native_discussion_page, native_page_snapshot
from src.domains.users.active_reader import require_active_owner_read
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context


class PeerContextRow(DiscussionValue):
    """One accepted connection as a discussion reads it: who, and since when."""

    id: UUID
    recorded_at: AwareDatetime
    peer_id: UUID
    display_name: str
    email: str | None
    connected_since: AwareDatetime | None


class PeerMessageContextRow(DiscussionValue):
    """One relayed message exchanged with a connection, and its direction."""

    id: UUID
    recorded_at: AwareDatetime
    peer_id: UUID
    display_name: str
    text: str
    direction: str
    delivered_at: AwareDatetime
    expires_at: AwareDatetime | None


def _directory(request: SourceReadRequest) -> Select[tuple[object, ...]]:
    row = PeerConnection
    return (
        select(
            row.id,
            row.created_at.label("recorded_at"),
            counterpart(request.owner_id).label("peer_id"),
            User.full_name.label("display_name"),
            case((User.peer_email_visible.is_(True), User.email), else_=None).label("email"),
            row.responded_at.label("connected_since"),
        )
        .join(User, User.id == counterpart(request.owner_id))
        .where(readable_connection(request.owner_id))
    )


def _messages(request: SourceReadRequest) -> Select[tuple[object, ...]]:
    row = PeerMessage
    sent = row.sender_id == request.owner_id
    own_text = case((sent, row.content), else_=row.delivered_text)
    statement = (
        select(
            row.id,
            row.created_at.label("recorded_at"),
            counterpart(request.owner_id).label("peer_id"),
            User.full_name.label("display_name"),
            own_text.label("text"),
            case((sent, "sent"), else_="received").label("direction"),
            row.delivered_at,
            row.expires_at,
        )
        .join(PeerConnection, row.connection_id == PeerConnection.id)
        .join(User, User.id == counterpart(request.owner_id))
        .where(
            readable_connection(request.owner_id),
            row.status == PeerMessageStatus.DELIVERED.value,
            row.delivered_at.is_not(None),
            row.delivered_at >= request.window_start,
            row.delivered_at < request.window_end,
            row.delivered_at <= request.now,
            (row.expires_at.is_(None) | (row.expires_at > request.now)),
            own_text.is_not(None),
            own_text != "",
        )
    )
    if request.request.query is not None:
        statement = statement.where(own_text.icontains(request.request.query, autoescape=True))
    return statement


def _peer_evidence(row: PeerContextRow, request: SourceReadRequest) -> DiscussionEvidence:
    text = row.model_dump_json()
    return DiscussionEvidence(
        reference=f"peers:{row.id}",
        source=SourceKey.PEERS,
        object_id=str(row.id),
        subject_id=f"peer:{row.peer_id}",
        version=semantic_version((text,)),
        observed_at=request.now,
        recorded_at=row.recorded_at,
        assertion="observed",
        category="accepted_peer_connection",
        excerpt=text[: request.item_max_chars],
        excerpt_truncated=len(text) > request.item_max_chars,
    )


def _message_evidence(row: PeerMessageContextRow, request: SourceReadRequest) -> DiscussionEvidence:
    text = row.model_dump_json()
    return DiscussionEvidence(
        reference=f"peer_messages:{row.id}",
        source=SourceKey.PEER_MESSAGES,
        object_id=str(row.id),
        subject_id=f"peer:{row.peer_id}",
        version=semantic_version((text,)),
        observed_at=request.now,
        recorded_at=row.recorded_at,
        occurred_at=row.delivered_at,
        expires_at=row.expires_at,
        assertion="reported",
        category=f"peer_message_{row.direction}",
        excerpt=text[: request.item_max_chars],
        excerpt_truncated=len(text) > request.item_max_chars,
    )


async def _read(request: SourceReadRequest, source: SourceKey) -> SourceSnapshot:
    if request.request.source != source:
        raise ValueError("peer source mismatch")
    if source not in request.allowed_sources:
        return closed_source(request, disabled=True, reason="consent")
    messages = source == SourceKey.PEER_MESSAGES
    statement = _messages(request) if messages else _directory(request)
    row_id = PeerMessage.id if messages else PeerConnection.id
    if request.request.reference is not None:
        prefix, identifier = request.request.reference.split(":", 1)
        if prefix != source.value:
            raise ValueError("peer reference source mismatch")
        statement = statement.where(row_id == UUID(identifier))
    async with get_db_context() as db:
        await require_active_owner_read(db, request.owner_id)
        await require_capability_fresh(db, PlatformCapability.PEERS)
        page = await native_discussion_page(
            db,
            request.owner_id,
            statement,
            limit=request.item_limit,
            after_id=UUID(request.cursor) if request.cursor else None,
        )
    if request.request.operation == "detail" and not page.rows:
        raise ResourceNotFoundError("peer", request.request.reference)
    items = tuple(
        (
            _message_evidence(PeerMessageContextRow.model_validate(row), request)
            if messages
            else _peer_evidence(PeerContextRow.model_validate(row), request)
        )
        for row in page.rows[: request.item_limit]
    )
    return native_page_snapshot(
        request,
        page,
        items,
        coverage_kind="dated_synthesis" if messages else "active_facts",
    )


class PeerDiscussionSource:
    """The person's accepted connections, readable from both sides now."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one page of accepted connections, or one by reference.

        Args:
            request: The bounded read.

        Returns:
            The page; closed when peers are not consented.

        Raises:
            ValueError: The request or its reference is for another source.
            ResourceNotFoundError: A detail read names nothing the person can see.
        """
        return await _read(request, SourceKey.PEERS)


class PeerMessageDiscussionSource:
    """The messages relayed between the person and their connections."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one page of relayed messages, or one by reference.

        Args:
            request: The bounded read.

        Returns:
            The page; closed when peer messages are not consented.

        Raises:
            ValueError: The request or its reference is for another source.
            ResourceNotFoundError: A detail read names nothing the person can see.
        """
        return await _read(request, SourceKey.PEER_MESSAGES)
