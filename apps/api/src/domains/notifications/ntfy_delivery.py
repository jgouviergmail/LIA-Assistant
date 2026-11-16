"""The one door through which LIA publishes to ntfy (ADR-391).

Every road a push takes reaches it: the push door (``FCMNotificationService.send_to_user``), a
proactive discussion's delivery, an ingested message's delivery and a broadcast. One door, so a
switch, a content choice or a refusal reads the same on all of them.

Three rules hold the door:

- **the capability decides first.** ``is_capability_enabled`` reads the deployment ceiling AND
  the operator's switch at call time: a switch removes the ability, never the subscriptions
  (ADR-280);
- **no session across the network** (ADR-304). Targets are read in a short session of their
  own and leave it detached; every publication runs with no transaction open; every outcome is
  written afterwards in another short session;
- **nothing is said twice.** A publication is sent once: the client never retries, and a
  request that left unanswered is ``no_answer`` (ADR-221). Callers with a durable outbox read
  :attr:`NtfyBatch.retryable` to decide, never a guess. A store that cannot be read is said
  (:class:`NtfyTargetsUnreadable`: nothing left); one that cannot record the outcomes never
  unsays what left.

Logs carry counts and outcomes, never a topic, a token, a title or words (ADR-317).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.core.config import settings
from src.core.i18n import resolve_language
from src.core.notification_privacy import NotificationPrivacy
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.notifications.ntfy import NtfyServerKind, publication
from src.domains.notifications.ntfy_repository import NtfySubscriptionRepository, NtfyTarget
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context
from src.infrastructure.external.ntfy_client import (
    RETRYABLE_OUTCOMES,
    NtfyClient,
    NtfyOutcome,
    NtfyPublishResult,
)
from src.infrastructure.observability.metrics_channels import ntfy_publications_total

logger = structlog.get_logger(__name__)

#: Where a notification with no link of its own takes the person: the chat.
DEFAULT_CLICK_PATH = "/dashboard/chat"

#: What a store that cannot be read raises: the database, its connection, a wait.
_STORE_FAILURES = (SQLAlchemyError, OSError, TimeoutError)


class NtfyTargetsUnreadable(Exception):
    """The subscriptions could not be read: nothing was published, so trying again is safe."""


@dataclass(frozen=True, slots=True)
class NtfyNotice:
    """What one target receives, before its content choice applies."""

    title: str
    body: str
    click: str
    language: str
    privacy: NotificationPrivacy = NotificationPrivacy.NORMAL


@dataclass(frozen=True, slots=True)
class NtfyBatch:
    """How a delivery to several targets ended."""

    outcomes: tuple[NtfyOutcome, ...] = ()
    retry_after_seconds: int | None = None

    @property
    def sent(self) -> int:
        """Publications a server accepted."""
        return sum(1 for outcome in self.outcomes if outcome is NtfyOutcome.SENT)

    @property
    def failed(self) -> int:
        """Publications no server accepted."""
        return len(self.outcomes) - self.sent

    @property
    def retryable(self) -> bool:
        """Nothing was accepted, and nothing that failed could have reached a device."""
        return (
            self.sent == 0
            and bool(self.outcomes)
            and all(outcome in RETRYABLE_OUTCOMES for outcome in self.outcomes)
        )


async def ntfy_available() -> bool:
    """Whether ntfy may be used right now: the deployment ceiling and the operator's switch."""
    return await is_capability_enabled(PlatformCapability.NTFY)


def click_url(path: str | None) -> str:
    """The absolute address a notification opens: LIA's own path on its public origin.

    Args:
        path: A path the notification names (``/dashboard/…``), or None for the chat.

    Returns:
        The absolute address; never another origin.
    """
    chosen = path if path and path.startswith("/") and not path.startswith("//") else None
    return settings.frontend_url.rstrip("/") + (chosen or DEFAULT_CLICK_PATH)


async def _publish(client: NtfyClient, target: NtfyTarget, notice: NtfyNotice) -> NtfyPublishResult:
    """One publication, on the road its server takes."""
    sent = publication(
        topic=target.topic,
        title=notice.title,
        body=notice.body,
        click=notice.click,
        content=target.content,
        language=notice.language,
        privacy=notice.privacy,
    )
    if target.server_kind is NtfyServerKind.INSTANCE:
        if not settings.ntfy_server_url:
            return NtfyPublishResult(NtfyOutcome.NOT_CONFIGURED)
        return await client.publish_trusted(
            settings.ntfy_server_url, sent, token=settings.ntfy_publish_token or None
        )
    if not settings.ntfy_custom_servers_enabled or not target.server_url:
        return NtfyPublishResult(NtfyOutcome.NOT_CONFIGURED)
    return await client.publish_checked(target.server_url, sent, token=target.token)


async def deliver(
    pairs: Sequence[tuple[NtfyTarget, NtfyNotice]], *, concurrency: int = 1
) -> NtfyBatch:
    """Publish each notice to its target, then write every outcome.

    Args:
        pairs: Each detached target with what it receives.
        concurrency: Publications in flight at once (a broadcast's burst).

    Returns:
        The batch's outcomes, in the order of ``pairs``.
    """
    if not pairs:
        return NtfyBatch()
    client = NtfyClient(timeout=settings.ntfy_timeout_seconds)
    gate = asyncio.Semaphore(max(1, concurrency))

    async def one(target: NtfyTarget, notice: NtfyNotice) -> NtfyPublishResult:
        async with gate:
            try:
                result = await _publish(client, target, notice)
            except Exception as error:
                # One target's surprise never silences the others; it may have left, so it is
                # unknown, never retried.
                logger.warning("ntfy_publication_failed", error_type=type(error).__name__)
                result = NtfyPublishResult(NtfyOutcome.NO_ANSWER)
        ntfy_publications_total.labels(
            server_kind=target.server_kind.value, outcome=result.outcome.value
        ).inc()
        return result

    results = await asyncio.gather(*(one(target, notice) for target, notice in pairs))
    try:
        async with get_db_context() as db:
            await NtfySubscriptionRepository(db).record_outcomes(
                [
                    (target.id, result.outcome)
                    for (target, _), result in zip(pairs, results, strict=True)
                ],
                at=datetime.now(UTC),
            )
    except Exception as error:
        # The publications left: what they achieved still reaches the caller, or a caller
        # that retries would say everything twice. Only the settings' status is late.
        logger.warning(
            "ntfy_outcomes_unrecorded", targets=len(pairs), error_type=type(error).__name__
        )
    waits = [result.retry_after_seconds for result in results if result.retry_after_seconds]
    batch = NtfyBatch(
        outcomes=tuple(result.outcome for result in results),
        retry_after_seconds=max(waits) if waits else None,
    )
    logger.info("ntfy_delivered", targets=len(pairs), sent=batch.sent, failed=batch.failed)
    return batch


async def read_targets(
    user_ids: Sequence[UUID],
) -> tuple[list[NtfyTarget], dict[UUID, str | None]]:
    """The active targets of some accounts and their languages, read in one short session.

    Args:
        user_ids: The accounts.

    Returns:
        The detached targets, and each account's stored language.

    Raises:
        NtfyTargetsUnreadable: The store could not be read; nothing was published.
    """
    try:
        async with get_db_context() as db:
            targets = await NtfySubscriptionRepository(db).active_targets(user_ids)
            owners = sorted({target.user_id for target in targets})
            rows = (
                await db.execute(select(User.id, User.language).where(User.id.in_(owners)))
            ).all()
    except _STORE_FAILURES as error:
        raise NtfyTargetsUnreadable from error
    return targets, {row.id: row.language for row in rows}


async def push_to_ntfy(
    user_id: UUID,
    *,
    title: str,
    body: str,
    click_path: str | None = None,
    privacy: NotificationPrivacy = NotificationPrivacy.NORMAL,
) -> NtfyBatch:
    """Publish one notification to every active ntfy subscription of an account.

    Args:
        user_id: The account.
        title: The notification's title, as the push shows it.
        body: Its words, as the push shows them (plain text).
        click_path: LIA's path the notification opens; the chat when None.
        privacy: Whether the notification is kept in LIA (never leaves with its words).

    Returns:
        How the publications ended; empty when ntfy is unavailable or unsubscribed.

    Raises:
        NtfyTargetsUnreadable: The subscriptions could not be read; nothing was published.
    """
    if not await ntfy_available():
        return NtfyBatch()
    targets, languages = await read_targets([user_id])
    notice = NtfyNotice(
        title=title,
        body=body,
        click=click_url(click_path),
        language=resolve_language(languages.get(user_id)),
        privacy=privacy,
    )
    # A person's few topics are reached together: a push waits for one server's timeout at
    # most, never for the sum of them (the ceiling bounds how many there are).
    return await deliver([(target, notice) for target in targets], concurrency=len(targets))


__all__ = [
    "DEFAULT_CLICK_PATH",
    "NtfyBatch",
    "NtfyNotice",
    "NtfyTargetsUnreadable",
    "click_url",
    "deliver",
    "ntfy_available",
    "push_to_ntfy",
    "read_targets",
]
