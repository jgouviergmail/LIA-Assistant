"""Peers router — the /peers REST surface (Lot 1, spec §4.3).

Every endpoint requires an active session; anything probe-able answers with
the neutral 404 raised inside the service (hide-existence doctrine). The
discovery search additionally carries a per-user rate limit (anti-enumeration
— the same factory the account-export surface uses). Write endpoints commit
explicitly (open_loops precedent), then deliver the service's lifecycle
events to the affected users' chats best-effort (Lot 3 — a notification
hiccup never fails an action that already committed).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.peers.notifications import dispatch_peer_events
from src.domains.peers.repository import PeersRepository
from src.domains.peers.schemas import (
    AccessLogEntry,
    BlockCreate,
    BlockView,
    ConnectionRequestCreate,
    ConnectionRespond,
    ConnectionStateView,
    ConnectionView,
    DiscoveryMatch,
    DiscoverySearchRequest,
    DiscoveryStateResponse,
    DiscoveryStateUpdate,
    RelayedMessageItem,
    RelayedMessagePage,
    ShareUpdate,
)
from src.domains.peers.service import PeersService
from src.domains.users.models import User
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/peers", tags=["Peers"])

# Read once at import, like every settings-driven module constant: the limiter
# closure holds the values for the process lifetime.
rate_limit_peer_discovery = create_user_rate_limiter(
    action="peers_discovery",
    max_calls=settings.peers_discovery_rate_limit_calls,
    window_seconds=settings.peers_discovery_rate_limit_window_seconds,
)


async def _notify_events_best_effort(service: PeersService, db: AsyncSession) -> None:
    """Deliver lifecycle events AFTER the commit; never fail the API call.

    The state change is already durable — a notification hiccup (FCM down,
    Redis blip) must degrade to a warning, not a 500 on an action that
    succeeded (same contract as the scheduled-action approval dispatch).
    """
    try:
        await dispatch_peer_events(service.pending_events, db)
    except Exception as exc:  # noqa: BLE001 — best-effort by contract
        logger.warning(
            "peers_notifications_dispatch_failed",
            events=len(service.pending_events),
            error_type=type(exc).__name__,
        )


@router.get(
    "/me",
    response_model=DiscoveryStateResponse,
    summary="Get my peers opt-ins",
    description=(
        "Whether the current user can be found by peer discovery search, and "
        "whether accepted connections see their real address."
    ),
)
async def get_discovery_state(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> DiscoveryStateResponse:
    """Return the caller's peers opt-ins (discovery + address visibility)."""
    service = PeersService(db)
    enabled = await service.get_discovery_state(user.id)
    return DiscoveryStateResponse(
        discovery_enabled=enabled,
        email_visible=bool(user.peer_email_visible),
    )


@router.put(
    "/me",
    response_model=DiscoveryStateResponse,
    summary="Toggle my peers opt-ins",
    description=(
        "Opt in or out of being discoverable, and of showing your address to "
        "accepted connections. Fields are independent; send only what changes."
    ),
)
async def update_discovery_state(
    payload: DiscoveryStateUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> DiscoveryStateResponse:
    """Persist whichever peers opt-in the payload actually carries.

    Partial by contract: the two switches are independent consents, and one
    tab must never revert what another just changed by echoing a stale value.
    """
    service = PeersService(db)
    if payload.discovery_enabled is not None:
        await service.set_discovery(user.id, payload.discovery_enabled)
    if payload.email_visible is not None:
        await service.set_email_visibility(user.id, payload.email_visible)
    await db.commit()
    return DiscoveryStateResponse(
        discovery_enabled=bool(user.discovery_enabled),
        email_visible=bool(user.peer_email_visible),
    )


@router.post(
    "/discovery/search",
    response_model=list[DiscoveryMatch],
    summary="Search discoverable users by exact name or email",
    description=(
        "Exact match over opted-in active users: a full name (accent/case folded) "
        "or an email address (case folded). Rate limited per user; never prefix "
        "or substring matching."
    ),
    dependencies=[Depends(rate_limit_peer_discovery)],
)
async def search_discovery(
    payload: DiscoverySearchRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> list[DiscoveryMatch]:
    """Run the exact-match discovery search."""
    service = PeersService(db)
    return await service.search_discoverable(user.id, payload.query)


@router.post(
    "/requests",
    response_model=ConnectionStateView,
    status_code=status.HTTP_201_CREATED,
    summary="Request a connection",
    description="Send a connection request to a discoverable user (crossing requests auto-accept).",
)
async def create_request(
    payload: ConnectionRequestCreate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectionStateView:
    """Create (or revive) a connection request."""
    service = PeersService(db)
    view = await service.request_connection(user.id, payload.peer_id, payload.context_message)
    await db.commit()
    await _notify_events_best_effort(service, db)
    return view


@router.get(
    "/requests",
    response_model=list[ConnectionView],
    summary="List my pending requests",
    description="Incoming and outgoing pending connection requests.",
)
async def list_requests(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> list[ConnectionView]:
    """List pending requests, newest first."""
    service = PeersService(db)
    return await service.get_pending(user.id)


@router.post(
    "/requests/{connection_id}/respond",
    response_model=ConnectionStateView,
    summary="Accept or decline a request",
    description="Only the addressee of a pending request may respond.",
)
async def respond_to_request(
    connection_id: UUID,
    payload: ConnectionRespond,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectionStateView:
    """Accept or decline one pending request."""
    service = PeersService(db)
    view = await service.respond_request(user.id, connection_id, payload.accept)
    await db.commit()
    await _notify_events_best_effort(service, db)
    return view


@router.get(
    "/connections",
    response_model=list[ConnectionView],
    summary="List my connections",
    description="Accepted connections with both share directions (mine editable, theirs read-only).",
)
async def list_connections(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> list[ConnectionView]:
    """List accepted connections."""
    service = PeersService(db)
    return await service.get_connections(user.id)


@router.delete(
    "/connections/{connection_id}",
    response_model=ConnectionStateView,
    summary="Remove a connection",
    description="Remove an accepted connection; both users are notified by their assistant.",
)
async def remove_connection(
    connection_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectionStateView:
    """Remove one accepted connection."""
    service = PeersService(db)
    view = await service.remove_connection(user.id, connection_id)
    await db.commit()
    await _notify_events_best_effort(service, db)
    return view


@router.put(
    "/connections/{connection_id}/shares",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Set or remove one of my shares",
    description=(
        "Upsert my share level for a domain on this connection, or remove it "
        "(level=null). Calendar admits availability|details; task admits titles."
    ),
)
async def set_or_delete_share(
    connection_id: UUID,
    payload: ShareUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Upsert or remove one of MY shares on this connection."""
    service = PeersService(db)
    await service.set_share(user.id, connection_id, payload.domain, payload.level)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/access-log",
    response_model=list[AccessLogEntry],
    summary="Who read my shared data",
    description="Transparency view: cross-user reads of MY data, newest first.",
)
async def list_access_log(
    limit: int = Query(default=50, ge=1, le=200, description="Max entries returned."),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> list[AccessLogEntry]:
    """List reads of the caller's shared data."""
    service = PeersService(db)
    return await service.get_access_log(user.id, limit)


@router.post(
    "/blocks",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Block a user",
    description="Silently sever any connection state; the blocked user is never notified.",
)
async def create_block(
    payload: BlockCreate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Place a block (idempotent)."""
    service = PeersService(db)
    await service.block_peer(user.id, payload.peer_id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/blocks/{peer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unblock a user",
    description="Lift a block; nothing is restored (a new request is needed).",
)
async def delete_block(
    peer_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Lift a block placed by the caller."""
    service = PeersService(db)
    await service.unblock_peer(user.id, peer_id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/blocks",
    response_model=list[BlockView],
    summary="List my blocks",
    description="Users the caller has blocked (never who blocked the caller).",
)
async def list_blocks(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> list[BlockView]:
    """List the caller's blocks."""
    service = PeersService(db)
    return await service.list_blocks(user.id)


# =============================================================================
# Relayed messages — the notifications hub's peers section
# =============================================================================


@router.get(
    "/messages",
    response_model=RelayedMessagePage,
    summary="Relayed messages, newest first",
    description=(
        "One page of the caller's relayed messages, both directions, with the "
        "EXACT total behind it. Read-only: the hub lists what reached the "
        "reader, it never re-opens the relay."
    ),
)
async def list_relayed_messages(
    limit: int = Query(default=10, ge=1, le=100, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Page offset."),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> RelayedMessagePage:
    """One page of relayed messages, and the exact total behind it.

    Both halves come from ONE session so a delivery landing between two reads
    cannot produce a total the page contradicts.

    Args:
        limit: Page size.
        offset: Page offset.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The page and the EXACT total (ADR-185) — the hub states its cap rather
        than applying it in silence.
    """
    repo = PeersRepository(db)
    activity = await repo.list_delivered_message_activity(user.id, limit=limit, offset=offset)
    total = await repo.count_delivered_messages(user.id)
    return RelayedMessagePage(
        messages=[
            RelayedMessageItem(
                id=str(item.message_id),
                peer_display_name=item.peer_display_name,
                direction=item.direction,
                content=item.text,
                occurred_at=item.occurred_at,
            )
            for item in activity
        ],
        total=total,
    )
