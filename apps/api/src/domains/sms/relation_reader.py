"""One bounded directory read, exact sender aggregates, fresh publication."""

import asyncio
import hashlib
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

from sqlalchemy import Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.domains.shared.aggregates import NameActivity
from src.domains.shared.relation_sms import PersonalSms, RelationSmsPage, RelationSmsProof
from src.domains.sms.content import read_sms_content
from src.domains.sms.facade import resolved_view
from src.domains.sms.identity import IdentityBook, SenderIdentity
from src.domains.sms.identity_resolution import resolve_senders
from src.domains.sms.identity_store import ResolutionScope, validate_resolutions
from src.domains.sms.models import SmsMessage
from src.domains.sms.reads import require_read
from src.domains.sms.repository import project
from src.infrastructure.database.session import get_db_context


@asynccontextmanager
async def _read_db() -> AsyncIterator[AsyncSession]:
    async with get_db_context() as db:
        await db.execute(
            select(func.set_config("statement_timeout", str(settings.sms_search_timeout_ms), True))
        )
        yield db


async def source_stamp(db: AsyncSession, owner: UUID) -> str:
    count, latest = (
        await db.execute(
            select(func.count(), func.max(SmsMessage.created_at)).where(SmsMessage.user_id == owner)
        )
    ).one()
    return hashlib.sha256(f"{count}:{latest}".encode()).hexdigest()


async def _sender_identities(
    owner: UUID, rows: Sequence[Row[tuple[str, str, int, datetime]]], proof: RelationSmsProof
) -> tuple[IdentityBook, dict[str, SenderIdentity], ResolutionScope | None]:
    """Prepare sender names outside the SQL publication transaction."""
    if not rows:
        return IdentityBook(complete=True), {}, None
    resolved = await resolve_senders(
        owner,
        [read_sms_content(row[1]) for row in rows],
        revision=proof.revision,
        assistant=proof.assistant,
    )
    return IdentityBook(resolver=resolved.resolver), resolved.identities, resolved.scope


class SmsRelationReader:
    async def read(
        self, owner: UUID, *, person: str | None = None, limit: int = 10, assistant: bool = False
    ) -> RelationSmsPage:
        if not 1 <= limit <= settings.relations_max_items_per_section:
            raise ValueError("Invalid relation SMS page size")
        async with _read_db() as db:
            actor = await require_read(db, owner, assistant=assistant)
            proof = RelationSmsProof(
                owner_id=owner,
                revision=actor.extraction_revision or 0,
                stamp=await source_stamp(db, owner),
                as_of=datetime.now(UTC),
                assistant=assistant,
            )
            rows = (
                await db.execute(
                    select(
                        SmsMessage.sender_hash,
                        func.min(SmsMessage.sender_encrypted),
                        func.count(),
                        func.max(SmsMessage.received_at),
                    )
                    .where(SmsMessage.user_id == owner)
                    .group_by(SmsMessage.sender_hash)
                    .limit(settings.sms_directory_max_contacts + 1)
                )
            ).all()
        if len(rows) > settings.sms_directory_max_contacts:
            raise ResourceConflictError("sms", detail={"error_code": "QUERY_TOO_BROAD"})
        book, identities, scope = await _sender_identities(owner, rows, proof)
        activities, hashes = await self._resolve(rows, book, identities, person)
        async with _read_db() as db:
            actor = await require_read(db, owner, assistant=assistant)
            if scope is not None:
                await validate_resolutions(db, scope, assistant=assistant)
            await self._check_stamp(db, owner, proof, actor.extraction_revision or 0)
            selected = select(SmsMessage).where(
                SmsMessage.user_id == owner, SmsMessage.sender_hash.in_(hashes)
            )
            total = await db.scalar(select(func.count()).select_from(selected.subquery())) or 0
            messages = (
                list(
                    (
                        await db.scalars(
                            selected.order_by(
                                SmsMessage.received_at.desc(), SmsMessage.id.desc()
                            ).limit(limit)
                        )
                    ).all()
                )
                if person is not None
                else []
            )
            items = []
            for row in messages:
                raw = project(row)
                item = resolved_view(raw, identities[raw.sender])
                items.append(PersonalSms.model_validate(item.model_dump()))
            return RelationSmsPage(
                available=True, activities=activities, messages=items, total=total, proof=proof
            )

    @staticmethod
    async def _resolve(
        rows: Sequence[Row[tuple[str, str, int, datetime]]],
        book: IdentityBook,
        identities: dict[str, SenderIdentity],
        person: str | None,
    ) -> tuple[list[NameActivity], list[str]]:
        activities = []
        hashes = []
        target = book.resolver.key(person) if person is not None else None
        deadline = perf_counter() + settings.sms_identity_timeout_seconds
        for index, (digest, encrypted, count, latest) in enumerate(rows):
            if perf_counter() > deadline:
                raise ResourceConflictError("sms", detail={"error_code": "QUERY_TOO_BROAD"})
            if index % 16 == 0:
                await asyncio.sleep(0)
            identity = identities[read_sms_content(encrypted)]
            activities.append(NameActivity(identity.display_name, count, latest))
            if target is None or book.resolver.key(identity.display_name) == target:
                hashes.append(digest)
        return activities, hashes

    async def check(
        self, db: AsyncSession, owner: UUID, proof: RelationSmsProof | RelationSmsPage
    ) -> None:
        selected = proof.proof if isinstance(proof, RelationSmsPage) else proof
        if selected is None or selected.owner_id != owner or not selected.assistant:
            raise ResourceConflictError("sms", detail={"error_code": "STALE_STATE"})
        actor = await require_read(db, owner, assistant=True)
        await self._check_stamp(db, owner, selected, actor.extraction_revision or 0)

    @staticmethod
    async def _check_stamp(
        db: AsyncSession, owner: UUID, proof: RelationSmsProof, revision: int
    ) -> None:
        if revision != proof.revision or await source_stamp(db, owner) != proof.stamp:
            raise ResourceConflictError("sms", detail={"error_code": "STALE_STATE"})
