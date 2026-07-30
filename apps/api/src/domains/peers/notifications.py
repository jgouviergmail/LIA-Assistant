"""Peers chat-lifecycle notifications (Lot 3, spec §6).

Turns the :class:`PeerEvent` list a :class:`PeersService` accumulated into
chat deliveries through :class:`NotificationDispatcher` (archive-first + FCM +
SSE + channels — the proactive pattern). Recipients per kind:

- ``request_created`` / ``request_accepted`` / ``request_declined`` — the
  affected user who is NOT the actor (the actor performed the action in their
  own UI and needs no echo).
- ``connection_removed`` — BOTH sides, each told by their own assistant in
  their own language (explicit spec requirement).

Every body names the OTHER participant relative to its recipient. Bodies link
to the settings deep link (connectors precedent — no locale segment); the
``?intent=`` accept/refuse upgrade ships with the agents lot. Best-effort by
contract: one failed recipient never blocks the others, and the caller wraps
the whole dispatch so an API call that already committed can never fail here.
Logs carry ids only (no names, no note content).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.i18n_proactive import ProactiveMessages
from src.domains.peers.models import PeerConnection
from src.domains.users.models import User
from src.infrastructure.observability.metrics_registry import peers_events_total
from src.infrastructure.proactive.notification import NotificationDispatcher

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domains.peers.schemas import PeerEvent

logger = structlog.get_logger(__name__)

# Falls back to the generic connection title/body family for unknown kinds.
_REQUEST_KIND = "request_created"
_REMOVED_KIND = "connection_removed"


def _settings_url() -> str:
    """Absolute deep link to the « Connexions » section (locale-less)."""
    return f"{settings.frontend_url}/dashboard/settings?section=peer-connections"


def _display_name(user: User | None) -> str:
    """Best-available display name for a participant (never the email)."""
    return (user.full_name if user is not None and user.full_name else None) or "?"


def _body_for(
    kind: str,
    other: User | None,
    connection: PeerConnection | None,
    language: str,
) -> tuple[str, str]:
    """Build (task_type, body) for one recipient.

    Args:
        kind: PeerEvent kind.
        other: The OTHER participant relative to the recipient.
        connection: Pair row (for the request's context note).
        language: Recipient language.

    Returns:
        Tuple of (proactive task type, localized markdown body).
    """
    name = _display_name(other)
    if kind == _REQUEST_KIND:
        note = connection.context_message if connection is not None else None
        return "peer_request", ProactiveMessages.peer_request_body(
            name, note, _settings_url(), language
        )
    if kind == "request_accepted":
        return "peer_connection", ProactiveMessages.peer_accepted_body(
            name, _settings_url(), language
        )
    if kind == "request_declined":
        return "peer_connection", ProactiveMessages.peer_declined_body(name, language)
    # connection_removed (and any future kind defaults to the removal wording).
    return "peer_connection", ProactiveMessages.peer_removed_body(name, language)


def _recipients(event: PeerEvent) -> tuple[UUID, ...]:
    """Who gets a chat message for this event (spec §6)."""
    if event.kind == _REMOVED_KIND:
        return event.affected_ids
    return tuple(uid for uid in event.affected_ids if uid != event.actor_id)


async def dispatch_peer_events(events: list[PeerEvent], db: AsyncSession) -> None:
    """Deliver every pending peer event to its recipients' chats.

    Args:
        events: Events accumulated by a PeersService during one request.
        db: Session used to load recipients and dispatch archives.
    """
    from contextlib import suppress

    if not events:
        return
    dispatcher = NotificationDispatcher()
    for event in events:
        with suppress(Exception):  # metrics must never block a dispatch
            peers_events_total.labels(kind=event.kind).inc()
        connection = await db.get(PeerConnection, event.connection_id)
        participants: dict[UUID, User | None] = {
            uid: await db.get(User, uid) for uid in event.affected_ids
        }
        for recipient_id in _recipients(event):
            recipient = participants.get(recipient_id)
            if recipient is None or not recipient.is_active or recipient.deleted_at:
                continue  # deactivated/deleted accounts get nothing (spec §5.3)
            other_id = next((uid for uid in event.affected_ids if uid != recipient_id), None)
            other = participants.get(other_id) if other_id is not None else None
            task_type, body = _body_for(event.kind, other, connection, recipient.language)
            try:
                await dispatcher.dispatch(
                    user=recipient,
                    content=body,
                    task_type=task_type,
                    target_id=str(event.connection_id),
                    # peer_id/name: chat quick-actions (Lot 7 — accept/decline
                    # on requests, block) act on the OTHER side without lookup.
                    metadata={
                        "peer_event": event.kind,
                        "peer_id": str(other.id) if other is not None else None,
                        "peer_name": _display_name(other),
                    },
                    db=db,
                    title=ProactiveMessages.notification_title(task_type, recipient.language),
                )
            except Exception as exc:  # noqa: BLE001 — isolation per recipient
                logger.warning(
                    "peers_event_dispatch_failed",
                    kind=event.kind,
                    connection_id=str(event.connection_id),
                    recipient_id=str(recipient_id),
                    error_type=type(exc).__name__,
                )
