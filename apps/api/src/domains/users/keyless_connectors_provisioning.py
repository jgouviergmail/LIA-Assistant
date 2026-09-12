"""Start every new account with the connectors that ask nothing of the person.

Wikipedia, the browser, Google Places, Google Weather and Google Environment
are activated by ONE click in the settings — no OAuth consent, no personal
key. A fresh account that has to find and press five buttons before the
assistant can look up a place or the weather has a worse first day than one
where those already work, so they are provisioned at sign-up (owner decision,
2026-09-11 — firm, no instance setting).

The list is the backend's own declaration (``ConnectorType.get_keyless_types``),
never a copy. What is NOT provisioned: a type the administrator disabled
globally, a platform-key type on an instance with no ``GOOGLE_API_KEY`` (an
active connector that can only fail is worse than an absent one), and the
browser on an instance that switched it off. Existing accounts are never
touched — they made their choices.

Created: 2026-09-12
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.connectors.repository import ConnectorRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

#: Stamp on ``connector_metadata`` so the register says where the row came from.
PROVISIONED_BY = "signup_keyless"


async def _skip_reason(
    repository: ConnectorRepository, connector_type: ConnectorType
) -> str | None:
    """Why this type must NOT be provisioned on this instance, or ``None``.

    Args:
        repository: Connector repository on the caller's session.
        connector_type: A keyless connector type.

    Returns:
        A short reason for the log, or ``None`` when the type may be activated.
    """
    # No row means enabled — the same default `ConnectorService._check_connector_enabled` applies.
    config = await repository.get_global_config_by_type(connector_type)
    if config is not None and not config.is_enabled:
        return "disabled_by_admin"
    if connector_type.uses_global_api_key and not settings.google_api_key:
        return "platform_key_missing"
    if connector_type is ConnectorType.BROWSER and not settings.browser_enabled:
        return "browser_disabled"
    return None


def _build_connector(user_id: UUID, connector_type: ConnectorType) -> Connector:
    """The row manual activation would write, plus the provenance stamp.

    Args:
        user_id: The freshly created account.
        connector_type: A keyless connector type.

    Returns:
        An ACTIVE connector with empty credentials.
    """
    return Connector(
        user_id=user_id,
        connector_type=connector_type,
        # ACTIVE on purpose: an inactive connector makes the tool answer
        # "category not activated", the broken-looking state we avoid.
        status=ConnectorStatus.ACTIVE,
        scopes=[],
        credentials_encrypted="{}",  # Nothing to store — platform key or no key at all
        connector_metadata={
            "auth_type": "global_api_key" if connector_type.uses_global_api_key else "none",
            "activated_at": datetime.now(UTC).isoformat(),
            # No probe ran: ACTIVE means "usable", not "provider-authenticated".
            "functionally_verified": False,
            "provisioned_by": PROVISIONED_BY,
        },
    )


async def provision_keyless_connectors(db: AsyncSession, user_id: UUID) -> list[ConnectorType]:
    """Activate, on a new account, every connector that needs no credential.

    Never raises: an account that starts without Wikipedia is a small loss, an
    account that cannot be created is a total one.

    Args:
        db: Session whose transaction the caller owns (no commit here).
        user_id: The freshly created account.

    Returns:
        The types actually provisioned, in a stable order.
    """
    repository = ConnectorRepository(db)
    provisioned: list[ConnectorType] = []
    try:
        for connector_type in sorted(ConnectorType.get_keyless_types(), key=lambda t: t.value):
            reason = await _skip_reason(repository, connector_type)
            if reason is not None:
                logger.debug(
                    "keyless_connector_not_provisioned",
                    user_id=str(user_id),
                    connector_type=connector_type.value,
                    reason=reason,
                )
                continue
            db.add(_build_connector(user_id, connector_type))
            provisioned.append(connector_type)
    except Exception as exc:  # noqa: BLE001 — never break a sign-up
        logger.error(
            "keyless_connectors_provisioning_failed",
            user_id=str(user_id),
            error_type=type(exc).__name__,
            provisioned=[t.value for t in provisioned],
        )
        # What was staged before the failure stays staged: the caller's
        # commit decides, and the return value must not deny those rows.
        return provisioned

    logger.info(
        "keyless_connectors_provisioned",
        user_id=str(user_id),
        connector_types=[t.value for t in provisioned],
    )
    return provisioned
