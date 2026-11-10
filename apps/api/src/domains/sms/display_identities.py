"""Resolve distinct senders outside the read transaction, then fence publication."""

import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.sms.content import read_sms_content
from src.domains.sms.identity import SenderIdentity
from src.domains.sms.identity_resolution import resolve_senders
from src.domains.sms.identity_store import ResolutionScope, validate_resolutions
from src.domains.sms.models import SmsMessage
from src.domains.sms.search import blind_digest
from src.domains.sms.search_limits import VerificationBudget, search_sql_budget, too_broad


@dataclass(frozen=True, slots=True)
class DisplayIdentities:
    """Ephemeral identity projection; no plaintext search/sort names are stored."""

    scope: ResolutionScope
    by_hash: dict[str, SenderIdentity]
    fingerprint: str


async def display_identities(
    db: AsyncSession,
    owner: UUID,
    statement: Select[tuple[SmsMessage]],
    revision: int,
) -> DisplayIdentities | None:
    """Resolve one representative per sender, independently of the message budget.

    Args:
        db: Native request session; its read transaction ends before resolution.
        owner: Authenticated account.
        statement: Complete owned/time-bounded archive selection.
        revision: Read authority revision, revalidated after resolution.

    Returns:
        The complete identity mapping, or None for an empty archive selection.
    """
    selection = (
        statement.with_only_columns(SmsMessage.sender_hash, SmsMessage.sender_encrypted)
        .distinct(SmsMessage.sender_hash)
        .order_by(SmsMessage.sender_hash, SmsMessage.received_at.desc(), SmsMessage.id.desc())
        .limit(settings.sms_display_max_senders + 1)
    )
    async with search_sql_budget(db):
        rows = (await db.execute(selection)).all()
    if len(rows) > settings.sms_display_max_senders:
        too_broad()
    if not rows:
        return None
    budget = VerificationBudget()
    senders: dict[str, str] = {}
    for digest, encrypted in rows:
        sender = read_sms_content(encrypted)
        budget.charge(sender)
        senders[digest] = sender
    await db.commit()
    resolved = await resolve_senders(
        owner, list(senders.values()), revision=revision, assistant=False
    )
    await validate_resolutions(db, resolved.scope, assistant=False)
    by_hash = {digest: resolved.identities[sender] for digest, sender in senders.items()}
    snapshot = json.dumps(
        [
            str(resolved.scope.generation),
            resolved.scope.authority,
            [
                (
                    digest,
                    identity.display_name,
                    identity.source,
                    identity.state,
                    identity.relation_key,
                )
                for digest, identity in sorted(by_hash.items())
            ],
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    fingerprint = blind_digest(owner, "display-identities", snapshot, key=resolved.scope.key)
    return DisplayIdentities(resolved.scope, by_hash, fingerprint)
