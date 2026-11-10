"""Native SMS display pages: names OR literal body fragments, with honest bounds."""

import builtins
from uuid import UUID

from sqlalchemy import Select, case, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.ingestion.key_material import key_for_owner
from src.domains.shared.display_queries import read_display_page
from src.domains.shared.text_normalization import normalize_search_text
from src.domains.sms.content import read_sms_content
from src.domains.sms.cursors import SmsCursor
from src.domains.sms.display_identities import DisplayIdentities, display_identities
from src.domains.sms.display_index import display_candidates, display_hashes
from src.domains.sms.display_schemas import SmsDisplayCursor, SmsDisplayQuery, display_cursor_for
from src.domains.sms.facade import resolved_view
from src.domains.sms.identity_resolution import resolve_senders
from src.domains.sms.identity_store import validate_resolutions
from src.domains.sms.models import SmsMessage
from src.domains.sms.read_schemas import SmsPage, SmsView
from src.domains.sms.reads import require_read
from src.domains.sms.repository import message_query, project
from src.domains.sms.search import blind_digest
from src.domains.sms.search_limits import VerificationBudget, bounded_candidates, search_sql_budget
from src.domains.sms.sender_policy import normalize_sender


async def _filtered(
    db: AsyncSession,
    statement: Select[tuple[SmsMessage]],
    needle: str,
    identities: DisplayIdentities,
) -> Select[tuple[SmsMessage]]:
    """Admit names by SQL and verify only body candidates not already covered."""
    if not needle:
        return statement
    matching = [
        digest
        for digest, identity in identities.by_hash.items()
        if needle in normalize_search_text(identity.display_name)
    ]
    budget = VerificationBudget()
    candidates = display_candidates(
        statement.where(SmsMessage.sender_hash.not_in(matching)),
        identities.scope.owner,
        display_hashes(identities.scope.owner, needle, key=identities.scope.key),
    )
    rows = await bounded_candidates(db, candidates)
    admitted: list[UUID] = []
    for row in rows:
        body = read_sms_content(row.body_encrypted)
        budget.charge(body)
        if needle in normalize_search_text(body):
            admitted.append(row.id)
    budget.charge("")
    return statement.where(or_(SmsMessage.sender_hash.in_(matching), SmsMessage.id.in_(admitted)))


def _ordered(
    statement: Select[tuple[SmsMessage]],
    query: SmsDisplayQuery,
    identities: DisplayIdentities | None,
) -> Select[tuple[SmsMessage]]:
    """Alphabetical ranks live only in this query; equal names share one rank."""
    if query.sort == "name" and identities is not None:
        names = {
            digest: normalize_search_text(identity.display_name)
            for digest, identity in identities.by_hash.items()
        }
        ranks = {name: index for index, name in enumerate(sorted(set(names.values())))}
        order = case(
            {digest: ranks[name] for digest, name in names.items()},
            value=SmsMessage.sender_hash,
            else_=len(ranks),
        )
        statement = statement.order_by(order)
    direction = (
        SmsMessage.received_at.asc() if query.sort == "oldest" else SmsMessage.received_at.desc()
    )
    return statement.order_by(direction, SmsMessage.id.asc())


class SmsDisplayReader:
    """Session-only display reader; no assistant consent, model or register act."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(self, owner: UUID, query: SmsDisplayQuery) -> SmsPage:
        """Read one exact native page and revalidate every source before publication.

        Args:
            owner: Authenticated owner of the archive.
            query: Literal filter, ordering, period and encrypted continuation.

        Returns:
            An exact matching count and one page, or an explicit bounded refusal.

        Raises:
            ResourceConflictError: A stale continuation/authority or an overly broad query.
        """
        actor = await require_read(self.db, owner)
        cursor = display_cursor_for(owner, query, actor.extraction_revision or 0)
        sender_digest = (
            blind_digest(owner, "sender", normalize_sender(query.sender), key=key_for_owner(actor))
            if query.sender is not None
            else None
        )
        window = SmsCursor(
            owner=owner, filters="native-display", revision=cursor.revision, as_of=cursor.as_of
        )
        statement = await message_query(self.db, owner, query, window, sender_digest=sender_digest)
        needle = normalize_search_text((query.query or "").strip())
        identities = None
        if needle or query.sort == "name":
            identities = await display_identities(self.db, owner, statement, cursor.revision)
            if identities is None:
                return await self._page(cursor, [], 0, None)
            if query.cursor and cursor.identities != identities.fingerprint:
                raise ResourceConflictError("sms_cursor", detail={"error_code": "STALE_CURSOR"})
            statement = await _filtered(self.db, statement, needle, identities)
        async with search_sql_budget(self.db):
            items, total = await read_display_page(
                self.db,
                _ordered(statement, query, identities),
                decode=lambda row: project(row[0]),
                query="",
                text_of=lambda row: (),
                limit=query.limit,
                offset=cursor.offset,
            )
        return await self._page(cursor, items, total, identities)

    async def _page(
        self,
        cursor: SmsDisplayCursor,
        items: builtins.list[SmsView],
        total: int,
        identities: DisplayIdentities | None,
    ) -> SmsPage:
        """Resolve only visible rows on a chronological unfiltered page, then recheck."""
        if items:
            if identities is not None:
                items = [
                    resolved_view(item, identities.by_hash[identities.scope.digest(item.sender)])
                    for item in items
                ]
            else:
                await self.db.commit()
                resolved = await resolve_senders(
                    cursor.owner,
                    [item.sender for item in items],
                    revision=cursor.revision,
                    assistant=False,
                )
                await validate_resolutions(self.db, resolved.scope, assistant=False)
                items = [resolved_view(item, resolved.identities[item.sender]) for item in items]
        actor = await require_read(self.db, cursor.owner)
        if (actor.extraction_revision or 0) != cursor.revision:
            raise ResourceConflictError("sms", detail={"error_code": "STALE_STATE"})
        position = cursor.offset + len(items)
        following = (
            cursor.model_copy(
                update={
                    "offset": position,
                    "identities": identities.fingerprint if identities is not None else None,
                }
            ).encode()
            if position < total
            else None
        )
        return SmsPage(
            items=items,
            total=total,
            as_of=cursor.as_of,
            revision=cursor.revision,
            next_cursor=following,
        )
