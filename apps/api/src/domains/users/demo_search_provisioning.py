"""Lend the demonstrator's search key to every visitor account.

Brave Search is a per-USER connector: its key lives on each account. A visitor
of a throwaway instance has no key and no reason to get one, so without help
the search agent would be visible and permanently broken — worse than an
absent feature.

The instance therefore holds ONE key and provisions it on each visitor account
at creation. The nightly purge takes the connectors down with the accounts
(FK cascade), so nothing outlives the night.

Why Brave rather than Perplexity: Brave has a free tier, Perplexity bills per
call and would spend the daily budget on searches instead of on the
conversation (owner arbitration 2026-08-06).

Created: 2026-08-06 (live-demonstrator programme, lot 4)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.security import encrypt_data
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.connectors.schemas import APIKeyCredentials

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


async def provision_shared_search(db: AsyncSession, user_id: UUID) -> bool:
    """Give this account the instance's shared search key.

    No-op outside demo mode, and no-op when no key is configured: a private
    instance must never see connectors appear on its accounts.

    Never raises. A visitor who cannot search is disappointed; a visitor who
    cannot sign up sees nothing at all.

    Args:
        db: Session whose transaction the caller owns (no commit here).
        user_id: The freshly created account.

    Returns:
        True when the connector was added.
    """
    if not settings.demo_mode_enabled:
        return False
    shared_key = getattr(settings, "demo_shared_search_api_key", "") or ""
    if not shared_key:
        return False

    try:
        credentials = APIKeyCredentials(api_key=shared_key)
        db.add(
            Connector(
                user_id=user_id,
                connector_type=ConnectorType.BRAVE_SEARCH,
                # ACTIVE on purpose: an inactive connector makes the tool
                # answer "category not activated", which is the broken-looking
                # state this whole function exists to avoid.
                status=ConnectorStatus.ACTIVE,
                scopes=[],
                credentials_encrypted=encrypt_data(credentials.model_dump_json()),
                connector_metadata={"provisioned_by": "demo_shared_key"},
            )
        )
    except Exception as exc:  # noqa: BLE001 — never break a sign-up
        logger.error(
            "demo_shared_search_provisioning_failed",
            user_id=str(user_id),
            error_type=type(exc).__name__,
        )
        return False

    logger.info("demo_shared_search_provisioned", user_id=str(user_id))
    return True
