"""Fresh heartbeat delivery authority; paid work does not freeze user consent."""

import hashlib
import json
from datetime import UTC, datetime, tzinfo
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from pydantic import JsonValue, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.connectors.models import Connector
from src.domains.heartbeat.preference_commands import (
    HEARTBEAT_PREFERENCE_FIELDS,
    heartbeat_preference_values,
)
from src.domains.heartbeat.schemas import HeartbeatTarget
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.system_settings.registry import decode_bool
from src.domains.users.models import User
from src.infrastructure.proactive.base import ProactiveTaskResult
from src.infrastructure.proactive.eligibility import is_within_hour_window

logger = structlog.get_logger(__name__)
_SCOPES = TypeAdapter(list[str])
_JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


async def _connector_authority_digest(db: AsyncSession, actor_id: UUID) -> str:
    """One bounded query; token refresh and credential ciphertext are deliberately absent."""
    rows = await db.execute(
        select(
            Connector.id,
            Connector.connector_type,
            Connector.status,
            Connector.preferences_encrypted,
            Connector.scopes,
        )
        .where(Connector.user_id == actor_id)
        .order_by(Connector.id)
    )
    values = [
        (
            str(connector_id),
            connector_type.value,
            status.value,
            preferences,
            sorted(_SCOPES.validate_python(scopes)),
        )
        for connector_id, connector_type, status, preferences, scopes in rows.all()
    ]
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def _within_current_window(user: User) -> bool:
    zone: tzinfo
    try:
        zone = ZoneInfo(user.timezone or "UTC")
    except KeyError, ValueError:
        zone = UTC
    if (
        type(user.heartbeat_notify_start_hour) is not int
        or type(user.heartbeat_notify_end_hour) is not int
    ):
        return False
    return is_within_hour_window(
        datetime.now(UTC).astimezone(zone).hour,
        user.heartbeat_notify_start_hour,
        user.heartbeat_notify_end_hour,
    )


async def heartbeat_delivery_stamp(actor_id: UUID) -> str | None:
    """Read current authority in a separate short session, independent of the runner cache."""
    from src.infrastructure.database.session import get_db_context

    if not settings.heartbeat_enabled:
        return None
    try:
        async with get_db_context() as db:
            raw: str | None = await db.scalar(
                select(SystemSetting.value).where(
                    SystemSetting.key == SystemSettingKey.CAPABILITY_HEARTBEAT_ENABLED
                )
            )
            if raw is not None and not decode_bool(raw):
                return None
            user: User | None = await db.scalar(
                select(User)
                .where(User.id == actor_id, User.is_active, User.deleted_at.is_(None))
                .execution_options(populate_existing=True)
            )
            if (
                user is None
                or user.id != actor_id
                or not user.is_active
                or user.is_deleted
                or user.heartbeat_enabled is not True
                or not _within_current_window(user)
            ):
                return None
            values = heartbeat_preference_values(user, HEARTBEAT_PREFERENCE_FIELDS)
            values.update(
                actor_id=str(user.id),
                timezone=user.timezone,
                language=user.language,
                extraction_revision=user.extraction_revision,
                sms_preferences=_JSON_VALUE.validate_python(user.sms_preferences),
                sms_enabled=settings.sms_enabled,
                sms_capability=await db.scalar(
                    select(SystemSetting.value).where(
                        SystemSetting.key == SystemSettingKey.CAPABILITY_SMS_ENABLED
                    )
                ),
                home_location_encrypted=user.home_location_encrypted,
                last_known_location_encrypted=user.last_known_location_encrypted,
                use_last_known_location=user.use_last_known_location,
                interests_enabled=user.interests_enabled,
                journals_enabled=user.journals_enabled,
                habits_enabled=user.habits_enabled,
                memory_enabled=user.memory_enabled,
                health_metrics_agents_enabled=user.health_metrics_agents_enabled,
                connector_authority=await _connector_authority_digest(db, actor_id),
            )
            return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
    except (SQLAlchemyError, ValueError, ValidationError) as exc:
        logger.warning(
            "heartbeat_delivery_authority_unavailable", exception_type=type(exc).__name__
        )
        return None


def abandoned_heartbeat_selection(target: HeartbeatTarget) -> ProactiveTaskResult:
    """Carry the decision's actual billing records when its rewrite is refused."""
    return ProactiveTaskResult(
        success=False,
        error="SETTINGS_CHANGED",
        tokens_in=target.decision_tokens_in,
        tokens_out=target.decision_tokens_out,
        tokens_cache=target.decision_tokens_cache,
        tokens_cache_write=target.decision_tokens_cache_write,
        billing_records=target.billing_records,
    )


async def heartbeat_delivery_current(actor_id: UUID, expected: str | None) -> bool:
    """An absent stamp denotes another task family; a captured stamp must still match."""
    return expected is None or await heartbeat_delivery_stamp(actor_id) == expected
