"""Receipt, encrypted message, blind index and outbox commit atomically.

The owner fence serializes source/token revocation, policy changes, deletions and
quota admission. Receipt tombstones survive message deletion and token rotation.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import JsonValue, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, raise_bearer_auth_failed, raise_invalid_input
from src.core.security.utils import encrypt_data
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.ingestion.authority import require_authority
from src.domains.ingestion.budgets import IngestionBudget
from src.domains.ingestion.key_material import key_for_owner
from src.domains.ingestion.models import (
    IngestionDelivery,
    IngestionReceipt,
    IngestionSource,
    IngestionToken,
)
from src.domains.ingestion.principal import IngestionPrincipal
from src.domains.ingestion.registry import IngestionResource, policy_for
from src.domains.ingestion.token_auth import hash_token
from src.domains.sms.models import SmsMessage, SmsSearchTerm, SmsSenderBlock
from src.domains.sms.preferences import SmsPreferences
from src.domains.sms.relation_invalidation import invalidate_sms_debriefs
from src.domains.sms.schemas import IngestItemReceipt, SmsIngestItem, SmsIngestResponse, Verdict
from src.domains.sms.search import blind_digest, blind_terms
from src.domains.sms.sender_policy import normalize_sender
from src.domains.sms.sensitive_filter import FILTER_VERSION, contains_access_secret
from src.domains.users.models import User


class SmsIngestionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def authenticate(self, raw_token: str) -> IngestionPrincipal:
        row = (
            await self.db.execute(
                select(IngestionToken)
                .join(IngestionSource, IngestionSource.id == IngestionToken.source_id)
                .join(User, User.id == IngestionToken.user_id)
                .where(
                    IngestionToken.token_hash == hash_token(raw_token),
                    IngestionToken.revoked_at.is_(None),
                    IngestionSource.user_id == IngestionToken.user_id,
                    IngestionSource.resource == "sms",
                    IngestionSource.revoked_at.is_(None),
                    User.is_active.is_(True),
                    User.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise_bearer_auth_failed("Invalid ingestion token")
        if policy_for(IngestionResource.SMS).write_scope not in row.scopes:
            raise AuthorizationError(detail={"error_code": "INGESTION_SCOPE_DENIED"})
        return IngestionPrincipal(
            user_id=row.user_id,
            token_id=row.id,
            source_id=row.source_id,
            scopes=frozenset(row.scopes),
        )

    async def ingest(
        self, principal: IngestionPrincipal, entries: list[JsonValue]
    ) -> SmsIngestResponse:
        if not entries or len(entries) > settings.ingestion_max_batch_items:
            raise_invalid_input("Invalid ingestion batch size")
        owner, source, token = await require_authority(self.db, principal, IngestionResource.SMS)
        await require_capability_fresh(self.db, PlatformCapability.SMS)
        key = key_for_owner(owner)
        prefs = SmsPreferences.from_stored(owner.sms_preferences)
        if not prefs.ingestion_enabled:
            raise AuthorizationError(detail={"error_code": "INGESTION_DISABLED"})
        blocked = set(
            (
                await self.db.scalars(
                    select(SmsSenderBlock.sender_hash).where(
                        SmsSenderBlock.user_id == principal.user_id
                    )
                )
            ).all()
        )
        occupied = (
            await self.db.scalar(
                select(func.coalesce(func.sum(SmsMessage.logical_bytes), 0)).where(
                    SmsMessage.user_id == principal.user_id
                )
            )
            or 0
        )
        receipt_count = (
            await self.db.scalar(
                select(func.count())
                .select_from(IngestionReceipt)
                .where(IngestionReceipt.user_id == principal.user_id)
            )
            or 0
        )
        budget = IngestionBudget(
            max(0, settings.sms_archive_max_logical_bytes - occupied),
            max(0, settings.ingestion_max_receipts_per_user - receipt_count),
        )
        results: list[IngestItemReceipt] = []
        for index, entry in enumerate(entries):
            results.append(
                await self._item(
                    principal, source, entry, index, blocked, budget, prefs.push_enabled, key=key
                )
            )
        await invalidate_sms_debriefs(self.db, principal.user_id, results)
        token.last_used_at = source.last_seen_at = datetime.now(UTC)
        await require_capability_fresh(self.db, PlatformCapability.SMS)
        await self.db.commit()
        return self._response(results)

    async def _item(
        self,
        principal: IngestionPrincipal,
        source: IngestionSource,
        entry: JsonValue,
        index: int,
        blocked: set[str],
        budget: IngestionBudget,
        push: bool,
        *,
        key: bytes,
    ) -> IngestItemReceipt:
        try:
            item = SmsIngestItem.model_validate(entry)
        except ValidationError:
            return IngestItemReceipt(index=index, verdict="invalid")
        canonical = item.model_dump_json(exclude={"event_id"})
        digest = blind_digest(principal.user_id, "payload", canonical, key=key)
        event_key = (
            blind_digest(principal.user_id, "event", str(item.event_id), key=key)
            if item.event_id
            else digest
        )
        previous = await self.db.scalar(
            select(IngestionReceipt).where(
                IngestionReceipt.user_id == principal.user_id,
                IngestionReceipt.source_id == source.id,
                IngestionReceipt.event_key == event_key,
            )
        )
        if previous is not None:
            verdict: Verdict = "duplicate" if previous.payload_hash == digest else "conflict"
            return IngestItemReceipt(index=index, verdict=verdict)
        if budget.available_receipts <= 0:
            return IngestItemReceipt(index=index, verdict="storage_full")
        sender_hash = blind_digest(
            principal.user_id, "sender", normalize_sender(item.sender), key=key
        )
        verdict = self._verdict(item.body, sender_hash in blocked)
        terms = blind_terms(principal.user_id, item.body, key=key) if verdict == "stored" else ()
        index_bytes = sum(len(term) // 2 for term in terms[: settings.sms_max_index_terms])
        size = len(item.sender.encode()) + len(item.body.encode()) + index_bytes
        if verdict == "stored" and size > budget.available_bytes:
            return IngestItemReceipt(index=index, verdict="storage_full")
        receipt = IngestionReceipt(
            id=uuid4(),
            user_id=principal.user_id,
            source_id=source.id,
            event_key=event_key,
            payload_hash=digest,
            verdict=verdict,
            filter_version=FILTER_VERSION,
        )
        self.db.add(receipt)
        await self.db.flush()
        budget.consume(size if verdict == "stored" else 0)
        if verdict != "stored":
            return IngestItemReceipt(index=index, verdict=verdict)
        message_id = await self._store(
            principal.user_id, receipt.id, item, sender_hash, size, push, terms=terms
        )
        return IngestItemReceipt(index=index, verdict="stored", message_id=message_id)

    @staticmethod
    def _verdict(body: str, blocked: bool) -> Verdict:
        if blocked:
            return "ignored_sender"
        return "ignored_sensitive" if contains_access_secret(body) else "stored"

    async def _store(
        self,
        owner: UUID,
        receipt_id: UUID,
        item: SmsIngestItem,
        sender_hash: str,
        size: int,
        push: bool,
        *,
        terms: tuple[str, ...],
    ) -> UUID:
        message = SmsMessage(
            id=uuid4(),
            user_id=owner,
            receipt_id=receipt_id,
            sender_encrypted=encrypt_data(item.sender),
            sender_hash=sender_hash,
            body_encrypted=encrypt_data(item.body),
            origin=item.o,
            received_at=item.date,
            date_kind=item.date_kind,
            logical_bytes=size,
            search_complete=len(terms) <= settings.sms_max_index_terms,
        )
        self.db.add(message)
        await self.db.flush()
        self.db.add(
            SmsSearchTerm(
                user_id=owner,
                message_id=message.id,
                term_hashes=[bytes.fromhex(term) for term in terms[: settings.sms_max_index_terms]],
            )
        )
        if push:
            self.db.add(IngestionDelivery(user_id=owner, receipt_id=receipt_id))
        await self.db.flush()
        return message.id

    @staticmethod
    def _response(items: list[IngestItemReceipt]) -> SmsIngestResponse:
        return SmsIngestResponse(
            received=len(items),
            inserted=sum(item.verdict == "stored" for item in items),
            duplicate=sum(item.verdict == "duplicate" for item in items),
            ignored=sum(item.verdict.startswith("ignored_") for item in items),
            rejected=sum(item.verdict in ("invalid", "storage_full") for item in items),
            conflict=sum(item.verdict == "conflict" for item in items),
            items=items,
        )
