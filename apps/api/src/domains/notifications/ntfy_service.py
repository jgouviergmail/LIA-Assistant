"""The ntfy subscriptions of an account (ADR-391).

A subscription is made on the instance's server — its topic drawn by LIA, under the prefix the
server lets LIA alone publish to — or on a public https server the person names, with an existing
topic and token of theirs or a drawn topic. What ntfy or LIA would refuse is refused here, before
anything is kept, with a code the settings translate; a secret is never echoed back in a refusal.

The per-account ceiling is counted and written under one advisory lock (``owner_lock``): two
simultaneous requests at the ceiling never pass it together. The session's caller commits.
"""

from __future__ import annotations

from urllib.parse import quote
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import (
    raise_not_found_or_unauthorized,
)
from src.core.security.authorization import check_resource_ownership_by_user_id
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.notifications.models import NtfySubscription
from src.domains.notifications.ntfy import (
    NtfyContent,
    NtfyServerKind,
    new_topic,
    server_url_refusal,
    subscribe_link,
    token_refusal,
    topic_refusal,
)
from src.domains.notifications.ntfy_errors import (
    CUSTOM_SERVERS_DISABLED,
    INSTANCE_UNAVAILABLE,
    SUBSCRIPTION_LIMIT,
    SUBSCRIPTION_UNREADABLE,
    TOKEN_INVALID,
    TOPIC_INVALID,
    refuse,
)
from src.domains.notifications.ntfy_repository import (
    NtfySubscriptionRepository,
    NtfyTarget,
    target_of,
)
from src.domains.notifications.ntfy_schemas import (
    NtfyOverview,
    NtfySubscriptionCreate,
    NtfySubscriptionUpdate,
    NtfySubscriptionView,
)
from src.infrastructure.database.owner_lock import hold_owner_lock
from src.infrastructure.external.ntfy_client import NtfyOutcome

#: The advisory lock scope a subscription's count and write share.
_LOCK_SCOPE = "ntfy_subscriptions"


def _clear_topic(row: NtfySubscription) -> str | None:
    """The topic in clear, or None when it no longer decrypts (a changed encryption key)."""
    try:
        return decrypt_data(row.topic_encrypted)
    except ValueError:
        return None


def _address_of(row: NtfySubscription) -> str:
    """The server an app subscribes to: the instance's public address, or the person's."""
    if NtfyServerKind(row.server_kind) is NtfyServerKind.INSTANCE:
        return settings.ntfy_instance_public_url
    return row.server_url or ""


def view_of(row: NtfySubscription) -> NtfySubscriptionView:
    """A subscription as its owner sees it, to subscribe from an app.

    A row whose topic no longer decrypts is still shown — without its topic — so its owner can
    remove it: one unreadable secret never takes the settings down.

    Args:
        row: The stored subscription.

    Returns:
        The view, its topic in clear and the address an app subscribes to.
    """
    server_kind = NtfyServerKind(row.server_kind)
    topic = _clear_topic(row)
    address = _address_of(row)
    return NtfySubscriptionView(
        id=row.id,
        server_kind=server_kind,
        server_url=address,
        topic=topic,
        has_token=row.token_encrypted is not None,
        content=NtfyContent(row.content),
        is_active=row.is_active,
        last_sent_at=row.last_sent_at,
        last_error_code=NtfyOutcome(row.last_error_code) if row.last_error_code else None,
        last_error_at=row.last_error_at,
        created_at=row.created_at,
        subscribe_link=subscribe_link(address, topic) if topic and address else None,
    )


def _custom_fields(request: NtfySubscriptionCreate) -> tuple[str, str, str | None]:
    """A custom server's address, topic and token, or the refusal they earn."""
    if not settings.ntfy_custom_servers_enabled:
        refuse(CUSTOM_SERVERS_DISABLED)
    url = (request.server_url or "").strip()
    url_refused = server_url_refusal(url)
    if url_refused:
        refuse(url_refused)
    topic = request.topic or new_topic()
    if topic_refusal(topic):
        refuse(TOPIC_INVALID)
    if request.token is not None and token_refusal(request.token):
        refuse(TOKEN_INVALID)
    return url.rstrip("/"), topic, request.token


class NtfySubscriptionService:
    """Make, change and remove an account's ntfy subscriptions."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize the service on the request's session."""
        self.db = db
        self.repository = NtfySubscriptionRepository(db)

    async def overview(self, user_id: UUID) -> NtfyOverview:
        """Everything the settings draw: the instance server, the rules and the subscriptions.

        Args:
            user_id: The account.

        Returns:
            The overview.
        """
        rows = await self.repository.list_for_user(user_id)
        return NtfyOverview(
            instance_url=settings.ntfy_instance_public_url or None,
            custom_servers_enabled=settings.ntfy_custom_servers_enabled,
            max_subscriptions=settings.ntfy_max_subscriptions_per_user,
            subscriptions=[view_of(row) for row in rows],
        )

    async def create(self, user_id: UUID, request: NtfySubscriptionCreate) -> NtfySubscriptionView:
        """Make a subscription, within the account's ceiling.

        Args:
            user_id: The account.
            request: The server, topic, token and content asked for.

        Returns:
            The new subscription.

        Raises:
            StructuredValidationError: A refusal, coded ``ntfy_*``.
        """
        if request.server is NtfyServerKind.INSTANCE:
            if not settings.ntfy_server_url:
                refuse(INSTANCE_UNAVAILABLE)
            server_url, topic, token = None, new_topic(), None
        else:
            server_url, topic, token = _custom_fields(request)
        await hold_owner_lock(self.db, _LOCK_SCOPE, user_id)
        ceiling = settings.ntfy_max_subscriptions_per_user
        if await self.repository.count_for_user(user_id) >= ceiling:
            refuse(SUBSCRIPTION_LIMIT, max=ceiling)
        row = await self.repository.create(
            {
                "user_id": user_id,
                "server_kind": request.server.value,
                "server_url": server_url,
                "topic_encrypted": encrypt_data(topic),
                "token_encrypted": encrypt_data(token) if token else None,
                "content": request.content.value,
            }
        )
        return view_of(row)

    async def owned(self, user_id: UUID, subscription_id: UUID) -> NtfySubscription:
        """A subscription of this account, or « not found » (never « forbidden »).

        Args:
            user_id: The account.
            subscription_id: The subscription.

        Returns:
            The subscription.

        Raises:
            ResourceNotFoundError: Absent, or another account's.
        """
        # A paused subscription (is_active false) is still the person's: never a soft delete.
        row = await self.repository.get_by_id(subscription_id, include_inactive=True)
        check_resource_ownership_by_user_id(row, user_id, "ntfy_subscription")
        if row is None:  # the check already refused it: this narrows the type
            raise_not_found_or_unauthorized("ntfy_subscription", subscription_id)
        return row

    async def target(self, user_id: UUID, subscription_id: UUID) -> NtfyTarget:
        """One subscription of this account as a delivery uses it, detached from the session.

        Paused or not: a test is the person's own request on this one subscription.

        Args:
            user_id: The account.
            subscription_id: The subscription.

        Returns:
            The detached target, its secrets in clear.

        Raises:
            ResourceNotFoundError: Absent, or another account's.
            StructuredValidationError: ``ntfy_subscription_unreadable`` — its secrets no longer
                decrypt; the person removes it and subscribes again.
        """
        row = await self.owned(user_id, subscription_id)
        try:
            return target_of(row)
        except ValueError:
            refuse(SUBSCRIPTION_UNREADABLE)

    async def subscribe_target(self, user_id: UUID, subscription_id: UUID) -> str:
        """What a phone scans to subscribe the ntfy app to one subscription.

        The ``ntfy://`` link when the server can be named that way, the topic's web address
        otherwise (the ntfy web app subscribes from there).

        Args:
            user_id: The account.
            subscription_id: The subscription.

        Returns:
            The text the QR code carries.

        Raises:
            ResourceNotFoundError: Absent, or another account's.
            BaseAPIException: ``ntfy_subscription_unreadable`` (its topic no longer decrypts) or
                ``ntfy_instance_unavailable`` (the instance's server is gone).
        """
        row = await self.owned(user_id, subscription_id)
        topic = _clear_topic(row)
        if topic is None:
            refuse(SUBSCRIPTION_UNREADABLE)
        address = _address_of(row)
        if not address:
            refuse(INSTANCE_UNAVAILABLE)
        return subscribe_link(address, topic) or f"{address}/{quote(topic, safe='')}"

    async def update(
        self, user_id: UUID, subscription_id: UUID, request: NtfySubscriptionUpdate
    ) -> NtfySubscriptionView:
        """Change what a subscription receives, or pause it.

        Args:
            user_id: The account.
            subscription_id: The subscription.
            request: The changes; an absent field is left as it is.

        Returns:
            The subscription as it now is.
        """
        row = await self.owned(user_id, subscription_id)
        if request.content is not None:
            row.content = request.content.value
        if request.is_active is not None:
            row.is_active = request.is_active
        await self.db.flush()
        return view_of(row)

    async def delete(self, user_id: UUID, subscription_id: UUID) -> None:
        """Remove a subscription.

        Args:
            user_id: The account.
            subscription_id: The subscription.
        """
        await self.repository.delete(await self.owned(user_id, subscription_id))


__all__ = ["NtfySubscriptionService", "view_of"]
