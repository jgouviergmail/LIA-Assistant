"""Leader-elected push channel sync job (lot H, 2026-08).

Runs on the scheduler leader: for every user with an active Google connector,
ensures a live watch channel (creating or renewing as needed). Each user gets
its own DB session (AsyncSession is not concurrency-safe; the sweep is
sequential on purpose — it is a background job, not a latency path), and one
user's failure never stops the sweep: push is an optimization, the fallback
is polling with TTL-bounded staleness.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import select

from src.core.config import settings
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.push_channels.repository import PushChannelRepository
from src.domains.push_channels.service import PushChannelService
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_push_channels import push_channel_sync_total

logger = structlog.get_logger(__name__)


async def _list_user_ids(connector_type: ConnectorType) -> list[UUID]:
    """Users holding an ACTIVE connector of the given type."""
    async with get_db_context() as db:
        result = await db.execute(
            select(Connector.user_id).where(
                Connector.connector_type == connector_type,
                Connector.status == ConnectorStatus.ACTIVE,
            )
        )
        return list(result.scalars().all())


async def _ensure_user_calendar(user_id: UUID) -> None:
    """Ensure the user's calendar events.watch channel."""
    from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
    from src.domains.connectors.service import ConnectorService

    async with get_db_context() as db:
        connector_service = ConnectorService(db)
        credentials = await connector_service.get_connector_credentials(
            user_id, ConnectorType.GOOGLE_CALENDAR
        )
        if credentials is None:
            return
        client = GoogleCalendarClient(user_id, credentials, connector_service)
        await PushChannelService(db).ensure_calendar_watch(user_id, client)


async def _ensure_user_drive(user_id: UUID) -> None:
    """Ensure the user's Drive changes.watch channel."""
    from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
    from src.domains.connectors.service import ConnectorService

    async with get_db_context() as db:
        connector_service = ConnectorService(db)
        credentials = await connector_service.get_connector_credentials(
            user_id, ConnectorType.GOOGLE_DRIVE
        )
        if credentials is None:
            return
        client = GoogleDriveClient(user_id, credentials, connector_service)
        await PushChannelService(db).ensure_drive_watch(user_id, client)


async def _ensure_user_gmail(user_id: UUID) -> None:
    """Ensure the user's Gmail users.watch subscription (phase 2)."""
    from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
    from src.domains.connectors.clients.google_gmail_settings_client import (
        GoogleGmailSettingsClient,
    )
    from src.domains.connectors.service import ConnectorService

    async with get_db_context() as db:
        connector_service = ConnectorService(db)
        credentials = await connector_service.get_connector_credentials(
            user_id, ConnectorType.GOOGLE_GMAIL
        )
        if credentials is None:
            return
        # The mailbox address keys the Pub/Sub event → channel resolution.
        profile = await GoogleGmailClient(user_id, credentials, connector_service).get_profile()
        email_address = profile.get("emailAddress", "")
        if not email_address:
            return
        client = GoogleGmailSettingsClient(user_id, credentials, connector_service)
        await PushChannelService(db).ensure_gmail_watch(user_id, client, email_address)


async def _purge_orphan_channels(active_users_by_provider: dict[str, set[UUID]]) -> int:
    """Delete channels whose owner lost the matching connector.

    Only the providers in the current sweep scope are purged: a provider
    whose phase flag is off keeps its rows (the Gmail dedup ledger must
    survive a temporary phase toggle). The Google-side watch cannot be
    stopped without the departed user's credentials — it dies at its own
    expiry, and its interim notifications hit an unknown channel (ignored).

    Args:
        active_users_by_provider: provider value → user ids holding an
            ACTIVE matching connector.

    Returns:
        Number of purged rows (exact).
    """
    purged = 0
    async with get_db_context() as db:
        repo = PushChannelRepository(db)
        for provider, user_ids in active_users_by_provider.items():
            purged += await repo.delete_channels_not_in(provider, user_ids)
        await db.commit()
    if purged:
        logger.info("push_orphan_channels_purged", purged=purged)
    return purged


async def sync_push_channels() -> dict[str, int]:
    """Ensure/renew every push channel + purge orphans (scheduler job body).

    Returns:
        {"ensured", "errors", "purged"} — exact counts of the sweep.
    """
    if not settings.push_channels_enabled:
        return {"ensured": 0, "errors": 0, "purged": 0}

    from src.domains.push_channels.models import PushChannelProvider

    sweeps: list[tuple[ConnectorType, str, object]] = [
        (
            ConnectorType.GOOGLE_CALENDAR,
            PushChannelProvider.GOOGLE_CALENDAR.value,
            _ensure_user_calendar,
        ),
        (ConnectorType.GOOGLE_DRIVE, PushChannelProvider.GOOGLE_DRIVE.value, _ensure_user_drive),
    ]
    if settings.gmail_push_enabled:
        sweeps.append(
            (ConnectorType.GOOGLE_GMAIL, PushChannelProvider.GOOGLE_GMAIL.value, _ensure_user_gmail)
        )

    ensured = 0
    errors = 0
    active_users_by_provider: dict[str, set[UUID]] = {}
    for connector_type, provider_value, ensure_fn in sweeps:
        try:
            user_ids = await _list_user_ids(connector_type)
        except Exception as exc:  # noqa: BLE001 — one provider must not kill the job
            logger.warning(
                "push_sync_listing_failed",
                connector_type=connector_type.value,
                error=str(exc),
            )
            errors += 1
            continue
        active_users_by_provider[provider_value] = set(user_ids)
        for user_id in user_ids:
            try:
                await ensure_fn(user_id)  # type: ignore[operator]
                ensured += 1
                push_channel_sync_total.labels(result="ensured").inc()
            except Exception as exc:  # noqa: BLE001 — sweep continues past one user
                errors += 1
                push_channel_sync_total.labels(result="error").inc()
                logger.warning(
                    "push_sync_user_failed",
                    connector_type=connector_type.value,
                    user_id=str(user_id),
                    error=str(exc),
                )

    try:
        purged = await _purge_orphan_channels(active_users_by_provider)
    except Exception as exc:  # noqa: BLE001 — purge is housekeeping, never fatal
        logger.warning("push_orphan_purge_failed", error=str(exc))
        purged = 0
        errors += 1

    logger.info("push_channels_synced", ensured=ensured, errors=errors, purged=purged)
    return {"ensured": ensured, "errors": errors, "purged": purged}
