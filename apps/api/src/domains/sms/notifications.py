"""Content-free notification policy, rechecked under the owner fence."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.core.i18n import normalize_language
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.ingestion.models import IngestionReceipt, IngestionSource, IngestionToken
from src.domains.sms.models import SmsMessage, SmsSenderBlock
from src.domains.sms.preferences import SmsPreferences
from src.domains.users.models import User

_WORDS: dict[str, tuple[str, str]] = {
    "fr": ("Nouveau SMS", "Un nouveau SMS est disponible dans Mes SMS."),
    "en": ("New SMS", "A new SMS is available in My SMS."),
    "de": ("Neue SMS", "Eine neue SMS ist unter Meine SMS verfügbar."),
    "es": ("Nuevo SMS", "Hay un nuevo SMS en Mis SMS."),
    "it": ("Nuovo SMS", "Un nuovo SMS è disponibile in I miei SMS."),
    "zh-CN": ("新短信", "“我的短信”中有一条新短信。"),
}


@dataclass(frozen=True, slots=True)
class SmsNotice:
    message_id: UUID
    title: str
    body: str
    language: str


async def notice_for(db: AsyncSession, owner: UUID, receipt_id: UUID) -> SmsNotice | None:
    user = await db.get(User, owner, populate_existing=True)
    if user is None or not user.is_active or user.deleted_at is not None:
        return None
    prefs = SmsPreferences.from_stored(user.sms_preferences)
    if not prefs.ingestion_enabled or not prefs.push_enabled:
        return None
    try:
        await require_capability_fresh(db, PlatformCapability.SMS)
    except AuthorizationError as error:
        if (
            isinstance(error.detail, dict)
            and error.detail.get("error_code") == "CAPABILITY_DISABLED"
        ):
            return None
        raise
    row = (
        await db.execute(
            select(SmsMessage.id, SmsMessage.sender_hash)
            .join(IngestionReceipt, IngestionReceipt.id == SmsMessage.receipt_id)
            .join(IngestionSource, IngestionSource.id == IngestionReceipt.source_id)
            .where(
                SmsMessage.user_id == owner,
                IngestionReceipt.id == receipt_id,
                IngestionReceipt.user_id == owner,
                IngestionReceipt.verdict == "stored",
                IngestionSource.user_id == owner,
                IngestionSource.resource == "sms",
                IngestionSource.revoked_at.is_(None),
                exists(
                    select(IngestionToken.id).where(
                        IngestionToken.source_id == IngestionSource.id,
                        IngestionToken.user_id == owner,
                        IngestionToken.revoked_at.is_(None),
                        IngestionToken.scopes.contains(["sms:write"]),
                    )
                ),
            )
        )
    ).first()
    if row is None:
        return None
    blocked = await db.scalar(
        select(SmsSenderBlock.id).where(
            SmsSenderBlock.user_id == owner, SmsSenderBlock.sender_hash == row[1]
        )
    )
    if blocked is not None:
        return None
    language = normalize_language(user.language)
    title, body = _WORDS[language]
    return SmsNotice(row[0], title, body, language)
