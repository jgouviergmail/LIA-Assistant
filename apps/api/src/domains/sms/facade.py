"""Resolve after releasing the read transaction, then revalidate publication."""

from typing import TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.sms.identity import IdentityBook
from src.domains.sms.identity_directory import load_identity_book
from src.domains.sms.read_schemas import SmsPage, SmsQuery, SmsSenderPage, SmsSenderView, SmsView
from src.domains.sms.reads import SmsReadService, require_read

_View = TypeVar("_View", SmsView, SmsSenderView)


def resolve_view(item: _View, book: IdentityBook) -> _View:
    identity = book.resolve(item.sender)
    return item.model_copy(
        update={
            "display_name": identity.display_name,
            "identity_source": identity.source,
            "identity_state": identity.state,
            "relation_key": identity.relation_key,
        }
    )


class SmsFacade:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.reader = SmsReadService(db)

    async def _book(self, owner: UUID, revision: int, *, assistant: bool) -> IdentityBook:
        await self.db.commit()
        book = await load_identity_book(owner)
        actor = await require_read(self.db, owner, assistant=assistant)
        if (actor.extraction_revision or 0) != revision:
            raise ResourceConflictError("sms", detail={"error_code": "STALE_STATE"})
        return book

    async def list(
        self, owner: UUID, query: SmsQuery, *, assistant: bool, unmentioned_only: bool = False
    ) -> SmsPage:
        page = await self.reader.list(
            owner, query, assistant=assistant, unmentioned_only=unmentioned_only
        )
        if page.items:
            book = await self._book(owner, page.revision, assistant=assistant)
            page = page.model_copy(
                update={"items": [resolve_view(item, book) for item in page.items]}
            )
        return page

    async def get(self, owner: UUID, message_id: UUID, *, assistant: bool) -> SmsView:
        item = await self.reader.get(owner, message_id, assistant=assistant)
        actor = await require_read(self.db, owner, assistant=assistant)
        revision = actor.extraction_revision or 0
        book = await self._book(owner, revision, assistant=assistant)
        return resolve_view(item, book)

    async def senders(
        self, owner: UUID, *, assistant: bool, limit: int = 20, cursor: str | None = None
    ) -> SmsSenderPage:
        page = await self.reader.senders(owner, assistant=assistant, limit=limit, cursor=cursor)
        if page.items:
            book = await self._book(owner, page.revision, assistant=assistant)
            page = page.model_copy(
                update={"items": [resolve_view(item, book) for item in page.items]}
            )
        return page
